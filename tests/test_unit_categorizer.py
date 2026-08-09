"""Unit tests for the merchant categorization logic.

No LLM/API calls and no Chroma usage: these tests exercise only
app/services/categorizer.py against the in-memory pytest database.
"""

import pytest

from app.models.category_feedback import CategoryFeedback
from app.services.categorizer import (
    lookup_feedback_category,
    lookup_rule_category,
    normalize_merchant_name,
    predict_category,
)


class TestNormalizeMerchantName:
    def test_lowercases_and_strips(self):
        assert normalize_merchant_name("  KFC  ") == "kfc"

    def test_removes_punctuation(self):
        assert normalize_merchant_name("Domino's Pizza") == "dominos pizza"
        assert normalize_merchant_name("K-Electric") == "kelectric"
        assert normalize_merchant_name("Total.Parco") == "totalparco"

    def test_collapses_whitespace(self):
        assert normalize_merchant_name("Burger    King") == "burger king"
        assert normalize_merchant_name("  Sui   Southern Gas  ") == "sui southern gas"

    def test_equivalent_merchants_normalize_consistently(self):
        assert normalize_merchant_name("McDonald's") == normalize_merchant_name("mcdonalds")
        assert normalize_merchant_name("Domino's Pizza") == normalize_merchant_name("dominos pizza")
        assert normalize_merchant_name("pizza hut") == normalize_merchant_name("PIZZA HUT")


class TestLookupFeedbackCategory:
    def test_matching_feedback_returns_corrected_category(self, db):
        feedback = CategoryFeedback(
            merchant_name="Uber",
            original_category="Transport",
            corrected_category="Food",
        )
        db.add(feedback)
        db.commit()
        assert lookup_feedback_category("UBER", db) == "Food"

    def test_unknown_merchant_returns_uncategorized(self, db):
        assert lookup_feedback_category("No Such Place", db) == "Uncategorized"

    def test_normalized_matching_works(self, db):
        feedback = CategoryFeedback(
            merchant_name="Domino's Pizza",
            original_category="Food",
            corrected_category="Entertainment",
        )
        db.add(feedback)
        db.commit()
        assert lookup_feedback_category("dominos pizza", db) == "Entertainment"

    def test_no_db_returns_uncategorized(self):
        assert lookup_feedback_category("Uber") == "Uncategorized"


class TestLookupRuleCategory:
    def test_known_merchant_returns_category(self):
        assert lookup_rule_category("KFC") == "Food"
        assert lookup_rule_category("Shell") == "Fuel"

    def test_case_and_spacing_insensitive(self):
        assert lookup_rule_category("  SPOTIFY  ") == "Entertainment"
        assert lookup_rule_category("pizza hut") == "Food"

    def test_substring_matches(self):
        assert lookup_rule_category("KFC Downtown") == "Food"
        assert lookup_rule_category("Restaurant Burger King 5th Ave") == "Food"
        assert lookup_rule_category("Shell Petrol Station") == "Fuel"

    def test_unknown_merchant_returns_uncategorized(self):
        assert lookup_rule_category("Random Diner") == "Uncategorized"


class TestPredictCategory:
    def test_feedback_priority_over_rule(self, db):
        feedback = CategoryFeedback(
            merchant_name="KFC",
            original_category="Food",
            corrected_category="Entertainment",
        )
        db.add(feedback)
        db.commit()
        assert predict_category("KFC", db) == "Entertainment"

    def test_rule_engine_used_when_feedback_does_not_match(self, db):
        feedback = CategoryFeedback(
            merchant_name="Arrive",
            original_category="Other",
            corrected_category="Other",
        )
        db.add(feedback)
        db.commit()
        assert predict_category("Netflix", db) == "Entertainment"

    def test_returns_uncategorized_when_neither_matches(self, db):
        assert predict_category("Unknown Merchant 123", db) == "Uncategorized"