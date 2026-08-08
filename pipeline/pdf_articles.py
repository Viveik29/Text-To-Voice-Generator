"""Detect and extract individual news articles from multi-article PDF pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

import fitz  # PyMuPDF
from rapidfuzz import fuzz

from pipeline.pdf_extract import (
    count_real_words,
    extract_document_text,
    extract_page_text,
    get_ocr_lines,
    is_pdf_readable,
    readable_ratio as _readable_ratio,
    unreadable_pdf_message,
)
from pipeline.ocr_layout import MIN_ARTICLE_WORDS, MIN_CHUNK_WORDS, split_ocr_lines_into_articles

MIN_MATCH_SCORE = 38
MAX_PAGES = 50
HEADLINE_MAX_LEN = 140
GAP_SPLIT_THRESHOLD = 22.0
MIN_READABLE_RATIO = 0.52


@dataclass
class ArticleChunk:
    """A candidate article segment extracted from a PDF page."""

    title_guess: str
    text: str
    page: int  # 1-indexed
    score: float = 0.0

    @property
    def preview(self) -> str:
        snippet = self.text.replace("\n", " ").strip()
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        return snippet

    @property
    def label(self) -> str:
        title = self.title_guess if _readable_ratio(self.title_guess) >= MIN_READABLE_RATIO else self.preview[:80]
        return f"p.{self.page} · {title[:90]}"


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text) if len(w) > 2]


def extract_text_from_pdf(path: Path, *, max_pages: int = MAX_PAGES, force_ocr: bool = False) -> str:
    """Return full cleaned text from a PDF (all pages)."""
    text, _method = extract_document_text(path, max_pages=max_pages, force_ocr=force_ocr)
    if not text:
        raise ValueError(unreadable_pdf_message())
    return text


def _guess_title(text: str, fallback: str = "Article excerpt") -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 8 and _readable_ratio(line) >= MIN_READABLE_RATIO:
            if len(line) > HEADLINE_MAX_LEN:
                return line[: HEADLINE_MAX_LEN - 3] + "..."
            return line
    return fallback


def _looks_like_new_headline(line: str) -> bool:
    line = line.strip()
    if len(line) < 12 or len(line) > HEADLINE_MAX_LEN:
        return False
    if _readable_ratio(line) < MIN_READABLE_RATIO:
        return False
    alpha = re.sub(r"[^A-Za-z]", "", line)
    if not alpha:
        return False
    upper_ratio = sum(1 for c in alpha if c.isupper()) / len(alpha)
    return upper_ratio > 0.65 or (line.istitle() and len(line.split()) <= 12)


def _slice_article_from_index(text: str, start: int) -> str:
    """Extract one article starting at character offset."""
    rest = text[start:]
    lines = rest.splitlines()
    collected: list[str] = []
    char_count = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if i > 2 and char_count > 400 and _looks_like_new_headline(stripped):
            break
        collected.append(line)
        char_count += len(line) + 1
        if char_count > 14_000:
            break

    return "\n".join(collected).strip()


def _selector_variants(selector: str) -> list[str]:
    """Generate progressively shorter match phrases."""
    selector = selector.strip()
    variants = [selector]
    words = selector.split()
    if len(words) > 6:
        variants.append(" ".join(words[:8]))
        variants.append(" ".join(words[:5]))
    # Distinctive phrases (numbers + proper nouns)
    key_phrases = re.findall(r"[0-9][0-9A-Za-z-]*|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", selector)
    variants.extend(key_phrases)
    tokens = _tokenize(selector)
    if len(tokens) >= 3:
        variants.append(" ".join(tokens[:4]))
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def find_article_by_selector(page_text: str, selector: str, page: int) -> ArticleChunk | None:
    """Locate article by headline/keywords in readable page text."""
    if not page_text or not selector.strip():
        return None

    if _readable_ratio(page_text) < 0.35:
        return None

    lowered_page = page_text.lower()

    for variant in _selector_variants(selector):
        v_lower = variant.lower()
        idx = lowered_page.find(v_lower)

        if idx < 0:
            words = variant.split()
            if len(words) >= 2:
                pattern = r"\s+".join(re.escape(w) for w in words)
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    idx = match.start()

        if idx >= 0:
            article_text = _slice_article_from_index(page_text, idx)
            if len(article_text) >= 80:
                return ArticleChunk(
                    title_guess=_guess_title(article_text, fallback=variant[:HEADLINE_MAX_LEN]),
                    text=article_text,
                    page=page,
                    score=100.0,
                )

    # Token overlap on lines — match headline even if split across spans
    sel_tokens = set(_tokenize(selector))
    if len(sel_tokens) < 2:
        return None

    best_line_idx = -1
    best_overlap = 0.0
    lines = page_text.splitlines()
    for i, line in enumerate(lines):
        if _readable_ratio(line) < MIN_READABLE_RATIO:
            continue
        line_tokens = set(_tokenize(line))
        if not line_tokens:
            continue
        overlap = len(sel_tokens & line_tokens) / len(sel_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_line_idx = i

    if best_line_idx >= 0 and best_overlap >= 0.45:
        start_offset = sum(len(lines[j]) + 1 for j in range(best_line_idx))
        article_text = _slice_article_from_index(page_text, start_offset)
        if len(article_text) >= 80:
            return ArticleChunk(
                title_guess=_guess_title(article_text, fallback=selector[:HEADLINE_MAX_LEN]),
                text=article_text,
                page=page,
                score=best_overlap * 100,
            )

    return None


def search_pdf_by_headline(
    path: Path,
    selector: str,
    *,
    page_number: int | None = None,
    max_pages: int = MAX_PAGES,
    force_ocr: bool = False,
) -> ArticleChunk | None:
    """Search PDF pages for an article by headline/keywords using readable text."""
    doc = fitz.open(path)
    try:
        if page_number and page_number > 0:
            indices = [page_number - 1]
        else:
            indices = list(range(min(len(doc), max_pages)))
    finally:
        doc.close()

    best: ArticleChunk | None = None
    for idx in indices:
        if idx < 0:
            continue
        page_text, _method = extract_page_text(path, idx, force_ocr=force_ocr)
        hit = find_article_by_selector(page_text, selector, idx + 1)
        if hit and (best is None or hit.score > best.score):
            best = hit
    return best


def fetch_article_by_headline(
    path: Path,
    headline: str,
    *,
    page_number: int | None = 1,
    force_ocr: bool = True,
    max_pages: int = MAX_PAGES,
) -> ArticleChunk:
    """
    Find a user-supplied headline via OCR line boxes and extract that article only.

    Raises ValueError with a clear message when not found or quality is too low.
    """
    from pipeline.ocr_layout import extract_article_from_headline_line
    from pipeline.pdf_extract import article_text_is_usable
    from pipeline.text_clean import clean_ocr_text

    selector = (headline or "").strip()
    if len(selector) < 4:
        raise ValueError("Enter a longer headline (at least a few words).")

    doc = fitz.open(path)
    try:
        if page_number and page_number > 0:
            indices = [page_number - 1]
        else:
            indices = list(range(min(len(doc), max_pages)))
    finally:
        doc.close()

    best_chunk: ArticleChunk | None = None
    best_score = 0.0
    selector_l = selector.lower()

    for idx in indices:
        if idx < 0:
            continue
        # Prefer OCR layout for newspaper PDFs
        lines = get_ocr_lines(path, idx) if force_ocr else []
        if not lines and force_ocr:
            lines = get_ocr_lines(path, idx)

        if lines:
            for ln in lines:
                text = ln.text.strip()
                if len(text) < 6:
                    continue
                score = max(
                    fuzz.partial_ratio(selector_l, text.lower()),
                    fuzz.token_set_ratio(selector_l, text.lower()),
                    fuzz.WRatio(selector_l, text.lower()),
                )
                # Boost when selector tokens appear in the OCR line
                sel_toks = set(_tokenize(selector))
                line_toks = set(_tokenize(text))
                if sel_toks:
                    overlap = len(sel_toks & line_toks) / len(sel_toks)
                    score = max(score, overlap * 100)
                if score < 55:
                    continue
                extracted = extract_article_from_headline_line(lines, ln)
                if not extracted:
                    continue
                title, body = extracted
                body = clean_ocr_text(body)
                usable, _reason = article_text_is_usable(body, min_words=40)
                if not usable:
                    continue
                if score > best_score:
                    best_score = score
                    best_chunk = ArticleChunk(
                        title_guess=title,
                        text=body,
                        page=idx + 1,
                        score=score,
                    )

        # Fallback: plain-text headline search on this page
        if best_chunk is None or best_score < 70:
            page_text, _method = extract_page_text(path, idx, force_ocr=force_ocr)
            hit = find_article_by_selector(page_text, selector, idx + 1)
            if hit and hit.score >= best_score:
                body = clean_ocr_text(hit.text)
                usable, reason = article_text_is_usable(body, min_words=40)
                if usable:
                    best_score = hit.score
                    best_chunk = ArticleChunk(
                        title_guess=hit.title_guess,
                        text=body,
                        page=hit.page,
                        score=hit.score,
                    )
                elif best_chunk is None:
                    raise ValueError(
                        f"Found text near '{selector}' but extract quality is too low. {reason} "
                        "Try paste fallback or a clearer headline."
                    )

    if best_chunk is None:
        raise ValueError(
            f"Headline not found: '{selector}'. "
            "Check spelling, try fewer keywords, set the correct page, enable OCR, "
            "or paste the article text."
        )

    usable, reason = article_text_is_usable(best_chunk.text, min_words=40)
    if not usable:
        raise ValueError(
            f"Headline matched but extract is not usable. {reason} "
            "Paste the article text instead."
        )
    return best_chunk


def _page_blocks(page: fitz.Page) -> list[dict]:
    """Extract positioned text blocks with font metadata."""
    blocks: list[dict] = []
    data = page.get_text("dict")
    page_width = page.rect.width

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue

        parts: list[str] = []
        max_size = 0.0
        bold = False
        bbox = block.get("bbox", (0, 0, 0, 0))

        for line in block.get("lines", []):
            line_parts = []
            for span in line.get("spans", []):
                text = span.get("text", "").replace("\n", " ").strip()
                if not text:
                    continue
                line_parts.append(text)
                max_size = max(max_size, float(span.get("size", 0)))
                if int(span.get("flags", 0)) & 16:
                    bold = True
            if line_parts:
                parts.append(" ".join(line_parts))

        text = "\n".join(parts).strip()
        if not text or len(text) < 3:
            continue
        if _readable_ratio(text) < 0.35:
            continue

        x0 = float(bbox[0])
        column = 0 if x0 < page_width * 0.48 else 1
        blocks.append(
            {
                "text": text,
                "x0": x0,
                "y0": float(bbox[1]),
                "x1": float(bbox[2]),
                "y1": float(bbox[3]),
                "font_size": max_size,
                "bold": bold,
                "column": column,
            }
        )

    blocks.sort(key=lambda b: (b["column"], b["y0"], b["x0"]))
    return blocks


def _median_font_size(blocks: list[dict]) -> float:
    sizes = [b["font_size"] for b in blocks if b["font_size"] > 0]
    if not sizes:
        return 10.0
    sizes.sort()
    return sizes[len(sizes) // 2]


def _is_headline(block: dict, median_size: float) -> bool:
    text = block["text"].strip()
    if len(text) > HEADLINE_MAX_LEN or _readable_ratio(text) < MIN_READABLE_RATIO:
        return False

    alpha = re.sub(r"[^A-Za-z]", "", text)
    uppercase_ratio = sum(1 for c in alpha if c.isupper()) / max(len(alpha), 1)

    if block["bold"] and len(text) < 100:
        return True
    if block["font_size"] >= median_size + 1.2 and len(text) < 100:
        return True
    if uppercase_ratio > 0.75 and len(text) < 80:
        return True
    if text.endswith(":") and len(text) < 90:
        return True
    return False


def _blocks_to_articles(blocks: list[dict]) -> list[str]:
    """Group blocks into article text segments."""
    if not blocks:
        return []

    median_size = _median_font_size(blocks)
    articles: list[list[dict]] = []
    current: list[dict] = []

    for block in blocks:
        if current:
            prev = current[-1]
            gap = block["y0"] - prev["y1"]
            new_column = block["column"] != prev["column"]
            new_article = _is_headline(block, median_size) or (
                gap > GAP_SPLIT_THRESHOLD and len(current) > 1
            )
            if new_article and not new_column:
                articles.append(current)
                current = [block]
                continue
            if new_column and gap > GAP_SPLIT_THRESHOLD * 1.5 and len(" ".join(b["text"] for b in current)) > 200:
                articles.append(current)
                current = [block]
                continue

        current.append(block)

    if current:
        articles.append(current)

    texts: list[str] = []
    for group in articles:
        merged = "\n\n".join(b["text"] for b in group).strip()
        if len(merged) >= 80 and _readable_ratio(merged) >= MIN_READABLE_RATIO:
            texts.append(merged)

    if not texts and blocks:
        merged = "\n\n".join(b["text"] for b in blocks).strip()
        if _readable_ratio(merged) >= MIN_READABLE_RATIO:
            texts.append(merged)

    return texts


def split_plain_text_into_articles(page_text: str, page_number: int) -> list[ArticleChunk]:
    """Split readable plain text into articles by paragraph/headline boundaries."""
    paragraphs = re.split(r"\n\s*\n+", page_text.strip())
    if not paragraphs:
        return []

    segments: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        seg = "\n\n".join(current).strip()
        if len(seg) >= 80 and _readable_ratio(seg) >= MIN_READABLE_RATIO:
            segments.append(seg)

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        first_line = para.splitlines()[0].strip()
        if current and _looks_like_new_headline(first_line):
            flush()
            current = [para]
        else:
            current.append(para)
    flush()

    if not segments:
        if _readable_ratio(page_text) >= MIN_READABLE_RATIO:
            segments = [page_text.strip()]

    return [
        ArticleChunk(title_guess=_guess_title(seg), text=seg, page=page_number)
        for seg in segments
    ]


def split_page_into_articles(
    path: Path,
    page_index: int,
    *,
    force_ocr: bool = False,
) -> list[ArticleChunk]:
    """
    Split one PDF page into candidate article chunks.

    Tries, in order:
      1. Layout OCR (when forced, or text layer is unreadable / custom fonts)
      2. Native PDF text blocks (digital newspapers)
      3. Plain-text heuristic split
      4. Whole page as a single article (reports, letters, single-column PDFs)
    """
    page_number = page_index + 1

    def _from_ocr() -> list[ArticleChunk]:
        ocr_lines = get_ocr_lines(path, page_index)
        if not ocr_lines:
            return []
        segments = split_ocr_lines_into_articles(ocr_lines, page_number)
        return _dedupe_chunks(
            [
                ArticleChunk(title_guess=title, text=body, page=page_number)
                for title, body in segments
                if count_real_words(body) >= MIN_CHUNK_WORDS
            ]
        )

    # 1) OCR when requested
    if force_ocr:
        chunks = _from_ocr()
        if chunks:
            return chunks

    # 2) Native block geometry (works for many digital PDFs)
    doc = fitz.open(path)
    try:
        page = doc[page_index]
        blocks = _page_blocks(page)
        block_segments = _blocks_to_articles(blocks)
        block_chunks = _dedupe_chunks(
            [
                ArticleChunk(title_guess=_guess_title(seg), text=seg, page=page_number)
                for seg in block_segments
                if count_real_words(seg) >= MIN_CHUNK_WORDS
            ]
        )
    finally:
        doc.close()

    plain, method = extract_page_text(
        path, page_index, force_ocr=force_ocr, ocr_mode="fast" if force_ocr else "auto"
    )
    plain_ratio = _readable_ratio(plain) if plain else 0.0

    # 3) Unreadable / OCR-derived text → layout OCR
    if method.startswith("ocr") or plain_ratio < MIN_READABLE_RATIO:
        chunks = _from_ocr()
        if chunks:
            return chunks

    # 4) Prefer multi-article native blocks when they look healthy
    if len(block_chunks) > 1 and all(_readable_ratio(c.text) >= MIN_READABLE_RATIO for c in block_chunks):
        return block_chunks

    # 5) Plain-text headline split
    plain_chunks = split_plain_text_into_articles(plain, page_number) if plain else []
    if len(plain_chunks) > 1:
        return _dedupe_chunks(plain_chunks)

    # 6) Single usable chunk (letter, report, single-column article)
    if block_chunks and _readable_ratio(block_chunks[0].text) >= MIN_READABLE_RATIO:
        return block_chunks[:1]
    if plain_chunks and _readable_ratio(plain_chunks[0].text) >= MIN_READABLE_RATIO:
        return plain_chunks[:1]
    if plain and plain_ratio >= MIN_READABLE_RATIO:
        return [ArticleChunk(title_guess=_guess_title(plain), text=plain, page=page_number)]

    # 7) Last resort: OCR even when text layer looked "ok" but produced nothing useful
    chunks = _from_ocr()
    if chunks:
        return chunks
    return plain_chunks if plain_chunks else block_chunks


def _dedupe_chunks(chunks: list[ArticleChunk]) -> list[ArticleChunk]:
    """Remove duplicate or near-duplicate article chunks."""
    unique: list[ArticleChunk] = []
    seen: set[str] = set()
    for chunk in chunks:
        if _readable_ratio(chunk.text) < 0.35:
            continue
        if count_real_words(chunk.text) < MIN_CHUNK_WORDS:
            continue
        key = chunk.text[:200].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


@dataclass
class PdfInspection:
    """Summary of a scanned PDF for the UI."""

    page_count: int
    pages_scanned: int
    article_count: int
    articles: list[ArticleChunk]
    articles_by_page: dict[int, int]
    readable: bool
    readable_ratio: float
    extraction_method: str


def get_pdf_page_count(path: Path) -> int:
    """Return total number of pages in a PDF."""
    doc = fitz.open(path)
    try:
        return len(doc)
    finally:
        doc.close()


def inspect_pdf(
    path: Path,
    *,
    page_number: int | None = None,
    max_pages: int = MAX_PAGES,
    force_ocr: bool = False,
    save_txt: bool = True,
    txt_folder_name: str | None = None,
) -> PdfInspection:
    """Scan a PDF and return page count plus detected article candidates.

    When save_txt=True (default), also writes clean article TXT files under
    extracted_txt/<pdf_stem>/ for LLM input.
    """
    page_count = get_pdf_page_count(path)
    pages_scanned = 1 if page_number and page_number > 0 else min(page_count, max_pages)

    if save_txt:
        from pipeline.article_store import extract_pdf_to_txt_folder

        _folder, _saved, articles, _skipped = extract_pdf_to_txt_folder(
            path,
            page_number=page_number,
            force_ocr=force_ocr,
            max_pages=max_pages,
            folder_name=txt_folder_name,
        )
    else:
        articles = detect_articles_from_pdf(
            path,
            page_number=page_number,
            max_pages=max_pages,
            force_ocr=force_ocr,
        )
        # Still drop unusable chunks when not saving
        from pipeline.pdf_extract import article_text_is_usable

        articles = [c for c in articles if article_text_is_usable(c.text, min_words=40)[0]]

    articles_by_page: dict[int, int] = {}
    for chunk in articles:
        articles_by_page[chunk.page] = articles_by_page.get(chunk.page, 0) + 1

    scan_page = page_number if page_number and page_number > 0 else 1
    readable, ratio, method = is_pdf_readable(path, scan_page if page_count else None)
    if force_ocr and method.startswith("ocr"):
        readable = True

    return PdfInspection(
        page_count=page_count,
        pages_scanned=pages_scanned,
        article_count=len(articles),
        articles=articles,
        articles_by_page=articles_by_page,
        readable=readable,
        readable_ratio=ratio,
        extraction_method=method,
    )


def detect_articles_from_pdf(
    path: Path,
    *,
    page_number: int | None = None,
    max_pages: int = MAX_PAGES,
    force_ocr: bool = False,
) -> list[ArticleChunk]:
    """Detect article candidates across the PDF or on one page."""
    doc = fitz.open(path)
    try:
        if page_number and page_number > 0:
            page_indices = [page_number - 1]
        else:
            page_indices = range(min(len(doc), max_pages))
    finally:
        doc.close()

    chunks: list[ArticleChunk] = []
    for idx in page_indices:
        if idx < 0:
            continue
        chunks.extend(split_page_into_articles(path, idx, force_ocr=force_ocr))

    return _dedupe_chunks(chunks)


def score_chunk(chunk: ArticleChunk, selector: str) -> float:
    """Score how well a chunk matches the user's article description."""
    selector = selector.strip().lower()
    if not selector:
        return 0.0

    haystack = f"{chunk.title_guess}\n{chunk.text[:2000]}".lower()
    return max(
        fuzz.partial_ratio(selector, haystack),
        fuzz.token_set_ratio(selector, haystack),
        fuzz.WRatio(selector, haystack),
        fuzz.partial_token_set_ratio(selector, haystack),
    )


def rank_articles(chunks: list[ArticleChunk], selector: str) -> list[ArticleChunk]:
    """Return chunks sorted by match score (descending)."""
    scored = [replace(chunk, score=score_chunk(chunk, selector)) for chunk in chunks]
    return sorted(scored, key=lambda c: c.score, reverse=True)


def select_best_article(
    chunks: list[ArticleChunk],
    selector: str,
    *,
    min_score: float = MIN_MATCH_SCORE,
) -> ArticleChunk:
    """Pick the best matching article or raise with suggestions."""
    if not chunks:
        raise ValueError("No articles detected in the PDF. Try a different page or paste the text instead.")

    if not selector.strip():
        if len(chunks) == 1:
            return chunks[0]
        titles = "\n".join(f"  • {c.label}" for c in chunks[:8])
        raise ValueError(
            "Multiple articles found. Specify which article to analyze, or pick one from the detected list.\n"
            f"Detected:\n{titles}"
        )

    ranked = rank_articles(chunks, selector)
    best = ranked[0]

    if best.score < min_score:
        if chunks and all(_readable_ratio(c.text) < MIN_READABLE_RATIO for c in chunks):
            raise ValueError(unreadable_pdf_message())

        readable = [c for c in ranked if _readable_ratio(c.text) >= MIN_READABLE_RATIO]
        suggestions = "\n".join(f"  • {c.label} (match {c.score:.0f}%)" for c in (readable or ranked)[:5])
        raise ValueError(
            f"No article matched '{selector}' confidently (best score {best.score:.0f}%).\n"
            f"Try shorter keywords (e.g. '850-seat Lok Sabha'), another page number, or pick from detected articles:\n{suggestions}"
        )

    return best


def detect_articles_from_text(text: str) -> list[ArticleChunk]:
    """Split pasted text into article candidates using paragraph/headline heuristics."""
    return split_plain_text_into_articles(text, 1) or [
        ArticleChunk(title_guess=_guess_title(text), text=text.strip(), page=1)
    ]


def extract_filtered_article(
    path: Path,
    *,
    article_selector: str,
    page_number: int | None = None,
    chunk_override: ArticleChunk | None = None,
    force_ocr: bool = False,
) -> tuple[str, ArticleChunk, list[ArticleChunk]]:
    """
    Extract only the requested article text from a PDF.

    Returns:
        filtered_text, selected_chunk, all_detected_chunks
    """
    if chunk_override is not None:
        return chunk_override.text.strip(), chunk_override, [chunk_override]

    selector = article_selector.strip()

    # Auto-enable OCR when text layer is unreadable
    if not force_ocr:
        ok, _ratio, _method = is_pdf_readable(path, page_number)
        if not ok:
            force_ocr = True

    # 1) Direct headline/keyword search in readable page text (best for newspaper PDFs)
    if selector:
        headline_hit = search_pdf_by_headline(
            path, selector, page_number=page_number, force_ocr=force_ocr
        )
        if headline_hit and headline_hit.score >= 45:
            all_chunks = detect_articles_from_pdf(path, page_number=page_number, force_ocr=force_ocr)
            return headline_hit.text.strip(), headline_hit, all_chunks

        if page_number:
            headline_hit = search_pdf_by_headline(path, selector, page_number=None, force_ocr=force_ocr)
            if headline_hit and headline_hit.score >= 45:
                all_chunks = detect_articles_from_pdf(path, page_number=page_number, force_ocr=force_ocr)
                return headline_hit.text.strip(), headline_hit, all_chunks

    all_chunks = detect_articles_from_pdf(path, page_number=page_number, force_ocr=force_ocr)

    if page_number and page_number > 0 and not all_chunks:
        all_chunks = detect_articles_from_pdf(path, page_number=None)

    if page_number and page_number > 0 and selector:
        page_chunks = [c for c in all_chunks if c.page == page_number]
        search_pool = page_chunks if page_chunks else all_chunks
    else:
        search_pool = all_chunks

    # 2) Re-score chunks; also try headline search on each chunk's page text as fallback
    if selector and search_pool:
        ranked = rank_articles(search_pool, selector)
        if ranked and ranked[0].score >= MIN_MATCH_SCORE:
            return ranked[0].text.strip(), ranked[0], all_chunks

    # 3) Last resort: headline search with lower threshold
    if selector:
        headline_hit = search_pdf_by_headline(
            path, selector, page_number=page_number or None, force_ocr=force_ocr
        )
        if headline_hit:
            return headline_hit.text.strip(), headline_hit, all_chunks

    if not search_pool:
        raise ValueError(unreadable_pdf_message())

    selected = select_best_article(search_pool, selector)
    return selected.text.strip(), selected, all_chunks
