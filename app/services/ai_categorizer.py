import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

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


def predict_category_ai(merchant_name: str) -> str:
    """
    Categorize a merchant using an LLM via OpenRouter.
    Returns one of the allowed categories, or 'Other' on failure.
    Returns 'Uncategorized' if the API key is missing.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "Uncategorized"

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    prompt = (
        "Categorize the following merchant into exactly ONE of these categories: "
        "Food, Fuel, Transport, Entertainment, Shopping, Utilities, Healthcare, "
        "Education, Bills, Office, Maintenance, Other.\n\n"
        f"Merchant: {merchant_name}\n\n"
        "Return ONLY the category name, nothing else."
    )

    response = client.chat.completions.create(
        model="qwen/qwen3.7-flash",
        messages=[{"role": "user", "content": prompt}],
    )

    result = response.choices[0].message.content.strip()
    if result in _ALLOWED_CATEGORIES:
        return result
    for cat in _ALLOWED_CATEGORIES:
        if cat.lower() == result.lower():
            return cat
    return "Other"
