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


def clean_invalid_json(s: str) -> str:
    """
    Sanitizes JSON strings by escaping raw newlines, carriage returns,
    and tabs inside string literals.
    """
    result = []
    in_str = False
    escaped = False
    for char in s:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == '\\':
            result.append(char)
            escaped = True
            continue
        if char == '"':
            in_str = not in_str
            result.append(char)
            continue
        if in_str:
            if char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            else:
                result.append(char)
        else:
            result.append(char)
    return "".join(result)


def robust_extract_fields(text: str, keys: list[str]) -> dict[str, str]:
    import re
    positions = []
    for key in keys:
        match = re.search(r'"' + re.escape(key) + r'"\s*:', text)
        if not match:
            match = re.search(r"'" + re.escape(key) + r"'\s*:", text)
        if match:
            positions.append((key, match.start()))
            
    positions.sort(key=lambda x: x[1])
    
    extracted = {}
    for i, (key, pos) in enumerate(positions):
        colon_pos = text.find(':', pos)
        if colon_pos == -1:
            continue
        
        quote_char = None
        val_start = -1
        for j in range(colon_pos + 1, len(text)):
            if text[j] in ('"', "'"):
                quote_char = text[j]
                val_start = j + 1
                break
        
        if val_start == -1:
            continue
        
        if i + 1 < len(positions):
            val_end_limit = positions[i+1][1]
        else:
            val_end_limit = text.rfind('}')
            if val_end_limit == -1 or val_end_limit < val_start:
                val_end_limit = len(text)
        
        val_cand = text[val_start:val_end_limit]
        val_end = val_cand.rfind(quote_char) if quote_char else -1
        if val_end != -1:
            val_str = val_cand[:val_end]
        else:
            val_str = val_cand
            
        val_str = val_str.strip()
        val_str = val_str.replace('\\"', '"')
        val_str = val_str.replace('\\\\', '\\')
        val_str = val_str.replace('\\n', '\n')
        val_str = val_str.replace('\\t', '\t')
        val_str = val_str.replace('\\r', '\r')
        
        extracted[key] = val_str
        
    return extracted


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
            # 1. Clean control characters and attempt standard parsing
            cleaned = clean_invalid_json(candidate)
            data = json.loads(cleaned)
            return model.model_validate(data)
        except Exception as exc:
            last_error = exc

    # 2. Hard regex parsing fallbacks for critical graph states
    # This prevents the execution pipeline from crashing due to minor model quote-escaping errors
    try:
        cand_str = candidates[-1] if candidates else text
        if model.__name__ == "ResearchPlan":
            import re
            goal_match = re.search(r'"goal"\s*:\s*"([^"]+)"', cand_str)
            goal = goal_match.group(1) if goal_match else ""
            
            tasks_match = re.search(r'"tasks"\s*:\s*\[(.*?)\]', cand_str, re.DOTALL)
            tasks = []
            if tasks_match:
                tasks_content = tasks_match.group(1)
                for task_str in re.findall(r'"([^"]*?)"', tasks_content):
                    if task_str.strip():
                        tasks.append(task_str)
            if tasks:
                return model(goal=goal, tasks=tasks)
                
        elif model.__name__ == "SubQueries":
            import re
            queries_match = re.search(r'"queries"\s*:\s*\[(.*?)\]', cand_str, re.DOTALL)
            queries = []
            if queries_match:
                queries_content = queries_match.group(1)
                for q_str in re.findall(r'"([^"]*?)"', queries_content):
                    if q_str.strip():
                        queries.append(q_str)
            if queries:
                return model(queries=queries)

        elif model.__name__ == "CriticDecision":
            # Extract decision, feedback, suggested_search_task robustly
            extracted = robust_extract_fields(cand_str, ["decision", "feedback", "suggested_search_task"])
            decision = extracted.get("decision", "REVISE").strip().upper()
            feedback = extracted.get("feedback", "").strip()
            suggested_search_task = extracted.get("suggested_search_task", "").strip()
            
            # Additional fallback checks for decision format
            if decision not in {"PASS", "REVISE", "RESEARCH"}:
                decision = "REVISE"
                
            return model(decision=decision, feedback=feedback, suggested_search_task=suggested_search_task)

        elif model.__name__ == "SectionOutput":
            extracted = robust_extract_fields(cand_str, ["content", "summary"])
            content = extracted.get("content", "").strip()
            summary = extracted.get("summary", "").strip()
            return model(content=content, summary=summary)

        elif model.__name__ == "RevisionPlan":
            extracted = robust_extract_fields(cand_str, ["reasoning"])
            reasoning = extracted.get("reasoning", "").strip()
            
            import re
            sec_match = re.search(r'"sections_to_revise"\s*:\s*\[(.*?)\]', cand_str, re.DOTALL)
            sections_to_revise = []
            if sec_match:
                content_str = sec_match.group(1)
                for item in re.findall(r'"([^"]*?)"', content_str):
                    if item.strip():
                        sections_to_revise.append(item.strip())
            return model(sections_to_revise=sections_to_revise, reasoning=reasoning)
    except Exception as parse_err:
        pass

    raise ValueError(f"Could not parse model response as {model.__name__}: {last_error}")
