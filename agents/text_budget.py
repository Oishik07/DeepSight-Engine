def compact_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    head_chars = max_chars * 2 // 3
    tail_chars = max_chars - head_chars
    return (
        text[:head_chars].rstrip()
        + "\n\n[...middle content omitted to stay within model token limits...]\n\n"
        + text[-tail_chars:].lstrip()
    )


def final_stage_char_budget(provider: str, model: str) -> int:
    provider = (provider or "").lower()
    model = (model or "").lower()

    if provider == "groq":
        if "8b" in model or "instant" in model:
            return 5000
        return 15000

    return 30000
