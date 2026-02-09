import json
import re

def extract_json(text: str) -> dict:
    """
    Safely extract JSON object from AI response text.
    Returns a dict or raises ValueError if impossible.
    """

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract JSON using regex
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in AI response")

    json_text = match.group()

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError("Extracted JSON is invalid") from e
def calculate_ats_score(data: dict) -> int:
    keyword = data.get("keyword_match_score", 0)
    formatting = data.get("formatting_score", 0)
    language = data.get("language_score", 0)

    # Weighted average (industry-like)
    ats_score = (
        0.5 * keyword +
        0.3 * formatting +
        0.2 * language
    )

    return round(ats_score)
