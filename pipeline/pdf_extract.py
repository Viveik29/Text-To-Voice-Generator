"""Multi-method PDF page text extraction with OCR fallback."""

from __future__ import annotations

import io
import os
import re
import shutil
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF

OcrMode = Literal["auto", "fast", "high"]

OCR_FAST_DPI = 175
OCR_HIGH_DPI = 280

MIN_READABLE_RATIO = 0.52
OCR_TRIGGER_RATIO = 0.45

# Newspaper PDFs often map glyphs to Private Use Area (U+E000–U+F8FF).
_PUA_RE = re.compile(r"[\ue000-\uf8ff]")
_HTML_ENTITY_RE = re.compile(r"&#x[0-9a-fA-F]+;|&[a-zA-Z]+;")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# HTML-escape debris from broken PDF text layers (not real words).
_ENTITY_WORDS = frozenset(
    {"quot", "apos", "amp", "nbsp", "lt", "gt", "copy", "reg", "mdash", "ndash", "hellip"}
)

# In-memory OCR cache: (path, mtime_ns, page_index, dpi) -> text
_ocr_cache: dict[tuple[str, int, int, int], str] = {}
_ocr_lines_cache: dict[tuple[str, int, int, int], list] = {}


def _clean_for_word_count(text: str) -> str:
    text = _HTML_ENTITY_RE.sub(" ", text)
    text = _CONTROL_RE.sub(" ", text)
    return text


def _base_readable_ratio(text: str) -> float:
    if not text:
        return 0.0
    good = sum(
        1
        for c in text
        if c.isalnum() or c.isspace() or c in ".,;:'\"!?-—()[]/%&"
    )
    return good / len(text)


def readable_ratio(text: str) -> float:
    if not text or has_broken_font_mapping(text):
        return 0.0
    return _base_readable_ratio(text)


def count_real_words(text: str) -> int:
    cleaned = _clean_for_word_count(text)
    words = re.findall(r"[A-Za-z]{4,}", cleaned)
    return sum(
        1
        for w in words
        if w.lower() not in _ENTITY_WORDS and any(v in w.lower() for v in "aeiou")
    )


def article_text_quality(text: str) -> tuple[float, int, float]:
    """Return (readable_ratio, real_word_count, alpha_ratio)."""
    stripped = text.strip()
    if not stripped:
        return 0.0, 0, 0.0
    words = count_real_words(stripped)
    compact = stripped.replace(" ", "").replace("\n", "")
    alpha = sum(c.isalpha() for c in compact)
    alpha_ratio = alpha / max(len(compact), 1)
    return readable_ratio(stripped), words, alpha_ratio


def article_text_is_usable(text: str, *, min_words: int = 25) -> tuple[bool, str]:
    """Return whether extracted article text is good enough to send to Claude."""
    ratio, words, alpha_ratio = article_text_quality(text)
    if len(text.strip()) < 80:
        return False, "Extracted text is too short."
    if words < min_words:
        return (
            False,
            f"PDF extraction produced only {words} readable words (garbled text). "
            "Enable **Use OCR**, re-detect the article, or paste the article text in the fallback box.",
        )
    if alpha_ratio < 0.4:
        return (
            False,
            "Extracted text is mostly symbols, not real sentences. "
            "Paste the article manually in **Paste article text (fallback)**.",
        )
    if ratio < 0.58:
        return (
            False,
            f"Extracted text quality is too low ({ratio:.0%}). "
            "Try **Use OCR** or paste the article text directly.",
        )
    return True, "ok"


def has_broken_font_mapping(text: str) -> bool:
    """True when text looks like a broken PDF copy (PUA / symbol soup, not real words)."""
    if not text.strip():
        return False
    if _HTML_ENTITY_RE.search(text):
        entity_hits = len(_HTML_ENTITY_RE.findall(text))
        if entity_hits >= 10 or entity_hits / max(len(text), 1) > 0.01:
            return True
    if _CONTROL_RE.search(text):
        ctrl = len(_CONTROL_RE.findall(text))
        if ctrl >= 8 or ctrl / max(len(text), 1) > 0.005:
            return True
    pua_hits = len(_PUA_RE.findall(text))
    if pua_hits >= 8:
        return True
    if pua_hits >= 3 and pua_hits / max(len(text), 1) > 0.02:
        return True
    words = count_real_words(text)
    if words < 15:
        compact = _clean_for_word_count(text).replace(" ", "").replace("\n", "")
        alpha_ratio = sum(c.isalpha() for c in compact) / max(len(compact), 1)
        if alpha_ratio < 0.12 or _base_readable_ratio(text) < 0.55:
            return True
    return False


def text_quality_score(text: str) -> float:
    """Higher is better — balances readability and real English word count."""
    ratio, words, alpha_ratio = article_text_quality(text)
    return ratio * 0.35 + min(words / 80, 1.0) * 0.45 + alpha_ratio * 0.2


def _strip_html(raw: str) -> str:
    text = re.sub(r"<(br|/p|/div|/tr)\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_pymupdf(page: fitz.Page) -> list[str]:
    out: list[str] = []
    out.append(page.get_text("text", sort=True).strip())

    block_lines = [
        str(b[4]).strip() for b in page.get_text("blocks") if len(b) >= 5 and str(b[4]).strip()
    ]
    if block_lines:
        out.append("\n".join(block_lines))

    dict_lines: list[str] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            parts = [s.get("text", "").strip() for s in line.get("spans", [])]
            line_text = " ".join(p for p in parts if p)
            if line_text:
                dict_lines.append(line_text)
    if dict_lines:
        out.append("\n".join(dict_lines))

    html = page.get_text("html")
    if html:
        out.append(_strip_html(html))

    return [t for t in out if t]


def _extract_pdfplumber(path: Path, page_index: int) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""

    try:
        with pdfplumber.open(path) as pdf:
            if page_index < 0 or page_index >= len(pdf.pages):
                return ""
            text = pdf.pages[page_index].extract_text() or ""
            if not text.strip():
                text = pdf.pages[page_index].extract_text(layout=True) or ""
            return text.strip()
    except Exception:
        return ""


def _configure_tesseract() -> bool:
    """Point pytesseract at the Tesseract binary on Windows if needed."""
    try:
        import pytesseract
    except ImportError:
        return False

    cmd = os.getenv("TESSERACT_CMD", "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        return Path(cmd).exists()

    if shutil.which("tesseract"):
        return True

    # Common Windows install locations
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return True
    return False


def _page_cache_key(path: Path, page_index: int, dpi: int) -> tuple[str, int, int, int]:
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, page_index, dpi)


def _preprocess_ocr_image(pix: fitz.Pixmap):
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return ImageOps.autocontrast(img.convert("L"))


def _run_tesseract(image, *, psm: int = 1, dpi: int = OCR_FAST_DPI) -> str:
    import pytesseract

    config = f"--psm {psm} -c preserve_interword_spaces=1"
    return pytesseract.image_to_string(image, lang="eng", config=config).strip()


def _extract_ocr(page: fitz.Page, *, dpi: int = OCR_FAST_DPI, psm: int = 1) -> str:
    """OCR a rendered page using Tesseract (requires tesseract installed on system)."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return ""

    if not _configure_tesseract():
        return ""

    try:
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        gray = _preprocess_ocr_image(pix)
        return _run_tesseract(gray, psm=psm, dpi=dpi)
    except Exception:
        return ""


def _extract_ocr_cached(path: Path, page_index: int, *, dpi: int = OCR_FAST_DPI) -> str:
    key = _page_cache_key(path, page_index, dpi)
    if key in _ocr_cache:
        return _ocr_cache[key]

    doc = fitz.open(path)
    try:
        if page_index < 0 or page_index >= len(doc):
            return ""
        text = _extract_ocr(doc[page_index], dpi=dpi)
    finally:
        doc.close()

    _ocr_cache[key] = text
    return text


def get_ocr_lines(path: Path, page_index: int, *, dpi: int = OCR_FAST_DPI):
    """Return cached OCR lines with layout (word boxes)."""
    from pipeline.ocr_layout import extract_ocr_lines, ocr_page_to_plain_text

    key = _page_cache_key(path, page_index, dpi)
    if key in _ocr_lines_cache:
        return _ocr_lines_cache[key]

    doc = fitz.open(path)
    try:
        if page_index < 0 or page_index >= len(doc):
            return []
        lines = extract_ocr_lines(doc[page_index], dpi=dpi)
    finally:
        doc.close()

    _ocr_lines_cache[key] = lines
    if lines:
        _ocr_cache[key] = ocr_page_to_plain_text(lines)
    return lines


def tesseract_available() -> bool:
    """Return True if Tesseract OCR binary is available."""
    return _configure_tesseract()


def extract_page_text(
    path: Path,
    page_index: int,
    *,
    force_ocr: bool = False,
    ocr_mode: OcrMode = "auto",
) -> tuple[str, str]:
    """
    Extract text from one PDF page using the best available method.

    ocr_mode:
        auto  — pick best method
        fast  — 175 DPI OCR (quick scan / article detection)
        high  — 280 DPI OCR (final article extraction)

    Returns:
        (text, method_used) e.g. ("...", "pymupdf") or ("...", "ocr_fast")
    """
    ocr_dpi = OCR_HIGH_DPI if ocr_mode == "high" else OCR_FAST_DPI

    doc = fitz.open(path)
    try:
        if page_index < 0 or page_index >= len(doc):
            return "", "none"
        page = doc[page_index]

        if force_ocr or ocr_mode in ("fast", "high"):
            from pipeline.ocr_layout import ocr_page_to_plain_text

            lines = get_ocr_lines(path, page_index, dpi=ocr_dpi)
            if lines:
                text = ocr_page_to_plain_text(lines)
                if text:
                    tag = "ocr_high" if ocr_dpi >= OCR_HIGH_DPI else "ocr_fast"
                    return text, tag
            ocr_text = _extract_ocr_cached(path, page_index, dpi=ocr_dpi)
            if ocr_text:
                tag = "ocr_high" if ocr_dpi >= OCR_HIGH_DPI else "ocr_fast"
                return ocr_text, tag
            return "", "ocr_failed"

        candidates: list[tuple[str, str]] = []
        for text in _extract_pymupdf(page):
            candidates.append((text, "pymupdf"))

        plumber = _extract_pdfplumber(path, page_index)
        if plumber:
            candidates.append((plumber, "pdfplumber"))

        best_text = ""
        best_method = "none"
        if candidates:
            best_text, best_method = max(candidates, key=lambda x: text_quality_score(x[0]))
            if has_broken_font_mapping(best_text):
                from pipeline.ocr_layout import ocr_page_to_plain_text

                lines = get_ocr_lines(path, page_index, dpi=OCR_FAST_DPI)
                if lines:
                    ocr_text = ocr_page_to_plain_text(lines)
                    if ocr_text and text_quality_score(ocr_text) > text_quality_score(best_text):
                        return ocr_text, "ocr_fast"
                ocr_text = _extract_ocr_cached(path, page_index, dpi=OCR_FAST_DPI)
                if ocr_text and text_quality_score(ocr_text) > text_quality_score(best_text):
                    return ocr_text, "ocr_fast"
                if ocr_text:
                    return ocr_text, "ocr_fast"
                return "", "ocr_failed"
            usable, _reason = article_text_is_usable(best_text)
            if usable:
                return best_text, best_method

        from pipeline.ocr_layout import ocr_page_to_plain_text

        lines = get_ocr_lines(path, page_index, dpi=OCR_FAST_DPI)
        ocr_text = ocr_page_to_plain_text(lines) if lines else _extract_ocr_cached(path, page_index, dpi=OCR_FAST_DPI)
        if ocr_text and text_quality_score(ocr_text) > text_quality_score(best_text):
            return ocr_text, "ocr_fast"

        if best_text:
            return best_text, best_method
        if ocr_text:
            return ocr_text, "ocr_fast"
        return "", "none"
    finally:
        doc.close()


def extract_document_text(
    path: Path,
    *,
    page_number: int | None = None,
    max_pages: int = 50,
    force_ocr: bool = False,
    ocr_mode: OcrMode = "auto",
) -> tuple[str, str]:
    """Extract text from one page or entire document."""
    doc = fitz.open(path)
    try:
        n = min(len(doc), max_pages)
        if page_number and page_number > 0:
            indices = [page_number - 1]
        else:
            indices = list(range(n))
    finally:
        doc.close()

    parts: list[str] = []
    methods: set[str] = set()
    for idx in indices:
        text, method = extract_page_text(path, idx, force_ocr=force_ocr, ocr_mode=ocr_mode)
        if text:
            parts.append(text)
            methods.add(method)

    if not parts:
        return "", "none"
    return "\n\n".join(parts), "+".join(sorted(methods))


def is_pdf_readable(path: Path, page_number: int | None = None) -> tuple[bool, float, str]:
    """Check if PDF has extractable readable text on a page."""
    doc = fitz.open(path)
    try:
        idx = (page_number - 1) if page_number and page_number > 0 else 0
        if idx >= len(doc):
            idx = 0
    finally:
        doc.close()

    text, method = extract_page_text(path, idx)
    ratio = readable_ratio(text)
    return ratio >= MIN_READABLE_RATIO, ratio, method


def unreadable_pdf_message(*, ocr_failed: bool = False) -> str:
    if ocr_failed:
        return (
            "OCR was enabled but could not read this PDF page.\n\n"
            "Check that Tesseract is installed (`python check_pdf_ocr.py`), "
            "or paste the article in **Paste article text (fallback)**."
        )
    ocr_hint = (
        "Enable **Use OCR** and click Detect (Tesseract is installed)."
        if tesseract_available()
        else "Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
    )
    return (
        "This PDF has no readable text layer (scanned image or custom fonts).\n\n"
        "Options:\n"
        f"  1. {ocr_hint}\n"
        "  2. Expand **'Paste article text (fallback)'** and paste the article\n"
        "  3. Switch to **Paste text** input mode"
    )
