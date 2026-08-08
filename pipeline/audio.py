"""Audio generation helpers for narration scripts."""

from __future__ import annotations

import re
from pathlib import Path


def clean_script_for_tts(text: str) -> str:
    """
    Remove markdown / symbols so TTS does not speak slashes, asterisks, labels, etc.
    Keeps Devanagari and basic punctuation suitable for Hindi speech.
    """
    if not text:
        return ""

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")

    # Drop common section labels if model leaked them
    cleaned = re.sub(
        r"(?im)^\s*(?:title|hook|introduction|background|current news|static knowledge|"
        r"exam importance|revision|ending|subscribe cta|part\s*\d+|स्लाइड\s*\d+)\s*[:\-–—]\s*",
        "",
        cleaned,
    )

    # Remove markdown and URL noise
    cleaned = re.sub(r"```[\s\S]*?```", " ", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"[#*_~>]", " ", cleaned)

    # Strip bullets / numbering at line starts
    cleaned = re.sub(r"(?m)^\s*[-•●▪◦]\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*\d+[\).]\s*", "", cleaned)

    # Characters TTS often misreads aloud
    cleaned = cleaned.replace("/", " ")
    cleaned = cleaned.replace("\\", " ")
    cleaned = cleaned.replace("|", " ")
    cleaned = cleaned.replace("_", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = cleaned.replace("[", " ").replace("]", " ")
    cleaned = cleaned.replace("<", " ").replace(">", " ")
    cleaned = cleaned.replace("&", " और ")
    cleaned = cleaned.replace("@", " ")
    cleaned = cleaned.replace("#", " ")
    cleaned = cleaned.replace("*", " ")
    cleaned = cleaned.replace("=", " ")
    cleaned = cleaned.replace("+", " ")
    cleaned = cleaned.replace("~", " ")
    cleaned = cleaned.replace("^", " ")

    # Normalize dashes / ellipsis to pause-friendly punctuation
    cleaned = cleaned.replace("—", ", ").replace("–", ", ").replace("…", "। ")
    cleaned = cleaned.replace("...", "। ")

    # Collapse whitespace; keep paragraph breaks as short pauses via danda
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "। ", cleaned)
    cleaned = re.sub(r"\n+", " ", cleaned)
    cleaned = re.sub(r"[।]{2,}", "। ", cleaned)
    cleaned = re.sub(r"\s+([,।.!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _truncate_for_tts(text: str, limit: int | None = None) -> str:
    from tts_engine import MAX_CHARS

    if limit is None:
        limit = MAX_CHARS
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 3].rsplit(" ", 1)[0]
    return cut + "..."


def generate_narration_audio(
    narration_script: str,
    voice_id: str,
    *,
    output_name: str | None = None,
    speed: float = 1.0,
    volume: float = 1.0,
) -> Path:
    """Convert narration script to audio using the existing TTS engine."""
    from tts_engine import synthesize

    script = clean_script_for_tts(narration_script)
    script = _truncate_for_tts(script)
    if not script:
        raise ValueError("Narration script is empty after cleaning. Cannot generate audio.")
    return synthesize(
        script,
        voice_id,
        speed=speed,
        volume=volume,
        output_name=output_name,
    )
