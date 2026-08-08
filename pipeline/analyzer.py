"""Run Claude news analyst and return structured output."""

import json
import os
import re
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from agents.news_analyst.agent import MODEL, SYSTEM_INSTRUCTION
from agents.news_analyst.prompts import (
    ARTICLE_FOCUS_PAGE_LINE,
    ARTICLE_FOCUS_TEMPLATE,
    JSON_OUTPUT_INSTRUCTION,
    PREFILTERED_NOTE,
    USER_PROMPT_TEMPLATE,
)
from pipeline.schemas import ExamNotesReport

EXAM_FOCUS_LABELS = {
    "UPSC Prelims": "UPSC Civil Services Preliminary Examination",
    "UPSC Mains GS": "UPSC Civil Services Mains General Studies",
    "State PCS": "State Public Service Commission examinations",
    "SSC": "Staff Selection Commission exams",
    "Banking": "IBPS / SBI / RBI banking exams",
    "CDS / CAPF": "CDS and CAPF examinations",
    "Judiciary": "Judicial Services examinations",
}

MAX_OUTPUT_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "32000"))
MAX_PARSE_ATTEMPTS = 2


def _build_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your Anthropic API key."
        )
    # Long educational packs need extended timeout; streaming avoids the 10-min non-stream limit.
    timeout_s = float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "1200"))
    return Anthropic(api_key=api_key, timeout=timeout_s)


def _stream_message_text(
    client: Anthropic,
    *,
    system: str,
    messages: list[dict[str, str]],
) -> str:
    """Call Claude with streaming (required for large max_tokens / long runs)."""
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system,
        messages=messages,
    ) as stream:
        message = stream.get_final_message()
    return _response_text(message)


def _build_article_focus_block(
    article_selector: str | None,
    page_number: int | None = None,
) -> str:
    selector = (article_selector or "").strip()
    if not selector:
        return ""

    page_line = ""
    if page_number and page_number > 0:
        page_line = ARTICLE_FOCUS_PAGE_LINE.format(page_number=page_number)

    return ARTICLE_FOCUS_TEMPLATE.format(article_selector=selector, page_line=page_line)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _find_json_object(text: str) -> str | None:
    """Extract the outermost JSON object using brace balancing."""
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _repair_json_text(raw: str) -> str:
    """Apply light repairs for common LLM JSON mistakes."""
    text = raw.replace("\ufeff", "")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text


def _extract_json_payload(text: str) -> dict[str, Any]:
    """Parse JSON from model text, tolerating fences, preamble, or minor errors."""
    candidates: list[str] = []

    stripped = _strip_code_fences(text)
    candidates.append(stripped)

    found = _find_json_object(stripped)
    if found:
        candidates.append(found)

    if not stripped.startswith("{"):
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if match:
            candidates.append(match.group(0))

    seen: set[str] = set()
    errors: list[str] = []

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)

        for variant in (candidate, _repair_json_text(candidate)):
            try:
                return json.loads(variant)
            except json.JSONDecodeError as exc:
                errors.append(str(exc))

    raise json.JSONDecodeError("No valid JSON object found", text[:200], 0)


def _response_text(response) -> str:
    chunks = []
    for block in response.content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            chunks.append(block.text)
    return "".join(chunks).strip()


def _parse_with_structured_output(client: Anthropic, system: str, prompt: str) -> ExamNotesReport | None:
    """Try Anthropic structured output first (skip if it would hit long-request limits)."""
    # Large educational packs almost always exceed the non-streaming 10-minute estimate.
    if MAX_OUTPUT_TOKENS > 8192:
        return None
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=ExamNotesReport,
        )
        if response.parsed_output is not None:
            return response.parsed_output
    except Exception:
        return None
    return None


def _fallback_from_markdown(text: str, exam_focus: str) -> ExamNotesReport:
    """Build a minimal report when JSON parsing fails but markdown content exists."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0][:200] if lines else "Examination Notes"

    for line in lines[:20]:
        if line.startswith("#"):
            title = line.lstrip("#").strip()[:200]
            break

    narration = ""
    if "## 18" in text or "# 18" in text:
        parts = re.split(r"#+\s*18[\.\)]\s*Final Takeaway", text, flags=re.I)
        if len(parts) > 1:
            narration = parts[-1][:6000].strip()

    if not narration:
        narration = text[:5000]

    return ExamNotesReport(
        title=title,
        exam_focus=exam_focus,
        exam_one_liner=title[:240],
        executive_summary=lines[1:6] if len(lines) > 1 else [],
        full_report_markdown=text,
        narration_script=narration[:8000],
    )


def _parse_response_text(final_text: str, exam_focus: str) -> ExamNotesReport:
    try:
        payload = _extract_json_payload(final_text)
        return ExamNotesReport.model_validate(payload)
    except (json.JSONDecodeError, ValidationError):
        if len(final_text) > 400 and ("# " in final_text or "## " in final_text):
            return _fallback_from_markdown(final_text, exam_focus)
        raise


def analyze_news(
    news_text: str,
    exam_focus: str,
    *,
    article_selector: str | None = None,
    page_number: int | None = None,
    pre_filtered: bool = False,
) -> ExamNotesReport:
    """Analyze news text using Claude; parse JSON response into ExamNotesReport."""
    exam_label = EXAM_FOCUS_LABELS.get(exam_focus, exam_focus)

    if pre_filtered:
        article_focus_block = PREFILTERED_NOTE.format(
            article_selector=article_selector or "Selected article"
        )
    else:
        article_focus_block = _build_article_focus_block(article_selector, page_number)

    prompt = USER_PROMPT_TEMPLATE.format(
        exam_focus=exam_label,
        article_focus_block=article_focus_block,
        article_text=news_text,
    )

    system = SYSTEM_INSTRUCTION + "\n\n" + JSON_OUTPUT_INSTRUCTION
    client = _build_client()

    # Attempt 1: structured output API
    parsed = _parse_with_structured_output(client, system, prompt)
    if parsed is not None:
        return parsed.model_copy(update={"exam_focus": exam_focus})

    last_error: Exception | None = None
    messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

    for attempt in range(MAX_PARSE_ATTEMPTS):
        try:
            final_text = _stream_message_text(client, system=system, messages=messages)
        except Exception as exc:
            raise RuntimeError(_friendly_api_error(exc)) from exc

        if not final_text:
            raise RuntimeError("Claude returned an empty response. Try again or shorten the input.")

        try:
            analysis = _parse_response_text(final_text, exam_focus)
            return analysis.model_copy(update={"exam_focus": exam_focus})
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": final_text[:12000]},
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was not valid JSON. "
                        "Return ONLY one valid JSON object matching the required schema. "
                        "No markdown fences, no commentary. Escape quotes and newlines inside strings."
                    ),
                },
            ]

    raise RuntimeError(
        "Claude returned a response that could not be parsed as JSON after retries. "
        "Try running analysis again or shorten the article text."
    ) from last_error


def _friendly_api_error(exc: Exception) -> str:
    msg = str(exc)
    if "not_found_error" in msg and "model:" in msg:
        return (
            f"Model not found ({MODEL}). "
            "Set ANTHROPIC_MODEL in .env to a current model such as "
            "'claude-sonnet-5' or 'claude-sonnet-4-6'. "
            f"Original error: {msg}"
        )
    if "Schema is too complex" in msg or "schema is too complex" in msg.lower():
        return (
            "Structured output schema rejected by API; retrying with text JSON mode failed. "
            f"Original error: {msg}"
        )
    if "Streaming is required" in msg or "stream=True" in msg:
        return (
            "Claude long-request needs streaming. This app now uses streaming automatically — "
            "restart Streamlit and run Analyze again. "
            f"Original error: {msg}"
        )
    return msg
