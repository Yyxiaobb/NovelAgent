import json


def json_candidate(raw: str):
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(candidate)


def text_value(value) -> str:
    if isinstance(value, list):
        return "；".join(str(item) for item in value)
    if isinstance(value, dict):
        return "；".join(f"{key}：{item}" for key, item in value.items())
    return str(value)


def outline_max_tokens(expected_words: int) -> int:
    # A full-book outline stays concise regardless of novel length; the target
    # novel word count informs scope, not the size of the outline itself.
    return 5000


def plan_max_tokens(expected_words: int) -> int:
    return max(900, min(7000, round(expected_words * 0.65)))


def memory_max_tokens(content: str) -> int:
    return max(2200, min(8000, round(len(content) * 0.2)))


def content_max_tokens(expected_words: int) -> int:
    return max(1400, min(24000, round(expected_words * 1.35)))
