"""Extract plain text from PDF uploads or raw text input."""

from pathlib import Path

from pipeline.pdf_articles import extract_text_from_pdf as _extract_full_pdf

__all__ = ["extract_text_from_pdf", "normalize_text"]


def extract_text_from_pdf(path: Path, *, max_pages: int = 50, force_ocr: bool = False) -> str:
    """Return cleaned text from a PDF file (all pages)."""
    return _extract_full_pdf(path, max_pages=max_pages, force_ocr=force_ocr)


def normalize_text(text: str, *, max_chars: int = 80_000) -> str:
    """Clean and cap user-provided text."""
    cleaned = "\n".join(line.rstrip() for line in text.strip().splitlines())
    cleaned = "\n".join(line for line in cleaned.split("\n") if line.strip())
    if not cleaned:
        raise ValueError("Please provide news text or upload a PDF.")
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n\n[Truncated for analysis length limit]"
    return cleaned
