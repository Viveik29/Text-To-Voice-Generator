"""Save detected PDF articles as clean TXT files for LLM input."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pipeline.pdf_articles import ArticleChunk, detect_articles_from_pdf
from pipeline.pdf_extract import article_text_is_usable, count_real_words
from pipeline.text_clean import (
    clean_ocr_text,
    extract_body_from_txt,
    extract_title_from_txt,
    format_article_txt,
    slugify_title,
)

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_TXT_DIR = ROOT / "extracted_txt"


@dataclass
class SavedArticle:
    index: int
    title: str
    path: Path
    page: int
    word_count: int

    @property
    def label(self) -> str:
        return f"{self.index:02d}. p.{self.page} · {self.title[:90]} (~{self.word_count:,} words)"


@dataclass
class SkippedArticle:
    title: str
    page: int
    reason: str
    word_count: int = 0


def pdf_extract_folder(pdf_path: Path, *, folder_name: str | None = None) -> Path:
    """Folder for one PDF's extracted article TXT files."""
    stem = folder_name or pdf_path.stem
    stem = re.sub(r"[^\w.\-]+", "_", stem).strip("_") or "pdf"
    # Drop Streamlit preview prefix if present
    if stem.startswith("_preview_"):
        stem = stem[len("_preview_") :]
    return EXTRACTED_TXT_DIR / stem


def save_articles_as_txt(
    pdf_path: Path,
    articles: list[ArticleChunk],
    *,
    clear_existing: bool = True,
    folder_name: str | None = None,
) -> tuple[list[SavedArticle], list[SkippedArticle]]:
    """
    Write each usable article as a clean TXT file under extracted_txt/<pdf_stem>/.

    Low-quality / garbled chunks are skipped (not forced into the selectable list).
    Returns (saved, skipped).
    """
    out_dir = pdf_extract_folder(pdf_path, folder_name=folder_name)
    if clear_existing and out_dir.exists():
        for old in out_dir.glob("*.txt"):
            old.unlink()
        index_path = out_dir / "index.json"
        if index_path.exists():
            index_path.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    saved: list[SavedArticle] = []
    skipped: list[SkippedArticle] = []
    index_rows: list[dict] = []
    skip_rows: list[dict] = []
    next_index = 1

    for chunk in articles:
        title = (chunk.title_guess or "Article").strip()
        body = clean_ocr_text(chunk.text)
        words = count_real_words(body)

        # Prefer cleaned first line as title when OCR title is junk
        first = body.splitlines()[0].strip() if body else ""
        if first and (count_real_words(title) < 3 or len(title) < 8):
            title = first[:140]

        usable, reason = article_text_is_usable(body, min_words=40)
        if not usable:
            skipped.append(
                SkippedArticle(
                    title=title[:120] or "Untitled",
                    page=chunk.page,
                    reason=reason,
                    word_count=words,
                )
            )
            skip_rows.append(
                {
                    "title": title[:120] or "Untitled",
                    "page": chunk.page,
                    "reason": reason,
                    "words": words,
                }
            )
            continue

        content = format_article_txt(
            title=title,
            body=body,
            page=chunk.page,
            source_pdf=pdf_path.name,
            article_index=next_index,
        )
        final_title = extract_title_from_txt(content)
        slug = slugify_title(final_title)
        filename = f"{next_index:02d}_{slug}.txt"
        path = out_dir / filename
        path.write_text(content, encoding="utf-8")

        final_words = count_real_words(extract_body_from_txt(content))
        saved.append(
            SavedArticle(
                index=next_index,
                title=final_title,
                path=path,
                page=chunk.page,
                word_count=final_words,
            )
        )
        index_rows.append(
            {
                "index": next_index,
                "title": final_title,
                "file": filename,
                "page": chunk.page,
                "words": final_words,
            }
        )
        next_index += 1

    (out_dir / "index.json").write_text(
        json.dumps(
            {
                "source_pdf": pdf_path.name,
                "article_count": len(saved),
                "skipped_count": len(skipped),
                "articles": index_rows,
                "skipped": skip_rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        f"Source: {pdf_path.name}",
        f"Articles saved: {len(saved)}",
        f"Skipped (low quality): {len(skipped)}",
        "",
    ]
    for row in index_rows:
        lines.append(f"{row['index']:02d}. {row['title']}  [{row['file']}] (~{row['words']} words)")
    if skip_rows:
        lines.append("")
        lines.append("Skipped:")
        for row in skip_rows:
            lines.append(f"  - p.{row['page']} · {row['title']} — {row['reason']}")
    (out_dir / "00_INDEX.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return saved, skipped


def save_single_article_txt(
    pdf_path: Path,
    chunk: ArticleChunk,
    *,
    folder_name: str | None = None,
    clear_existing: bool = False,
) -> SavedArticle:
    """Save one headline-fetched article as TXT (optionally append to folder)."""
    if clear_existing:
        saved, skipped = save_articles_as_txt(
            pdf_path,
            [chunk],
            clear_existing=True,
            folder_name=folder_name,
        )
        if not saved:
            reason = skipped[0].reason if skipped else "Extract failed quality check."
            raise ValueError(reason)
        return saved[0]

    # Append alongside any existing extracts
    existing = list_saved_articles(pdf_path, folder_name=folder_name)
    out_dir = pdf_extract_folder(pdf_path, folder_name=folder_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    title = (chunk.title_guess or "Article").strip()
    body = clean_ocr_text(chunk.text)
    usable, reason = article_text_is_usable(body, min_words=40)
    if not usable:
        raise ValueError(reason)

    next_index = max((s.index for s in existing), default=0) + 1
    content = format_article_txt(
        title=title,
        body=body,
        page=chunk.page,
        source_pdf=pdf_path.name,
        article_index=next_index,
    )
    final_title = extract_title_from_txt(content)
    slug = slugify_title(final_title)
    filename = f"{next_index:02d}_{slug}.txt"
    path = out_dir / filename
    path.write_text(content, encoding="utf-8")
    words = count_real_words(extract_body_from_txt(content))
    new_item = SavedArticle(
        index=next_index,
        title=final_title,
        path=path,
        page=chunk.page,
        word_count=words,
    )

    # Refresh index.json
    all_saved = existing + [new_item]
    skipped = list_skipped_articles(pdf_path, folder_name=folder_name)
    index_rows = [
        {
            "index": s.index,
            "title": s.title,
            "file": s.path.name,
            "page": s.page,
            "words": s.word_count,
        }
        for s in all_saved
    ]
    skip_rows = [
        {"title": s.title, "page": s.page, "reason": s.reason, "words": s.word_count}
        for s in skipped
    ]
    (out_dir / "index.json").write_text(
        json.dumps(
            {
                "source_pdf": pdf_path.name,
                "article_count": len(all_saved),
                "skipped_count": len(skipped),
                "articles": index_rows,
                "skipped": skip_rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return new_item


def extract_pdf_to_txt_folder(
    pdf_path: Path,
    *,
    page_number: int | None = None,
    force_ocr: bool = True,
    max_pages: int = 50,
    folder_name: str | None = None,
) -> tuple[Path, list[SavedArticle], list[ArticleChunk], list[SkippedArticle]]:
    """Detect articles from PDF, clean them, and save usable ones under extracted_txt/."""
    chunks = detect_articles_from_pdf(
        pdf_path,
        page_number=page_number,
        max_pages=max_pages,
        force_ocr=force_ocr,
    )
    cleaned_chunks: list[ArticleChunk] = []
    for chunk in chunks:
        body = clean_ocr_text(chunk.text)
        title = chunk.title_guess
        first = body.splitlines()[0].strip() if body else ""
        if first and count_real_words(title) < 3:
            title = first[:140]
        cleaned_chunks.append(
            ArticleChunk(
                title_guess=title,
                text=body,
                page=chunk.page,
                score=chunk.score,
            )
        )

    stem = folder_name or pdf_path.name
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    saved, skipped = save_articles_as_txt(pdf_path, cleaned_chunks, folder_name=stem)
    usable_chunks = [
        c for c in cleaned_chunks if article_text_is_usable(c.text, min_words=40)[0]
    ]
    return pdf_extract_folder(pdf_path, folder_name=stem), saved, usable_chunks, skipped


def load_article_txt(path: Path) -> tuple[str, str]:
    """Load (title, body_for_llm) from a saved article TXT."""
    content = path.read_text(encoding="utf-8")
    return extract_title_from_txt(content), extract_body_from_txt(content)


def list_saved_articles(pdf_path: Path, *, folder_name: str | None = None) -> list[SavedArticle]:
    """List already-extracted articles for a PDF (if folder exists)."""
    out_dir = pdf_extract_folder(pdf_path, folder_name=folder_name)
    index_path = out_dir / "index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    saved: list[SavedArticle] = []
    for row in data.get("articles", []):
        path = out_dir / row["file"]
        if not path.exists():
            continue
        saved.append(
            SavedArticle(
                index=int(row["index"]),
                title=row["title"],
                path=path,
                page=int(row.get("page", 1)),
                word_count=int(row.get("words", 0)),
            )
        )
    return saved


def list_skipped_articles(pdf_path: Path, *, folder_name: str | None = None) -> list[SkippedArticle]:
    """List skipped low-quality extracts recorded in index.json."""
    out_dir = pdf_extract_folder(pdf_path, folder_name=folder_name)
    index_path = out_dir / "index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return [
        SkippedArticle(
            title=row.get("title", "Untitled"),
            page=int(row.get("page", 1)),
            reason=row.get("reason", "Low quality"),
            word_count=int(row.get("words", 0)),
        )
        for row in data.get("skipped", [])
    ]
