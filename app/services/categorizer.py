import json
import re
from pathlib import Path

_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "merchant_categories.json"


def _load_knowledge_base() -> dict:
    with open(_KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_merchant_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[.,\-_()\[\]{}'\"']", "", name)
    return name


def predict_category(merchant_name: str) -> str:
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
