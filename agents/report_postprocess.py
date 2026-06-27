import re
from typing import Iterable


INLINE_CITATION_RE = re.compile(r"\s*\[\d+(?:,\s*\d+)*\]")
URL_RE = re.compile(r"https?://[^\s\)\]\}>\"']+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
REFERENCE_HEADING_RE = re.compile(
    r"^(#{1,6})\s*(references|sources|source list|bibliography|works cited)\b.*$",
    re.IGNORECASE,
)
REFERENCE_LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?(references|sources|source list|bibliography|works cited)(?:\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
SOURCE_LINE_RE = re.compile(
    r"^\s*(?:[-*]|\d+[.)])?\s*(?:\[\d+\]\s*)?(?:https?://|\[[^\]]+\]\(https?://)",
    re.IGNORECASE,
)


def _clean_url(url: str) -> str:
    return url.strip().rstrip(".,;:)]}>")


def collect_urls(markdown: str, sources: Iterable[str] | None = None) -> list[str]:
    urls: list[str] = []
    seen = set()

    for source in sources or []:
        source = _clean_url(str(source))
        if source and source not in seen:
            seen.add(source)
            urls.append(source)

    for match in URL_RE.findall(markdown or ""):
        url = _clean_url(match)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)

    return urls


def strip_reference_sections(markdown: str) -> str:
    kept_lines: list[str] = []
    skipping = False
    skip_level = 7

    for line in (markdown or "").splitlines():
        heading_match = re.match(r"^(#{1,6})\s+", line)
        reference_heading = REFERENCE_HEADING_RE.match(line)

        if reference_heading:
            skipping = True
            skip_level = len(reference_heading.group(1))
            continue

        if skipping and heading_match and len(heading_match.group(1)) <= skip_level:
            skipping = False

        if skipping:
            continue

        if REFERENCE_LABEL_RE.match(line) or SOURCE_LINE_RE.match(line):
            continue

        kept_lines.append(line)

    return "\n".join(kept_lines)


def normalize_report_markdown(
    markdown: str,
    sources: Iterable[str] | None = None,
    max_sources: int = 8,
    include_references: bool = True,
) -> tuple[str, list[str]]:
    """Remove inline citations and keep source links only in one final block."""
    urls = collect_urls(markdown, sources)

    cleaned = strip_reference_sections(markdown or "")
    cleaned = MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = URL_RE.sub("", cleaned)
    cleaned = INLINE_CITATION_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    references = urls[:max_sources]
    if include_references and references:
        cleaned = f"{cleaned}\n\n### References\n\n"
        cleaned += "\n".join(f"- [{url}]({url})" for url in references)

    return cleaned, references
