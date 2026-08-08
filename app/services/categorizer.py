import json
import re
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.models.category_feedback import CategoryFeedback

_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "merchant_categories.json"


def _load_knowledge_base() -> dict:
    with open(_KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_merchant_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[.,\-_()\[\]{}'\"']", "", name)
    return name


def lookup_feedback_category(
    merchant_name: str, db: Optional[Session] = None
) -> str:
    """Look up a category from CategoryFeedback (exact normalized match)."""
    if db is None:
        return "Uncategorized"
    merchant_normalized = normalize_merchant_name(merchant_name)
    feedback_records = db.exec(select(CategoryFeedback)).all()
    for fb in feedback_records:
        if normalize_merchant_name(fb.merchant_name) == merchant_normalized:
            return fb.corrected_category
    return "Uncategorized"


def lookup_rule_category(merchant_name: str) -> str:
    """Look up a category from the merchant knowledge base (substring match)."""
    kb = _load_knowledge_base()
    merchant = normalize_merchant_name(merchant_name)
    for category, merchants in kb.items():
        normalized_merchants = [normalize_merchant_name(m) for m in merchants]
        if merchant in normalized_merchants:
            return category
        for nm in normalized_merchants:
            if nm in merchant or merchant in nm:
                return category
    return "Uncategorized"


def predict_category(merchant_name: str, db: Optional[Session] = None) -> str:
    """Categorize a merchant by feedback lookup, then the knowledge base."""
    category = lookup_feedback_category(merchant_name, db)
    if category != "Uncategorized":
        return category
    return lookup_rule_category(merchant_name)
