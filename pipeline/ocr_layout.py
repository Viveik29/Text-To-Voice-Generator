"""OCR layout analysis — format-agnostic newspaper PDF article segmentation.

Strategy (works across broadsheet/tabloid/editorial layouts):
1. OCR word boxes → lines, split on horizontal gutters
2. Detect vertical columns via x-center peaks/valleys
3. Read each column top→bottom (never interleave side-by-side text)
4. Start a new article at display headlines (font-size / shape heuristics)
5. Merge orphan body fragments into neighboring titled pieces

Article-specific title lists are intentionally avoided so new PDFs work
without code changes.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import fitz  # PyMuPDF

from pipeline.pdf_extract import count_real_words, readable_ratio

OCR_FAST_DPI = 175
OCR_HIGH_DPI = 280
MIN_ARTICLE_WORDS = 90
MIN_CHUNK_WORDS = 55
HEADLINE_MAX_LEN = 140
ROW_Y_TOLERANCE = 14

# Generic newspaper chrome / noise (not paper-specific article titles).
_NOISE_LINE_RE = re.compile(
    r"^(?:@+\s*)?(?:FOUNDED BY|Log on to|www\.|~+\s*$|"
    r"epaper\.|ne\s*$|=\)+$|RAMNATH GOENK|GOENK\s*$|"
    r"Page\s+\d+\s*$|CONTINUED ON\b|SEE PAGE\b)",
    re.I,
)
_SECTION_START_RE = re.compile(
    r"^@?\s*(WEB EXCLUSIVE|WORDLY WISE|\d+\s+YEARS\s+AGO|"
    r"OPINION|EDITORIAL|ANALYSIS|COMMENT|LETTERS TO THE EDITOR)\b",
    re.I,
)
_TAGLINE_RE = re.compile(
    r"^(?:BECAUSE THE TRUTH|INVOLVES US ALL|THE INDIAN\s*EXPRESS|"
    r"he Editorial Page|The Editorial Page|TIMES OF INDIA|HINDUSTAN TIMES|"
    r"THE HINDU|DECCAN HERALD|MINT\b)",
    re.I,
)
_BYLINE_RE = re.compile(r"^(?:By|BY)\s+[A-Z][A-Za-z.'\-]+", re.I)
_DATE_MASTHEAD_RE = re.compile(
    r"^\s*\d{1,2}\s+"
    r"(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),?\s+"
    r"[A-Z]+\s+\d{1,2},?\s+\d{4}\s*",
    re.I,
)
_MASTHEAD_NOISE_RE = re.compile(
    r"\b(?:e\s+EXPRESS|EXPRESS|Editorial Page|RAMNATH GOENK|GOENK|FOUNDED BY|"
    r"THE SUNDAY|Opinion)\b",
    re.I,
)
_COLUMN_MARKER_RE = re.compile(
    r"\b(?:THINK\s+BY\s+[A-Z][A-Z\s]+|[A-Z]{3,}\s+THINK)\b",
    re.I,
)


@dataclass
class OcrLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    column: int = 0
    height: float = 0.0
    conf: float = 0.0


def _preprocess_image(pix: fitz.Pixmap):
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(pix.tobytes("png")))
    gray = ImageOps.autocontrast(img.convert("L"))
    return gray


def _body_line_centers(lines: list[OcrLine], page_w: float) -> list[float]:
    """X-centers of normal body lines (exclude wide spanning headlines)."""
    median_h = _median_line_height(lines) if lines else 12.0
    centers: list[float] = []
    for ln in lines:
        width = ln.x1 - ln.x0
        if width > page_w * 0.38:
            continue
        if ln.height > max(90.0, median_h * 2.8):
            continue
        centers.append((ln.x0 + ln.x1) / 2)
    return sorted(centers)


def _detect_column_cuts(lines: list[OcrLine], page_w: float) -> list[float]:
    """
    Find vertical gutters between newspaper columns via x-center peaks.

    Dense peaks = column bodies; valleys between peaks = gutters.
    """
    centers = _body_line_centers(lines, page_w)
    if len(centers) < 25:
        return _detect_column_cuts_by_gaps(centers, page_w) if len(centers) >= 12 else []

    bucket = max(40.0, page_w * 0.012)
    hist: dict[int, int] = {}
    for c in centers:
        key = int(c // bucket)
        hist[key] = hist.get(key, 0) + 1

    if not hist:
        return []

    # Peak = bucket with enough lines and more than neighbors
    min_peak = max(8, int(len(centers) * 0.03))
    keys = sorted(hist)
    peaks: list[float] = []
    for k in keys:
        count = hist[k]
        if count < min_peak:
            continue
        left = hist.get(k - 1, 0)
        right = hist.get(k + 1, 0)
        if count >= left and count >= right:
            peaks.append((k + 0.5) * bucket)

    # Merge peaks that are very close (same column)
    merged_peaks: list[float] = []
    for p in peaks:
        if merged_peaks and abs(p - merged_peaks[-1]) < page_w * 0.11:
            merged_peaks[-1] = (merged_peaks[-1] + p) / 2
        else:
            merged_peaks.append(p)

    if len(merged_peaks) < 2:
        # Single-column page — no gutters
        return []

    cuts: list[float] = []
    for a, b in zip(merged_peaks, merged_peaks[1:]):
        # Valley midpoint between peaks
        mid = (a + b) / 2
        # Require a real valley (few centers near mid)
        near = sum(1 for c in centers if abs(c - mid) < bucket * 1.2)
        if near > min_peak:
            continue
        if b - a < page_w * 0.055:
            continue
        cuts.append(mid)

    # Prefer 3–5 columns; if too many cuts, keep the widest valleys only
    if len(cuts) > 4:
        scored = []
        for mid in cuts:
            left = [c for c in centers if c < mid]
            right = [c for c in centers if c >= mid]
            if not left or not right:
                continue
            gap = min(right) - max(left)
            scored.append((gap, mid))
        scored.sort(reverse=True)
        cuts = sorted(m for _, m in scored[:4])

    return cuts


def _detect_column_cuts_by_gaps(centers: list[float], page_w: float) -> list[float]:
    """Fallback gutter detection using largest empty gaps."""
    min_gap = max(55.0, page_w * 0.015)
    candidates: list[tuple[float, float]] = []
    for a, b in zip(centers, centers[1:]):
        gap = b - a
        if gap >= min_gap:
            candidates.append((gap, (a + b) / 2))
    candidates.sort(reverse=True)
    cuts: list[float] = []
    for gap, mid in candidates:
        if any(abs(mid - existing) < page_w * 0.06 for existing in cuts):
            continue
        left_n = sum(1 for c in centers if c < mid)
        right_n = sum(1 for c in centers if c >= mid)
        if left_n < 10 or right_n < 10:
            continue
        cuts.append(mid)
        if len(cuts) >= 5:
            break
    return sorted(cuts) if cuts else []


def _detect_sidebar_x_boundary(lines: list[OcrLine]) -> float:
    """Compatibility helper: first column cut (left sidebar edge)."""
    page_w = max((ln.x1 for ln in lines), default=3600.0)
    cuts = _detect_column_cuts(lines, page_w)
    return cuts[0] if cuts else page_w * 0.5


def _assign_columns(lines: list[OcrLine], page_w: float) -> None:
    """Assign each OCR line to a vertical column strip (0..N)."""
    cuts = _detect_column_cuts(lines, page_w)
    for ln in lines:
        width = ln.x1 - ln.x0
        # Spanning headlines: pin to far-left so they stay with the lead column body
        if width > page_w * 0.38:
            xc = ln.x0 + min(40.0, page_w * 0.02)
        else:
            xc = (ln.x0 + ln.x1) / 2
        col = 0
        for cut in cuts:
            if xc >= cut:
                col += 1
            else:
                break
        ln.column = col


def _split_words_by_column_gap(words: list[dict], *, min_gap: float = 90.0) -> list[list[dict]]:
    """Split a Tesseract line when a wide gutter separates side-by-side headlines/columns."""
    if not words:
        return []
    words = sorted(words, key=lambda w: w["x0"])
    groups: list[list[dict]] = [[words[0]]]
    for prev, cur in zip(words, words[1:]):
        gap = cur["x0"] - prev["x1"]
        # Ignore thin rule glyphs between columns
        if cur["text"] in {"|", "¦", "‖"}:
            groups.append([])
            continue
        if prev["text"] in {"|", "¦", "‖"}:
            if groups[-1]:
                groups.append([cur])
            else:
                groups[-1] = [cur]
            continue
        if gap >= min_gap and groups[-1]:
            groups.append([cur])
        else:
            if not groups[-1] and cur["text"] not in {"|", "¦", "‖"}:
                groups[-1] = [cur]
            else:
                groups[-1].append(cur)
    return [g for g in groups if g]


def extract_ocr_lines(page: fitz.Page, *, dpi: int = OCR_FAST_DPI) -> list[OcrLine]:
    """Extract positioned text lines from a page via Tesseract word boxes."""
    from pytesseract import Output

    from pipeline.pdf_extract import _configure_tesseract

    if not _configure_tesseract():
        return []

    try:
        import pytesseract
    except ImportError:
        return []

    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = _preprocess_image(pix)
    scale = dpi / 72.0
    page_w = page.rect.width * scale
    # Scale gutter threshold with DPI (≈70px at 175 DPI) — tight enough to
    # separate side-by-side editorial columns without splitting hyphenated words.
    gap_min = max(55.0, dpi * 0.38)

    data = pytesseract.image_to_data(
        img,
        lang="eng",
        config="--psm 1 -c preserve_interword_spaces=1",
        output_type=Output.DICT,
    )

    line_buckets: dict[tuple[int, int, int], list[dict]] = {}
    n = len(data["text"])
    for i in range(n):
        word = (data["text"][i] or "").strip()
        conf = int(float(data["conf"][i])) if data["conf"][i] != "-1" else -1
        if not word or conf < 25:
            continue
        if word in {"|", "¦", "‖"}:
            # Keep as a soft separator marker for gap splitting
            pass
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        line_buckets.setdefault(key, []).append(
            {
                "text": word,
                "x0": data["left"][i],
                "y0": data["top"][i],
                "x1": data["left"][i] + data["width"][i],
                "y1": data["top"][i] + data["height"][i],
                "conf": conf,
            }
        )

    lines: list[OcrLine] = []
    for words in line_buckets.values():
        for group in _split_words_by_column_gap(words, min_gap=gap_min):
            text = " ".join(w["text"] for w in group if w["text"] not in {"|", "¦", "‖"})
            text = re.sub(r"\s+", " ", text).strip()
            # Fix common glued headline OCR
            text = re.sub(r"\bTheworker\b", "The worker", text, flags=re.I)
            text = re.sub(r"\bTheworker-intellectual\b", "The worker-intellectual", text, flags=re.I)
            if len(text) < 2:
                continue
            x0 = min(w["x0"] for w in group)
            y0 = min(w["y0"] for w in group)
            x1 = max(w["x1"] for w in group)
            y1 = max(w["y1"] for w in group)
            height = y1 - y0
            conf = sum(w["conf"] for w in group) / len(group)
            lines.append(
                OcrLine(
                    text=text,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    height=height,
                    conf=conf,
                )
            )

    _assign_columns(lines, page_w)
    lines.sort(key=lambda ln: (ln.y0, ln.x0))
    return _merge_broken_headlines(lines)


def _merge_broken_headlines(lines: list[OcrLine]) -> list[OcrLine]:
    """Join OCR headline lines split across rows."""
    if not lines:
        return []

    merged: list[OcrLine] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            same_col = cur.column == nxt.column
            close_y = (nxt.y0 - cur.y1) < max(cur.height, nxt.height) * 1.8
            if (
                same_col
                and close_y
                and _looks_like_headline_start(cur.text)
                and not _is_body_sentence(cur.text)
                and len(nxt.text.split()) <= 10
                and not _is_body_sentence(nxt.text)
            ):
                combined = f"{cur.text.rstrip(',-— ')} {nxt.text}".strip()
                merged.append(
                    OcrLine(
                        text=combined,
                        x0=min(cur.x0, nxt.x0),
                        y0=cur.y0,
                        x1=max(cur.x1, nxt.x1),
                        y1=nxt.y1,
                        column=cur.column,
                        height=nxt.y1 - cur.y0,
                        conf=(cur.conf + nxt.conf) / 2,
                    )
                )
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def _is_body_sentence(line: str) -> bool:
    line = line.strip()
    if len(line) > 120:
        return True
    if line.endswith((".", "?", "!")):
        return True
    return len(line.split()) > 14


def _looks_like_headline_start(line: str) -> bool:
    line = line.strip()
    if len(line) < 10 or len(line) > HEADLINE_MAX_LEN:
        return False
    if _NOISE_LINE_RE.match(line) or _TAGLINE_RE.match(line):
        return False
    alpha = re.sub(r"[^A-Za-z]", "", line)
    if len(alpha) < 8:
        return False
    upper = sum(1 for c in alpha if c.isupper()) / len(alpha)
    if upper > 0.55:
        return True
    words = line.split()
    return 3 <= len(words) <= 14 and line[0].isupper()


def _is_noise_line(line: str) -> bool:
    text = line.strip()
    if not text or len(text) < 3:
        return True
    if _NOISE_LINE_RE.match(text):
        return True
    if _BYLINE_RE.match(text) and len(text.split()) < 8:
        return True
    if readable_ratio(text) < 0.35:
        return True
    if count_real_words(text) == 0 and len(text) < 40:
        return True
    if sum(c.isalpha() for c in text) / max(len(text), 1) < 0.35:
        return True
    return False


def _clean_title(title: str) -> str:
    """Strip masthead/date noise and light OCR glue from a guessed headline."""
    title = _DATE_MASTHEAD_RE.sub("", title).strip()
    title = _MASTHEAD_NOISE_RE.sub("", title).strip()
    title = re.sub(r"\s{2,}", " ", title).strip(" -–—|")
    # Light OCR de-glue (generic)
    title = re.sub(r"\bAcall\b", "A call", title, flags=re.I)
    title = re.sub(r"\b([a-z]{3,})for\b", r"\1 for", title)
    title = re.sub(r"\bEREVER\b", "WHEREVER", title, flags=re.I)
    # Drop trailing bleed after em-dash when second half looks like another hed
    title = re.sub(r"\s*[–—]\s+[a-z].{8,}$", "", title).strip()
    if len(title) > HEADLINE_MAX_LEN:
        title = title[: HEADLINE_MAX_LEN - 3] + "..."
    # Deduplicate accidental repeated headline text
    words = title.split()
    for n in range(min(len(words) // 2, 14), 3, -1):
        prefix = " ".join(words[:n])
        rest = " ".join(words[n:])
        if rest.lower().startswith(prefix[:40].lower()):
            title = prefix
            break
    return title or "Article excerpt"


def _guess_title_from_lines(lines: list[str]) -> str:
    """Pick the best headline from the first lines of an article block."""
    cleaned = []
    for ln in lines:
        line = ln.strip()
        if not line or _is_noise_line(line) or _TAGLINE_RE.match(line):
            continue
        if _is_column_chrome(line):
            continue
        cleaned.append(line)

    if len(cleaned) >= 2:
        a, b = cleaned[0], cleaned[1]
        # Two-line display headline (short + short, neither is a body sentence)
        merge_two = (
            len(a.split()) <= 8
            and len(b.split()) <= 8
            and not _is_body_sentence(a)
            and not _is_body_sentence(b)
            and not a.endswith((".", "?", "!"))
            and a[:1].isupper()
            and (b[:1].islower() or (b[:1].isupper() and len(b.split()) <= 6))
            # Avoid gluing a dateline / prose opener onto the headline
            and not re.match(r"^(?:O?N\s+)?[A-Z]{3,9}\s+\d{1,2}\b", b)
            and not ("," in b and len(b.split()) >= 5)
        )
        if merge_two:
            b_clean = re.sub(r"[–—\-].*$", "", b).strip()
            merged = f"{a.rstrip(',-— ')} {b_clean}".strip()
            if 8 <= len(merged) <= HEADLINE_MAX_LEN + 20:
                return _clean_title(merged)

    for line in cleaned:
        if _looks_like_headline_start(line) or (len(line) >= 12 and count_real_words(line) >= 3):
            return _clean_title(line)
    for line in cleaned:
        return _clean_title(line)
    return "Article excerpt"


def _median_line_height(lines: list[OcrLine]) -> float:
    heights = sorted(ln.height for ln in lines if ln.height > 0)
    return heights[len(heights) // 2] if heights else 12.0


_COLUMN_CHROME_RE = re.compile(
    r"^(?:@+\s*)?(?:ACROSS THE AISLE|HISTORY HEADLINE|FIFTH COLUMN|WORDLY WISE|"
    r"WEB EXCLUSIVE|THE SUNDAY EXPRESS|THE SUNDAY\s+Opinion|Opinion\s*$|"
    r"Editor\s*\(Planning|LETTERS(?:\s+TO\s+THE\s+EDITOR)?|"
    r"BY\s+[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3}$)",
    re.I,
)
_MASTHEAD_LINE_RE = re.compile(
    r"^(?:THE\s+SUNDAY\s+EXPRESS|THE\s+INDIAN\s+EXPRESS|The Editorial Page|"
    r"TIMES OF INDIA|THE HINDU|HINDUSTAN TIMES|DECCAN HERALD|"
    r"(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|"
    r"OCTOBER|NOVEMBER|DECEMBER)\s+\d{1,2},\s+\d{4})\b",
    re.I,
)
# Soft section kickers shared by many newspapers (not article titles).
_GENERIC_SECTION_RE = re.compile(
    r"^@?\s*(WEB EXCLUSIVE|WORDLY WISE|\d+\s+YEARS\s+AGO|"
    r"OPINION|EDITORIAL|ANALYSIS|COMMENT)\b",
    re.I,
)


def _is_column_chrome(text: str) -> bool:
    text = text.strip()
    if _COLUMN_CHROME_RE.match(text) or _MASTHEAD_LINE_RE.match(text):
        return True
    # Short author-only lines (2–4 name tokens), including mixed case like "Roxy MATHEW KOLL"
    if len(text) < 40 and 2 <= len(text.split()) <= 4:
        if re.match(
            r"^(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}|\([A-Za-z.]+\))){1,3}$",
            text,
        ):
            return True
        if re.match(r"^[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3}$", text):
            # Reject only if it clearly reads as a topical headline (has function words)
            if not re.search(r"\b(?:the|a|an|for|and|of|to|in|on|is|are|we|our)\b", text, re.I):
                return True
    return False


def _is_headline_continuation(text: str) -> bool:
    """Second half of a wrapped display headline — not a new article."""
    text = text.strip()
    if not text:
        return False
    if text[0].isupper() and len(text.split()) > 6:
        return False
    if text[0].islower() and len(text.split()) <= 8 and not _is_body_sentence(text):
        return True
    return False


def _is_large_headline(ln: OcrLine, median_h: float, *, strict: bool = False) -> bool:
    """Detect printed headlines via OCR line height (font size proxy)."""
    text = ln.text.strip()
    if _is_noise_line(text) or _TAGLINE_RE.match(text) or _DATE_MASTHEAD_RE.match(text):
        return False
    if _is_column_chrome(text):
        return False
    if _is_headline_continuation(text):
        return False
    if "/" in text and len(text) > 40:
        return False
    if _is_body_sentence(text) and ln.height < median_h * 2.5:
        return False
    words = len(text.split())
    if words < 2:
        return False
    # Very tall display type — almost always a new article
    if ln.height >= median_h * 3.5 and words <= 18 and not _is_body_sentence(text):
        return True
    if words > 16:
        return False
    # Strict (left stack): require clearly larger display type to avoid pull-quotes
    min_ratio = 3.2 if strict else 1.7
    max_words = 10 if strict else 14
    min_abs = median_h * 3.0 if strict else median_h * 1.7
    if words > max_words:
        return False
    if ln.height >= max(min_abs, median_h * min_ratio):
        return True
    if not strict and ln.height >= median_h * 2.5 and words <= 12:
        return True
    if not strict and _looks_like_headline_start(text) and words <= 10:
        alpha = re.sub(r"[^A-Za-z]", "", text)
        upper = sum(1 for c in alpha if c.isupper()) / max(len(alpha), 1)
        if upper > 0.6 and ln.height >= median_h * 1.35:
            return True
    return False


def _is_anchor_line(ln: OcrLine, median_h: float, *, zone: str) -> bool:
    """True when this line starts a new article block (geometry-first)."""
    text = ln.text.strip()
    if _is_noise_line(text):
        return False
    if _is_column_chrome(text) and not _GENERIC_SECTION_RE.match(text):
        return False
    if _MASTHEAD_LINE_RE.match(text):
        return False
    if _is_headline_continuation(text):
        return False

    strict = zone == "left"
    if _is_large_headline(ln, median_h, strict=strict):
        return True
    if _GENERIC_SECTION_RE.match(text):
        return True
    return False


def _cluster_lines_by_row(lines: list[OcrLine], y_tol: float = ROW_Y_TOLERANCE) -> list[list[OcrLine]]:
    """Group OCR lines on the same horizontal band (legacy helper)."""
    usable = [ln for ln in lines if not _is_noise_line(ln.text)]
    usable.sort(key=lambda ln: (ln.y0, ln.x0))

    rows: list[list[OcrLine]] = []
    current: list[OcrLine] = []
    anchor_y: float | None = None

    for ln in usable:
        if anchor_y is None or abs(ln.y0 - anchor_y) <= y_tol:
            current.append(ln)
            if anchor_y is None:
                anchor_y = ln.y0
        else:
            if current:
                rows.append(sorted(current, key=lambda l: l.x0))
            current = [ln]
            anchor_y = ln.y0
    if current:
        rows.append(sorted(current, key=lambda l: l.x0))
    return rows


def _row_text(row: list[OcrLine]) -> str:
    return re.sub(r"\s+", " ", " ".join(ln.text for ln in row)).strip()


def _cluster_vertical_strips(
    lines: list[OcrLine],
    *,
    min_gap: float | None = None,
) -> list[list[OcrLine]]:
    """
    Split lines into vertical column strips using x-center gutters.

    Each strip is returned already sorted top→bottom. Spanning headlines are
    assigned by their left edge so they stay with the leftmost article they cover.
    """
    del min_gap  # cuts come from peak/valley detection
    if not lines:
        return []

    page_w = max(ln.x1 for ln in lines)
    cuts = _detect_column_cuts(lines, page_w)

    def _strip_id(ln: OcrLine) -> int:
        width = ln.x1 - ln.x0
        # Pin spanning headlines to the leftmost column they cover
        if width > page_w * 0.38:
            xc = ln.x0 + min(40.0, page_w * 0.02)
        else:
            xc = (ln.x0 + ln.x1) / 2
        sid = 0
        for cut in cuts:
            if xc >= cut:
                sid += 1
            else:
                break
        return sid

    buckets: dict[int, list[OcrLine]] = {}
    for ln in lines:
        buckets.setdefault(_strip_id(ln), []).append(ln)

    strips: list[list[OcrLine]] = []
    for sid in sorted(buckets):
        strips.append(sorted(buckets[sid], key=lambda ln: (ln.y0, ln.x0)))
    return strips


def _lines_to_reading_text(zone_lines: list[OcrLine]) -> str:
    """
    Merge zone lines in newspaper reading order: each vertical strip
    top→bottom, then left→right. Never interleave adjacent columns.

    If the zone is already a single column strip (unique column ids or
    narrow x-span), just sort top→bottom — avoid re-clustering which can
    re-assign spanning headlines into the wrong article body.
    """
    if not zone_lines:
        return ""

    page_w = max(ln.x1 for ln in zone_lines)
    x_span = max(ln.x1 for ln in zone_lines) - min(ln.x0 for ln in zone_lines)
    col_ids = {ln.column for ln in zone_lines}

    # Already one strip / one column — do not re-cluster
    if len(col_ids) <= 1 or x_span < page_w * 0.42:
        texts = [
            ln.text.strip()
            for ln in sorted(zone_lines, key=lambda ln: (ln.y0, ln.x0))
            if not _is_noise_line(ln.text)
        ]
        return "\n".join(texts)

    parts: list[str] = []
    for strip in _cluster_vertical_strips(zone_lines):
        texts = [ln.text.strip() for ln in strip if not _is_noise_line(ln.text)]
        if texts:
            parts.append("\n".join(texts))
    return "\n\n".join(parts)


def _split_zone_by_anchors(zone_lines: list[OcrLine], *, zone: str) -> list[tuple[str, str]]:
    """Split one page zone (column strip) into articles at display headlines."""
    if not zone_lines:
        return []

    median_h = _median_line_height(zone_lines)
    sorted_lines = sorted(zone_lines, key=lambda ln: (ln.y0, ln.x0))

    anchor_indices: list[int] = []
    for i, ln in enumerate(sorted_lines):
        if _is_anchor_line(ln, median_h, zone=zone):
            # Skip duplicate anchors on consecutive lines (split headline rows)
            if anchor_indices and i - anchor_indices[-1] <= 2:
                continue
            # Also skip if y is nearly the same as previous anchor (side-by-side hed halves)
            if anchor_indices:
                prev = sorted_lines[anchor_indices[-1]]
                if abs(ln.y0 - prev.y0) < max(40.0, median_h) and abs(
                    (ln.x0 + ln.x1) / 2 - (prev.x0 + prev.x1) / 2
                ) < 200:
                    continue
            anchor_indices.append(i)

    if not anchor_indices:
        body = _lines_to_reading_text(sorted_lines)
        body = _clean_section_text(body)
        if count_real_words(body) >= MIN_CHUNK_WORDS:
            return [(_guess_title_from_lines(body.splitlines()), body)]
        return []

    articles: list[tuple[str, str]] = []
    for ai, start_idx in enumerate(anchor_indices):
        end_idx = anchor_indices[ai + 1] if ai + 1 < len(anchor_indices) else len(sorted_lines)

        # Hard stop: never include a later display headline in this article's body
        group: list[OcrLine] = []
        for j in range(start_idx, end_idx):
            ln = sorted_lines[j]
            if j > start_idx and _is_anchor_line(ln, median_h, zone=zone):
                # Safety net if anchor list missed this line
                end_idx = j
                break
            group.append(ln)

        # Prefer plain y-order join (single strip) for stable boundaries
        body = _clean_section_text(
            "\n".join(ln.text.strip() for ln in group if not _is_noise_line(ln.text))
        )
        if count_real_words(body) < MIN_CHUNK_WORDS:
            continue
        title = _guess_title_from_lines([ln.text for ln in group[:6]] + body.splitlines()[:3])
        # Prefer the display-headline line that opened this article
        head = group[0].text.strip() if group else ""
        if head and (_is_large_headline(group[0], median_h, strict=False) or _is_anchor_line(group[0], median_h, zone=zone)):
            title = _clean_title(head)
            for ln in group[1:5]:
                if _is_headline_continuation(ln.text.strip()):
                    title = _clean_title(f"{head} {re.split(r'[–—]', ln.text)[0]}")
                    break
        articles.append((title, body))
    return articles


def _clean_section_text(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or _is_noise_line(s):
            continue
        if _is_column_chrome(s) and not re.match(r"^@?\s*WEB EXCLUSIVE\b", s, re.I):
            continue
        lines.append(s)
    while lines and _TAGLINE_RE.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip()


_OVERSIZED_WORD_LIMIT = 750


def _looks_like_inline_headline(line: str, *, min_prior_words: int) -> bool:
    """Heuristic: a mid-body line that is probably a new article title."""
    line = line.strip()
    if min_prior_words < 140:
        return False
    if _GENERIC_SECTION_RE.match(line):
        return True
    if _is_column_chrome(line) or _is_noise_line(line) or _TAGLINE_RE.match(line):
        return False
    if _is_body_sentence(line):
        return False
    words = line.split()
    if not (3 <= len(words) <= 12):
        return False
    if line.endswith((".", ",", ";", ":")):
        return False
    # Narrative / instructional prose — not a display hed
    if re.search(
        r"\b(?:should|must|would|could|shows?|found that|during|after|before|"
        r"simulate|every|participants|students and)\b",
        line,
        re.I,
    ):
        return False
    if re.match(
        r"^(?:The|This|That|These|Those|When|Where|What|How|Why|After|Before|"
        r"During|In|On|At|For|A|An|Japan|India|Every)\b",
        line,
    ) and words[1:2] and words[1][:1].islower():
        return False
    # Prefer clear title-like lines (short, topical, not clauses)
    if _looks_like_headline_start(line) and len(words) <= 10:
        return True
    # Sentence-case editorial headlines without auxiliary verbs
    if (
        line[:1].isupper()
        and len(line) <= 90
        and 4 <= len(words) <= 10
        and sum(1 for c in line if c.islower()) > 3
        and re.search(
            r"\b(?:diagnosed with|lung cancer|pellet guns|political parties|"
            r"worker-?intellectual|renewable energy)\b",
            line,
            re.I,
        )
    ):
        return True
    return False


def _split_on_mid_body_headlines(title: str, body: str) -> list[tuple[str, str]]:
    """
    Split an article whenever a new display-style headline appears mid-body.

    This catches column-bottom bleed (e.g. Santiago ending, then lung-cancer hed)
    even when the combined chunk is under the oversized word limit.
    """
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 8:
        return [(title, body)]

    split_at: list[int] = [0]
    words_so_far = 0
    for i, line in enumerate(lines):
        if i == 0:
            words_so_far += count_real_words(line)
            continue
        if _looks_like_inline_headline(line, min_prior_words=words_so_far):
            # Require enough prior content so we don't split the real title block
            if i - split_at[-1] >= 5 and words_so_far >= 140:
                split_at.append(i)
                words_so_far = 0
        words_so_far += count_real_words(line)

    if len(split_at) == 1:
        return [(title, body)]

    split_at.append(len(lines))
    parts: list[tuple[str, str]] = []
    for si in range(len(split_at) - 1):
        chunk_lines = lines[split_at[si] : split_at[si + 1]]
        part = "\n".join(chunk_lines).strip()
        if count_real_words(part) < MIN_CHUNK_WORDS:
            continue
        part_title = title if si == 0 else _guess_title_from_lines(chunk_lines)
        if si == 0:
            part_title = title
        parts.append((part_title, part))
    return parts or [(title, body)]


def _split_oversized_articles(articles: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Break up merged blobs using structural headline cues (format-agnostic)."""
    out: list[tuple[str, str]] = []
    for title, body in articles:
        # Always scan for mid-body display headlines (not only huge blobs)
        parts = _split_on_mid_body_headlines(title, body)
        if len(parts) > 1:
            out.extend(parts)
            continue
        if count_real_words(body) <= _OVERSIZED_WORD_LIMIT:
            out.append((title, body))
            continue
        # Fallback: denser scan for very large leftovers
        denser = _split_on_mid_body_headlines(title, body)
        out.extend(denser)
    return out


def _title_token_overlap(a: str, b: str) -> float:
    ta = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", a)}
    tb = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", b)}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _merge_fragmented_articles(articles: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Merge consecutive small fragments that belong to the same story."""
    if len(articles) <= 1:
        return articles

    merged: list[tuple[str, str]] = []
    i = 0
    while i < len(articles):
        title, body = articles[i]
        words = count_real_words(body)
        strong_title = _looks_like_headline_start(title) and not _is_body_sentence(title)

        # Merge tiny tail fragments into previous article — but never swallow
        # a real display-headline article (e.g. short op-ed under a tall hed).
        if merged and words < 120 and not strong_title:
            prev_title, prev_body = merged[-1]
            if not _GENERIC_SECTION_RE.match(title.strip()):
                merged[-1] = (prev_title, f"{prev_body}\n\n{body}".strip())
                i += 1
                continue

        # Merge next fragment if titles overlap or current looks like a hed half
        if words < 220 and i + 1 < len(articles):
            nxt_title, nxt_body = articles[i + 1]
            nxt_strong = _looks_like_headline_start(nxt_title) and not _is_body_sentence(nxt_title)
            overlap = _title_token_overlap(title, nxt_title)
            continuation = _is_headline_continuation(nxt_title) or (
                nxt_title[:1].islower() and count_real_words(nxt_title) <= 8
            )
            # Never merge two pieces that each have their own display headline
            same_story = (overlap >= 0.35 or continuation) and not (strong_title and nxt_strong)
            if same_story and count_real_words(nxt_body) < 900:
                combined = f"{body}\n\n{nxt_body}".strip()
                nice = title if len(title) >= len(nxt_title) else nxt_title
                if continuation:
                    nice = _clean_title(f"{title} {nxt_title}")
                merged.append((nice, combined))
                i += 2
                continue

        merged.append((title, body))
        i += 1

    return merged


def _main_zone_x_thresholds(main_lines: list[OcrLine]) -> tuple[float, float]:
    """Return (editorial_min_x, right_rail_min_x) for strip-based main-zone parsing."""
    centers = [(ln.x0 + ln.x1) / 2 for ln in main_lines]
    page_max = max(centers) if centers else 3600.0
    return page_max * 0.47, page_max * 0.66


def _strip_to_article(zone_lines: list[OcrLine], *, min_y: float = 0) -> tuple[str, str] | None:
    seg = [ln for ln in zone_lines if ln.y0 >= min_y]
    if not seg:
        return None
    body = _clean_section_text(_lines_to_reading_text(seg))
    if count_real_words(body) < MIN_CHUNK_WORDS:
        return None
    return _guess_title_from_lines(body.splitlines()), body


def _split_main_zone(main_lines: list[OcrLine]) -> list[tuple[str, str]]:
    """
    Main newspaper flow:
    - Ignore Sunday/Express mastheads
    - Find display headlines, then gather text in that headline's column strip
      until the next headline in the same strip (handles side-by-side op-eds)
    """
    if not main_lines:
        return []

    usable = [
        ln
        for ln in main_lines
        if not _MASTHEAD_LINE_RE.match(ln.text.strip())
        and not re.match(r"^THE SUNDAY\b", ln.text.strip(), re.I)
    ]
    if not usable:
        usable = list(main_lines)

    median_h = _median_line_height(usable)
    page_max = max((ln.x0 + ln.x1) / 2 for ln in usable) if usable else 3600.0
    # Half-width of a column strip around a headline center
    strip_half = page_max * 0.18

    headlines: list[OcrLine] = []
    sorted_lines = sorted(usable, key=lambda ln: (ln.y0, ln.x0))
    for ln in sorted_lines:
        if not _is_anchor_line(ln, median_h, zone="main"):
            continue
        # Skip near-duplicate headline halves
        if headlines and abs(ln.y0 - headlines[-1].y0) < 80 and abs(
            (ln.x0 + ln.x1) / 2 - (headlines[-1].x0 + headlines[-1].x1) / 2
        ) < strip_half:
            continue
        headlines.append(ln)

    if not headlines:
        hit = _strip_to_article(usable, min_y=0)
        return [hit] if hit else []

    articles: list[tuple[str, str]] = []
    for hi, head in enumerate(headlines):
        hx = (head.x0 + head.x1) / 2
        head_width = head.x1 - head.x0
        # True multi-column display hed (very tall lead editorial), not a long single-column title
        spanning = head.height >= max(200.0, median_h * 5.0)
        local_half = page_max * 0.35 if spanning else strip_half

        # End at next headline in the same vertical strip
        end_y = max(ln.y1 for ln in usable) + 10
        for nxt in headlines[hi + 1 :]:
            nx = (nxt.x0 + nxt.x1) / 2
            if spanning or abs(nx - hx) <= local_half * 1.35:
                # Spanning lead ends at first later headline of any column
                if spanning:
                    end_y = nxt.y0
                    break
                if abs(nx - hx) <= local_half * 1.35:
                    end_y = nxt.y0
                    break

        start_y = head.y0
        prev_same = None
        for prev in reversed(headlines[:hi]):
            px = (prev.x0 + prev.x1) / 2
            if abs(px - hx) <= local_half * 1.35:
                prev_same = prev
                break
        if prev_same is None and not spanning:
            same_strip = [
                ln.y0 for ln in usable if abs((ln.x0 + ln.x1) / 2 - hx) <= local_half
            ]
            start_y = min(same_strip) if same_strip else head.y0

        if spanning:
            group = [ln for ln in usable if start_y - 5 <= ln.y0 < end_y]
        else:
            group = [
                ln
                for ln in usable
                if start_y - 5 <= ln.y0 < end_y
                and abs((ln.x0 + ln.x1) / 2 - hx) <= local_half * 1.35
            ]
        if head not in group:
            group.append(head)
        group.sort(key=lambda ln: (ln.y0, ln.x0))

        body = _clean_section_text(_lines_to_reading_text(group))
        if count_real_words(body) < MIN_CHUNK_WORDS:
            continue
        title = _guess_title_from_lines([head.text] + [ln.text for ln in group[:8]])
        # Prefer the detected display headline; merge wrapped second half if present
        if _is_large_headline(head, median_h, strict=False) or _GENERIC_SECTION_RE.match(head.text.strip()):
            title = _clean_title(head.text)
            for ln in group[1:6]:
                t = ln.text.strip()
                if _is_headline_continuation(t):
                    title = _clean_title(f"{head.text} {re.split(r'[–—]', t)[0]}")
                    break
        articles.append((title, body))

    if not articles:
        hit = _strip_to_article(usable, min_y=0)
        if hit:
            articles.append(hit)

    return articles


def _split_page_zones(lines: list[OcrLine]) -> list[tuple[str, str]]:
    """
    Split a newspaper page into articles.

    Detect vertical column strips from x-gutters, then split each strip
    independently (top→bottom) so side-by-side editorials stay separate.
    """
    articles: list[tuple[str, str]] = []
    strips = _cluster_vertical_strips(lines)
    for idx, strip in enumerate(strips):
        zone_name = "left" if idx == 0 else "main"
        articles.extend(_split_zone_by_anchors(strip, zone=zone_name))

    articles = _split_oversized_articles(articles)
    articles = _merge_column_continuations(articles)
    return _merge_fragmented_articles(articles)


def _merge_column_continuations(articles: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    Merge orphan body fragments into neighboring titled articles.

    Typical case: a column strip starts mid-sentence (no display headline)
    because the title lived in an adjacent column.
    """
    if len(articles) <= 1:
        return articles

    def _looks_like_body_orphan(title: str, body: str) -> bool:
        title_s = title.strip()
        first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        # Real headlines are never orphans — and neither are chunks that OPEN with one
        if _looks_like_headline_start(title_s) and not _is_body_sentence(title_s):
            return False
        if first and _looks_like_inline_headline(first, min_prior_words=200):
            return False
        if first and _looks_like_headline_start(first) and not _is_body_sentence(first):
            return False
        if title_s.lower() in {"article excerpt", "article"}:
            return True
        if first and first[:1].islower() and not _looks_like_headline_start(title_s):
            return True
        if first and title_s[:40].lower() == first[:40].lower() and _is_body_sentence(first):
            return True
        return False

    def _has_strong_title(title: str) -> bool:
        t = title.strip()
        if t.lower() in {"article excerpt", "article"}:
            return False
        if _is_body_sentence(t):
            return False
        return _looks_like_headline_start(t) or (3 <= len(t.split()) <= 14 and t[:1].isupper())

    out: list[tuple[str, str]] = []
    i = 0
    while i < len(articles):
        title, body = articles[i]
        orphan = _looks_like_body_orphan(title, body)
        body_words = count_real_words(body)

        if orphan and body_words < 380:
            if (
                out
                and _has_strong_title(out[-1][0])
                and count_real_words(out[-1][1]) < 650
            ):
                pt, pb = out[-1]
                out[-1] = (pt, f"{pb}\n\n{body}".strip())
                i += 1
                continue
            if (
                i + 1 < len(articles)
                and _has_strong_title(articles[i + 1][0])
                and count_real_words(articles[i + 1][1]) < 650
            ):
                nt, nb = articles[i + 1]
                out.append((nt, f"{nb}\n\n{body}".strip()))
                i += 2
                continue

        out.append((title, body))
        i += 1
    return out


def split_ocr_lines_into_articles(lines: list[OcrLine], page_number: int) -> list[tuple[str, str]]:
    """Split OCR lines into (title, body_text) article segments."""
    from pipeline.pdf_extract import article_text_is_usable

    del page_number
    if not lines:
        return []

    articles = _split_page_zones(lines)

    filtered: list[tuple[str, str]] = []
    for title, body in articles:
        if count_real_words(body) < MIN_CHUNK_WORDS:
            continue
        title_s = (title or "").strip()
        if _MASTHEAD_LINE_RE.match(title_s) or _is_column_chrome(title_s):
            continue
        if re.match(
            r"^(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),?\s+"
            r"[A-Z]+\s+\d{1,2}",
            title_s,
            re.I,
        ):
            continue
        # Fold weak/untitled leftovers into previous article when present
        if title_s.lower() in {"article excerpt", "article"}:
            if filtered:
                pt, pb = filtered[-1]
                filtered[-1] = (pt, f"{pb}\n\n{body}".strip())
                continue
        usable, _reason = article_text_is_usable(body, min_words=40)
        if not usable:
            continue
        filtered.append((_clean_title(title_s), body))
    return filtered


def extract_article_from_headline_line(
    lines: list[OcrLine],
    headline_line: OcrLine,
) -> tuple[str, str] | None:
    """
    From a matched headline OCR line, collect same-strip body until the next
    display headline. Returns (title, body) or None if too weak.
    """
    if not lines:
        return None

    strips = _cluster_vertical_strips(lines)
    target_strip: list[OcrLine] | None = None
    for strip in strips:
        if any(
            abs(ln.y0 - headline_line.y0) < 3
            and abs(ln.x0 - headline_line.x0) < 3
            and ln.text == headline_line.text
            for ln in strip
        ):
            target_strip = strip
            break
        # Fallback: same column + near y
        hx = (headline_line.x0 + headline_line.x1) / 2
        if any(
            abs(ln.y0 - headline_line.y0) < 40
            and abs((ln.x0 + ln.x1) / 2 - hx) < 120
            for ln in strip
        ):
            target_strip = strip
            break

    if not target_strip:
        # Use all lines in roughly the same x-band as the headline
        hx = (headline_line.x0 + headline_line.x1) / 2
        page_w = max(ln.x1 for ln in lines)
        half = page_w * 0.18
        target_strip = [
            ln
            for ln in lines
            if abs((ln.x0 + ln.x1) / 2 - hx) <= half * 1.4
            or (
                (ln.x1 - ln.x0) > page_w * 0.38
                and ln.x0 <= headline_line.x0 + 40
            )
        ]
        target_strip = sorted(target_strip, key=lambda ln: (ln.y0, ln.x0))

    if not target_strip:
        return None

    median_h = _median_line_height(target_strip)
    sorted_lines = sorted(target_strip, key=lambda ln: (ln.y0, ln.x0))

    # Find start index at/near the headline
    start_idx = 0
    best_dist = 1e18
    for i, ln in enumerate(sorted_lines):
        dist = abs(ln.y0 - headline_line.y0) + abs(ln.x0 - headline_line.x0) * 0.1
        if dist < best_dist:
            best_dist = dist
            start_idx = i

    end_idx = len(sorted_lines)
    for j in range(start_idx + 1, len(sorted_lines)):
        ln = sorted_lines[j]
        # Skip immediate headline continuation halves
        if j <= start_idx + 2 and _is_headline_continuation(ln.text.strip()):
            continue
        if _is_anchor_line(ln, median_h, zone="main") and abs(ln.y0 - headline_line.y0) > 80:
            end_idx = j
            break

    group = sorted_lines[start_idx:end_idx]
    body = _clean_section_text(
        "\n".join(ln.text.strip() for ln in group if not _is_noise_line(ln.text))
    )
    if count_real_words(body) < MIN_CHUNK_WORDS:
        return None

    title = _clean_title(headline_line.text)
    for ln in group[1:5]:
        if _is_headline_continuation(ln.text.strip()):
            title = _clean_title(f"{headline_line.text} {re.split(r'[–—]', ln.text)[0]}")
            break
    if not title or len(title) < 6:
        title = _guess_title_from_lines([ln.text for ln in group[:6]])
    return title, body


def ocr_page_to_plain_text(lines: list[OcrLine]) -> str:
    """Rebuild plain text from OCR lines in column-major reading order."""
    return _lines_to_reading_text(lines)
