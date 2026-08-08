"""Clean OCR / extracted newspaper text into readable article TXT."""

from __future__ import annotations

import re

from pipeline.pdf_extract import count_real_words, readable_ratio

# Common newspaper chrome to strip from article bodies.
_CHROME_LINE_RE = re.compile(
    r"^(?:@+\s*)?(?:WEB EXCLUSIVE|WORDLY WISE|FOUNDED BY|Log on to|www\.|"
    r"epaper\.|THE INDIAN\s*EXPRESS|The Editorial Page|BECAUSE THE TRUTH|"
    r"INVOLVES US ALL|RAMNATH GOENK|GOENK\s*$|"
    r"\d{1,2}\s+(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),?\s+"
    r"[A-Z]+\s+\d{1,2},?\s+\d{4}.*)$",
    re.I,
)
_BYLINE_RE = re.compile(r"^By\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,4})\s*$", re.I)
_HYPHEN_BREAK_RE = re.compile(r"([A-Za-z])-\s*\n\s*([A-Za-z])")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_OCR_QUOTE_RE = re.compile(r"[“”„]|�")
_OCR_APOS_RE = re.compile(r"[‘’‚]|�")


def slugify_title(title: str, *, max_len: int = 60) -> str:
    """Filesystem-safe slug from a headline."""
    cleaned = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    cleaned = re.sub(r"[-\s]+", "_", cleaned.strip())
    cleaned = cleaned.strip("_") or "article"
    return cleaned[:max_len].rstrip("_")


def clean_ocr_text(text: str) -> str:
    """Make OCR text closer to the printed article (readable paragraphs)."""
    if not text or not text.strip():
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _OCR_QUOTE_RE.sub('"', text)
    text = _OCR_APOS_RE.sub("'", text)
    text = text.replace("—", "—").replace("–", "-")
    text = text.replace("�", "'")

    # Join hyphenated line-breaks: "compen-\nsating" → "compensating"
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)

    lines: list[str] = []
    for raw in text.splitlines():
        line = _MULTI_SPACE_RE.sub(" ", raw).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _CHROME_LINE_RE.match(line):
            continue
        if readable_ratio(line) < 0.28 and count_real_words(line) == 0:
            continue
        lines.append(line)

    # Merge soft-wrapped body lines into paragraphs (newspaper columns wrap mid-sentence).
    paragraphs: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        paragraphs.append(" ".join(buf).strip())
        buf.clear()

    for idx, line in enumerate(lines):
        if not line:
            flush()
            continue
        # Keep bylines as their own blocks
        if _BYLINE_RE.match(line):
            flush()
            paragraphs.append(line)
            continue
        # Keep a short headline block only at the very top
        if (
            idx < 3
            and not buf
            and not paragraphs
            and len(line) < 90
            and not line.endswith((".", "?", "!", ",", ";"))
            and line[0].isupper()
            and len(line.split()) <= 12
        ):
            paragraphs.append(line)
            continue
        # Continue paragraph if previous line doesn't end sentence
        if buf and not buf[-1].endswith((".", "?", "!", ":", '"', "'")):
            buf.append(line)
        elif buf and line and line[0].islower():
            buf.append(line)
        else:
            if buf and buf[-1].endswith((".", "?", "!", '"', "'")):
                flush()
            buf.append(line)
    flush()

    cleaned = "\n\n".join(p for p in paragraphs if p.strip())
    cleaned = _MULTI_NL_RE.sub("\n\n", cleaned).strip()
    # Fix common OCR glitches at word starts after join
    cleaned = re.sub(r"\bonblanket\b", "on blanket", cleaned, flags=re.I)
    cleaned = re.sub(r"\bItis\b", "It is", cleaned)
    cleaned = re.sub(r"\bNDIA'S\b", "INDIA'S", cleaned)
    cleaned = re.sub(r"\bARLIAMENT\b", "PARLIAMENT", cleaned)
    cleaned = re.sub(r"\bJINKYA\b", "AJINKYA", cleaned)
    cleaned = re.sub(r"\bTheworker-intellectual\b", "The worker-intellectual", cleaned, flags=re.I)
    cleaned = re.sub(r"\bTheworker\b", "The worker", cleaned, flags=re.I)
    cleaned = re.sub(r"\bAttimes\b", "At times", cleaned)
    cleaned = re.sub(r"\bAcall\b", "A call", cleaned, flags=re.I)
    cleaned = re.sub(r"\bdrillsfor\b", "drills for", cleaned, flags=re.I)
    cleaned = re.sub(r"\bwd control\b", "word control", cleaned, flags=re.I)
    cleaned = re.sub(r"\bHE JANTAR\b", "THE JANTAR", cleaned)
    cleaned = re.sub(r"\bEREVER\b", "WHEREVER", cleaned)
    cleaned = re.sub(r"\bOPULAR\b", "POPULAR", cleaned)
    return cleaned


def format_article_txt(
    *,
    title: str,
    body: str,
    page: int,
    source_pdf: str,
    article_index: int,
) -> str:
    """Format one article as clean TXT ready for LLM input."""
    body_clean = clean_ocr_text(body)
    title_clean = clean_ocr_text(title).splitlines()[0].strip() if title else "Article"
    title_clean = re.sub(r"\s+", " ", title_clean)[:140]

    # Prefer title from body first line if body starts with a better headline
    first = body_clean.splitlines()[0].strip() if body_clean else ""
    if first and len(first) >= 12 and len(first) <= 140 and count_real_words(first) >= 3:
        if count_real_words(title_clean) < 3 or title_clean.lower() in {"article", "article excerpt"}:
            title_clean = first

    body_clean = _strip_leading_headline_echo(body_clean, title_clean)

    byline = ""
    body_lines = body_clean.splitlines()
    if body_lines and _BYLINE_RE.match(body_lines[0].strip()):
        byline = body_lines[0].strip()
        body_clean = "\n".join(body_lines[1:]).lstrip()

    parts = [
        f"Title: {title_clean}",
        f"Page: {page}",
        f"Article: {article_index}",
        f"Source: {source_pdf}",
        "",
        "---",
        "",
        title_clean,
    ]
    if byline:
        parts.extend(["", byline])
    parts.extend(["", body_clean.strip(), ""])
    return "\n".join(parts)


def _strip_leading_headline_echo(body: str, title: str) -> str:
    """Remove headline fragments repeated at the start of the body."""
    if not body or not title:
        return body
    title_norm = re.sub(r"\s+", " ", title).strip().lower()
    title_tokens = set(re.findall(r"[a-z0-9']{3,}", title_norm))
    lines = body.splitlines()
    i = 0
    while i < min(4, len(lines)):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        line_norm = re.sub(r"\s+", " ", line).lower()
        if line_norm == title_norm:
            i += 1
            continue
        # Partial headline half (e.g. "SC strikes balance on")
        line_tokens = set(re.findall(r"[a-z0-9']{3,}", line_norm))
        if (
            line_tokens
            and title_tokens
            and len(line.split()) <= 12
            and not line.endswith((".", "?", "!"))
            and len(line_tokens & title_tokens) / len(line_tokens) >= 0.7
        ):
            i += 1
            continue
        break

    rest = "\n".join(lines[i:]).lstrip()
    if not rest:
        return rest

    # Peel headline words glued onto the first paragraph:
    # "ecology, public interest INDIA'S ENVIRONMENTAL..." → "INDIA'S ENVIRONMENTAL..."
    first_para, *more = rest.split("\n\n", 1)
    words = first_para.split()
    stop = {"a", "an", "the", "of", "in", "on", "to", "and", "or", "for", "is", "are"}
    peel = 0
    matched = 0
    for w in words[:14]:
        token = re.sub(r"[^a-z0-9']", "", w.lower())
        if not token or token in stop:
            if matched:
                peel += 1
                continue
            break
        if token in title_tokens:
            peel += 1
            matched += 1
            continue
        # Hit real body word
        break
    if matched >= 2 and peel < len(words):
        first_para = " ".join(words[peel:]).lstrip(" ,|-")
    if more:
        return (first_para + "\n\n" + more[0]).strip()
    return first_para.strip()


def extract_title_from_txt(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("Title:"):
            return line[6:].strip()
    return "Article"


def extract_body_from_txt(content: str) -> str:
    """Return the article body after the --- separator (for LLM)."""
    if "\n---\n" in content:
        body = content.split("\n---\n", 1)[1].strip()
    else:
        body = content.strip()
    return body
