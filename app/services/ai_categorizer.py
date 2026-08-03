import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "expense_categorization.txt"

_ALLOWED_CATEGORIES = {
    "Food",
    "Fuel",
    "Transport",
    "Entertainment",
    "Shopping",
    "Healthcare",
    "Education",
    "Bills",
    "Office",
    "Maintenance",
    "Other",
    "Utilities",
}


def _load_system_prompt() -> str:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def predict_category_ai(merchant_name: str) -> str:
    """
    Categorize a merchant using an LLM via OpenRouter.
    Returns one of the allowed categories, or 'Other' on failure.
    Returns 'Uncategorized' if the API key is missing.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "Uncategorized"

    model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.7-flash")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    system_prompt = _load_system_prompt()
    user_message = f"{system_prompt}\nMerchant: {merchant_name}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=100,
            temperature=0,
        )

        content = response.choices[0].message.content
        if content is None:
            logging.warning("AI returned no content for merchant '%s': %r", merchant_name, response)
            return "Uncategorized"

        result = content.strip()
        if result in _ALLOWED_CATEGORIES:
            return result
        for cat in _ALLOWED_CATEGORIES:
            if cat.lower() == result.lower():
                return cat
        return "Other"
    except Exception as exc:
        logging.exception("AI categorization failed for merchant '%s': %s", merchant_name, exc)
        return "Uncategorized"
