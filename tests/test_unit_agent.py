"""Unit tests for the categorization agent (OpenAI Agents SDK layer).

No real OpenRouter/LLM calls: `Runner.run_sync` (the LLM loop) and the
agent builder are mocked, and the underlying deterministic services are
patched so priority order and fallback logic are exercised directly.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.agents import categorization_agent as ca
from app.schemas.agent import CategorizeOutcome


class FakeRunResult:
    """Stand-in for the agents SDK RunResult carrying final_output."""

    def __init__(self, final_output):
        self.final_output = final_output


def build_agent_mock():
    return patch.object(ca, "_build_agent", return_value=MagicMock())


def run_sync_mock(final_output):
    return patch.object(ca.Runner, "run_sync", return_value=FakeRunResult(final_output))


def ai_outcome(category="Other"):
    return CategorizeOutcome(
        category=category,
        confidence=0.5,
        prediction_source="ai",
        requires_review=True,
    )


quiet_rag = {"category": None, "confidence": 0.0, "source": "none", "matched_merchant": None}
strong_rag = {"category": "Fuel", "confidence": 0.87, "source": "rag", "matched_merchant": "Shell"}


@pytest.fixture(autouse=True)
def _neutralize_determinism():
    """Tools could warn when tooling is missing; keep defaults deterministic."""
    return


class TestOutcomeConstructors:
    def test_rule_outcome_fields(self):
        outcome = ca._rule_outcome("Food")
        assert outcome.category == "Food"
        assert outcome.prediction_source == "rule_engine"
        assert outcome.confidence == 1.0
        assert not outcome.requires_review

    def test_rag_outcome_fields(self):
        outcome = ca._rag_outcome(strong_rag)
        assert outcome.category == "Fuel"
        assert outcome.prediction_source == "rag"
        assert outcome.confidence == 0.87
        assert not outcome.requires_review

    def test_ai_outcome_fields(self):
        outcome = ca._ai_outcome("Transport")
        assert outcome.category == "Transport"
        assert outcome.prediction_source == "ai"
        assert outcome.confidence == 0.5
        assert outcome.requires_review

    def test_ai_outcome_none_category_means_uncategorized(self):
        outcome = ca._ai_outcome(None)
        assert outcome.category == "Uncategorized"
        assert outcome.prediction_source == "ai"

    def test_uncategorized_outcome_fields(self):
        outcome = ca._uncategorized_outcome()
        assert outcome.category == "Uncategorized"
        assert outcome.prediction_source == "uncategorized"
        assert outcome.confidence == 0.0
        assert outcome.requires_review


class TestRunCategorizationGuard:
    @pytest.mark.parametrize("merchant", ["", "   ", "\n\t "])
    def test_empty_merchant_returns_uncategorized_without_building_agent(self, merchant, db):
        with patch.object(ca, "_build_agent") as build:
            outcome = ca.run_categorization(merchant, db)
        assert outcome.prediction_source == "uncategorized"
        assert outcome.requires_review
        build.assert_not_called()


class TestAgentPathOutcomes:
    def test_agent_output_flows_through(self, db):
        """A valid structured agent outcome with no higher-priority match stands."""
        agent_out = CategorizeOutcome(
            category="Transport", confidence=0.5, prediction_source="ai", requires_review=True
        )
        with build_agent_mock(), run_sync_mock(agent_out):
            with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
                 patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
                 patch.object(ca, "_run_rag", return_value=quiet_rag), \
                 patch.object(ca, "predict_category_ai") as ai_mock:
                outcome = ca.run_categorization("UBER", db)
        assert outcome == agent_out
        ai_mock.assert_not_called()

    def test_agent_rule_result_survives_reconcile(self, db):
        """Agent calling rule engine directly still yields a rule_engine outcome."""
        rule_out = ca._rule_outcome("Food")
        with build_agent_mock(), run_sync_mock(rule_out):
            with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
                 patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
                 patch.object(ca, "_run_rag", return_value=None):
                outcome = ca.run_categorization("KFC", db)
        assert outcome.category == "Food"
        assert outcome.prediction_source == "rule_engine"

    def test_agent_error_falls_back_to_legacy(self, db):
        with build_agent_mock(), \
             patch.object(ca.Runner, "run_sync", side_effect=RuntimeError("runner down")), \
             patch.object(ca, "_legacy_pipeline", return_value=ca._rule_outcome("Food")) as legacy:
            outcome = ca.run_categorization("KFC", db)
        assert outcome.category == "Food"
        assert outcome.prediction_source == "rule_engine"
        legacy.assert_called_once()

    def test_missing_api_key_falls_back_to_legacy(self, db):
        with patch.object(ca, "_build_agent", side_effect=RuntimeError("OPENROUTER_API_KEY not configured")), \
             patch.object(ca, "_legacy_pipeline", wraps=ca._legacy_pipeline) as legacy:
            outcome = ca.run_categorization("KFC", db)
        assert outcome.prediction_source == "rule_engine"
        legacy.assert_called_once()

    def test_non_outcome_final_output_falls_back_to_legacy(self, db):
        with build_agent_mock(), run_sync_mock("not-an-outcome"), \
             patch.object(ca, "_legacy_pipeline", return_value=ca._uncategorized_outcome()) as legacy:
            outcome = ca.run_categorization("KFC", db)
        assert outcome.prediction_source == "uncategorized"
        legacy.assert_called_once()

    def test_empty_category_final_output_falls_back_to_legacy(self, db):
        empty = CategorizeOutcome(
            category="", confidence=0.5, prediction_source="ai", requires_review=True
        )
        with build_agent_mock(), run_sync_mock(empty), \
             patch.object(ca, "_legacy_pipeline", return_value=ca._uncategorized_outcome()) as legacy:
            outcome = ca.run_categorization("KFC", db)
        assert outcome.prediction_source == "uncategorized"
        legacy.assert_called_once()


class TestReconcilePriority:
    def test_feedback_beats_rule_rag_and_ai(self, db):
        """Feedback (highest priority) always wins, even if RAG is strong."""
        with build_agent_mock(), run_sync_mock(ai_outcome("Other")):
            with patch.object(ca, "lookup_feedback_category", return_value="Food"), \
                 patch.object(ca, "lookup_rule_category", return_value="Fuel"):
                with patch.object(ca, "_run_rag", return_value=strong_rag) as rag_mock:
                    outcome = ca.run_categorization("KFC", db)
        assert outcome.category == "Food"
        assert outcome.prediction_source == "rule_engine"
        assert not outcome.requires_review

    def test_rule_beats_rag_and_ai(self, db):
        with build_agent_mock(), run_sync_mock(ai_outcome("Other")):
            with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
                 patch.object(ca, "lookup_rule_category", return_value="Fuel"), \
                 patch.object(ca, "_run_rag", return_value=strong_rag):
                outcome = ca.run_categorization("SHELL", db)
        assert outcome.category == "Fuel"
        assert outcome.prediction_source == "rule_engine"

    def test_strong_rag_beats_ai(self, db):
        with build_agent_mock(), run_sync_mock(ai_outcome()):
            with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
                 patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
                 patch.object(ca, "_run_rag", return_value=strong_rag), \
                 patch.object(ca, "predict_category_ai") as ai_mock:
                outcome = ca.run_categorization("SHELL", db)
        assert outcome.category == "Fuel"
        assert outcome.prediction_source == "rag"
        assert not outcome.requires_review
        ai_mock.assert_not_called()

    def test_reconcile_failure_keeps_agent_outcome(self, db):
        """A reconcile exception must not abort categorization."""
        agent_out = ai_outcome("Transport")
        with build_agent_mock(), run_sync_mock(agent_out):
            with patch.object(ca, "lookup_feedback_category", side_effect=RuntimeError("db down")):
                outcome = ca.run_categorization("UBER", db)
        assert outcome == agent_out


class TestLegacyPipeline:
    def test_feedback_wins(self, db):
        with patch.object(ca, "lookup_feedback_category", return_value="Food"):
            outcome = ca._legacy_pipeline("KFC", db)
        assert outcome.prediction_source == "rule_engine"
        assert outcome.category == "Food"

    def test_rule_wins_when_no_feedback(self, db):
        with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
             patch.object(ca, "lookup_rule_category", return_value="Fuel"):
            outcome = ca._legacy_pipeline("SHELL", db)
        assert outcome.prediction_source == "rule_engine"
        assert outcome.category == "Fuel"

    def test_strong_rag_short_circuits_ai(self, db):
        with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
             patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
             patch.object(ca, "_run_rag", return_value=strong_rag), \
             patch.object(ca, "predict_category_ai") as ai_mock:
            outcome = ca._legacy_pipeline("SHELL", db)
        assert outcome.prediction_source == "rag"
        assert outcome.category == "Fuel"
        assert not outcome.requires_review
        ai_mock.assert_not_called()

    def test_weak_rag_passes_context_to_ai(self, db):
        context = [
            {"merchant": "KFC", "category": "Food", "confidence": 0.4, "source": "kb"},
            {"merchant": "Burger King", "category": "Food", "confidence": 0.3, "source": "kb"},
        ]
        weak_rag = {"category": None, "confidence": 0.4, "source": "rag_context", "matched_merchant": "KFC", "context": context}
        with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
             patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
             patch.object(ca, "_run_rag", return_value=weak_rag):
            with patch.object(ca, "predict_category_ai", return_value="Food") as ai_mock:
                outcome = ca._legacy_pipeline("KFC", db)
        assert outcome.prediction_source == "ai"
        assert outcome.category == "Food"
        ai_mock.assert_called_once()
        _, kwargs = ai_mock.call_args
        assert kwargs["context"] == context

    def test_rag_none_calls_ai_without_context(self, db):
        with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
             patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
             patch.object(ca, "_run_rag", return_value=None):
            with patch.object(ca, "predict_category_ai", return_value="Other") as ai_mock:
                outcome = ca._legacy_pipeline("Random Diner", db)
        assert outcome.prediction_source == "ai"
        assert outcome.category == "Other"
        ai_mock.assert_called_once_with("Random Diner", context=None)

    def test_rag_failure_falls_back_to_ai(self, db):
        with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
             patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
             patch.object(ca, "rag_categorize_service", side_effect=RuntimeError("chroma down")):
            with patch.object(ca, "predict_category_ai", return_value="Utilities") as ai_mock:
                outcome = ca._legacy_pipeline("PTCL", db)
        assert outcome.prediction_source == "ai"
        assert outcome.category == "Utilities"
        ai_mock.assert_called_once()

    def test_all_stages_empty_returns_uncategorized_ai(self, db):
        with patch.object(ca, "lookup_feedback_category", return_value="Uncategorized"), \
             patch.object(ca, "lookup_rule_category", return_value="Uncategorized"), \
             patch.object(ca, "_run_rag", return_value=None), \
             patch.object(ca, "predict_category_ai", return_value="Uncategorized"):
            outcome = ca._legacy_pipeline("Corner Shop", db)
        assert outcome.prediction_source == "ai"
        assert outcome.category == "Uncategorized"