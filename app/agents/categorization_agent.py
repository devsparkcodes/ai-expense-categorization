"""Categorization agent orchestrating the existing services.

Thin OpenAI Agents SDK layer over the existing deterministic services.
Priority enforced: Feedback -> Rule Engine -> RAG -> AI.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from agents import Agent, Runner, function_tool
from agents.model_settings import ModelSettings
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from dotenv import load_dotenv
from openai import AsyncOpenAI
from sqlmodel import Session

from app.schemas.agent import CategorizeOutcome
from app.services.ai_categorizer import predict_category_ai
from app.services.categorizer import lookup_feedback_category, lookup_rule_category
from app.services.rag_service import rag_categorize as rag_categorize_service

load_dotenv()

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "expense_categorization.txt"

_PRIORITY_INSTRUCTIONS = """
You must follow this STRICT priority order, stopping at the first stage \
that produces a category:

1. Call lookup_feedback to check prior manual feedback.
   - If it returns a category, classify it directly as a rule_engine result.
2. If feedback returned nothing, call lookup_rule_engine.
   - If it returns a category, classify it as a rule_engine result.
3. If the rule engine returned nothing, call rag_retrieval.
   - If it returns category=None and source='rag_context', pass the context \
to ai_categorize in the next step.
   - If it returns a strong match (source='rag'), classify as a rag result.
   - If it returns nothing (source='none'), continue to the next step.
4. As the last resort, call ai_categorize with the merchant name and any \
RAG context gathered in step 3 (or empty context).
   The final category must be one of the allowed categories from the \
system prompt; use 'Uncategorized' only if the merchant cannot be classified.

After you have a category, output the CategorizeOutcome object with:
- prediction_source one of: rule_engine | rag | ai | uncategorized
- confidence 1.0 for rule_engine, the RAG confidence for rag, 0.5 for ai
- requires_review: False for rule_engine/rag, True for ai
"""


def _load_instructions() -> str:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        base_prompt = f.read()
    return base_prompt + "\n" + _PRIORITY_INSTRUCTIONS


def _uncategorized_outcome() -> CategorizeOutcome:
    return CategorizeOutcome(
        category="Uncategorized",
        confidence=0.0,
        prediction_source="uncategorized",
        requires_review=True,
    )


def _rule_outcome(category: str) -> CategorizeOutcome:
    return CategorizeOutcome(
        category=category,
        confidence=1.0,
        prediction_source="rule_engine",
        requires_review=False,
    )


def _rag_outcome(rag_result: dict) -> CategorizeOutcome:
    return CategorizeOutcome(
        category=rag_result["category"],
        confidence=rag_result["confidence"],
        prediction_source="rag",
        requires_review=False,
    )


def _ai_outcome(category: str) -> CategorizeOutcome:
    return CategorizeOutcome(
        category=category or "Uncategorized",
        confidence=0.5,
        prediction_source="ai",
        requires_review=True,
    )


def _build_tools(db: Session):
    """Create the agent tools, closed over the active session."""

    @function_tool
    def lookup_feedback(merchant_name: str) -> str:
        """Return the manually corrected category for a merchant, or 'Uncategorized'."""
        return lookup_feedback_category(merchant_name, db=db)

    @function_tool
    def lookup_rule_engine(merchant_name: str) -> str:
        """Return the knowledge-base category for a merchant, or 'Uncategorized'."""
        return lookup_rule_category(merchant_name)

    @function_tool
    def rag_retrieval(merchant_name: str) -> dict:
        """Retrieve similar merchants from the RAG knowledge base.

        Returns a dict with keys: category, confidence, source, matched_merchant.
        source is 'none' when nothing matched.
        """
        result = _run_rag(merchant_name, db)
        if not result:
            return {
                "category": None,
                "confidence": 0.0,
                "source": "none",
                "matched_merchant": None,
            }
        return result

    @function_tool
    def ai_categorize(merchant_name: str, context: str = "") -> str:
        """Categorize the merchant with the LLM, optionally using RAG context.

        context should be a JSON string of RAG reference examples, or empty.
        """
        ctx = None
        if context and context.strip():
            try:
                ctx = json.loads(context)
            except (json.JSONDecodeError, TypeError):
                ctx = None
        return predict_category_ai(merchant_name, context=ctx)

    return [lookup_feedback, lookup_rule_engine, rag_retrieval, ai_categorize]


def _build_agent(db: Session) -> Agent:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    model_name = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.7-flash")

    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    client = AsyncOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    return Agent(
        name="categorization_agent",
        instructions=_load_instructions(),
        tools=_build_tools(db),
        model=OpenAIChatCompletionsModel(model=model_name, openai_client=client),
        model_settings=ModelSettings(temperature=0, max_tokens=100),
        output_type=CategorizeOutcome,
    )


def _legacy_pipeline(merchant_name: str, db: Session) -> CategorizeOutcome:
    """Synchronous fallback matching the pre-agent categorization flow."""
    category = lookup_feedback_category(merchant_name, db)
    if category != "Uncategorized":
        return _rule_outcome(category)

    category = lookup_rule_category(merchant_name)
    if category != "Uncategorized":
        return _rule_outcome(category)

    rag_result = _run_rag(merchant_name, db)
    if rag_result and rag_result.get("source") == "rag":
        return _rag_outcome(rag_result)

    context = None
    if rag_result and rag_result.get("source") == "rag_context":
        context = rag_result.get("context")
    return _ai_outcome(predict_category_ai(merchant_name, context=context))


def _reconcile_priority(merchant_name: str, db: Session, outcome: CategorizeOutcome) -> CategorizeOutcome:
    """Deterministic safety: never let a lower-priority stage win.

    Re-checks the cheap, deterministic stages (feedback, rule, RAG strong)
    and overrides the agent outcome if a higher-priority result exists.
    """
    try:
        category = lookup_feedback_category(merchant_name, db)
        if category != "Uncategorized":
            return _rule_outcome(category)

        category = lookup_rule_category(merchant_name)
        if category != "Uncategorized":
            return _rule_outcome(category)

        rag_result = _run_rag(merchant_name, db)
        if rag_result and rag_result.get("source") == "rag":
            return _rag_outcome(rag_result)
    except Exception as exc:  # never let a reconcile failure block the result
        logger.exception("Priority reconciliation failed: %s", exc)

    return outcome


def _run_rag(merchant_name: str, db: Session) -> Optional[dict]:
    """Invoke the RAG service with defensive logging."""
    try:
        return rag_categorize_service(merchant_name, db=db)
    except Exception as exc:
        logger.exception("RAG service invocation failed: %s", exc)
        return None


def run_categorization(merchant_name: str, db: Session) -> CategorizeOutcome:
    """Run the categorization agent and return a structured outcome.

    Falls back to the synchronous legacy pipeline if the Agent SDK fails.
    """
    if not merchant_name or not merchant_name.strip():
        return _uncategorized_outcome()

    try:
        agent = _build_agent(db)
        result = Runner.run_sync(starting_agent=agent, input=f"Categorize merchant: {merchant_name}")
        raw_output = result.final_output
        if not isinstance(raw_output, CategorizeOutcome) or not raw_output.category:
            logger.warning("Agent returned no usable outcome: %r", raw_output)
            return _legacy_pipeline(merchant_name, db)
        return _reconcile_priority(merchant_name, db, raw_output)
    except Exception as exc:
        logger.exception("Categorization agent failed (%s); using legacy pipeline", exc)
        return _legacy_pipeline(merchant_name, db)