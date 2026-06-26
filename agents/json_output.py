import json
from typing import Type, TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)


def message_to_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def _extract_fenced_json(text: str) -> str | None:
    marker = "```"
    start = text.find(marker)
    while start != -1:
        content_start = text.find("\n", start + len(marker))
        if content_start == -1:
            return None
        end = text.find(marker, content_start + 1)
        if end == -1:
            return None
        candidate = text[content_start + 1:end].strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
        start = text.find(marker, end + len(marker))
    return None


def _extract_balanced_json(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    raise ValueError("No complete JSON object found in model response.")


def parse_json_model(message, model: Type[ModelT]) -> ModelT:
    text = message_to_text(message).strip()
    candidates = [text]

    fenced = _extract_fenced_json(text)
    if fenced:
        candidates.append(fenced)

    try:
        candidates.append(_extract_balanced_json(text))
    except ValueError:
        pass

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            return model.model_validate(data)
        except Exception as exc:
            last_error = exc

    raise ValueError(f"Could not parse model response as {model.__name__}: {last_error}")
