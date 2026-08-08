"""End-to-end MVP pipeline orchestration."""

import uuid
from dataclasses import dataclass
from pathlib import Path

from pipeline.analyzer import analyze_news
from pipeline.audio import generate_narration_audio
from pipeline.extract import extract_text_from_pdf, normalize_text
from pipeline.pdf_articles import ArticleChunk, extract_filtered_article
from pipeline.pdf_extract import article_text_is_usable
from pipeline.report import generate_pdf_report
from pipeline.schemas import ExamNotesReport
from pipeline.text_clean import slugify_title

ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT / "uploads"
ARTIFACTS_DIR = ROOT / "artifacts"


HINDI_VOICE_DEFAULT = "hi_IN-female"


@dataclass
class PipelineResult:
    job_id: str
    analysis: ExamNotesReport
    pdf_path: Path
    audio_path: Path
    json_path: Path
    md_path: Path
    source_text_path: Path
    filtered_text_path: Path | None = None
    hindi_summary_path: Path | None = None
    hindi_script_path: Path | None = None
    hindi_audio_path: Path | None = None
    headline: str = ""
    artifact_dir: Path | None = None
    claude_response_path: Path | None = None


def _first_nonempty(*candidates: str | None) -> str:
    for value in candidates:
        text = (value or "").strip()
        if len(text) >= 4:
            return text
    return ""


def _resolve_headline(
    analysis: ExamNotesReport,
    *,
    source_title: str = "",
    matched_chunk: ArticleChunk | None = None,
    selected_chunk: ArticleChunk | None = None,
    article_selector: str | None = None,
) -> str:
    """Best available article / news headline for the output folder name."""
    return (
        _first_nonempty(
            analysis.title,
            analysis.topic,
            source_title,
            matched_chunk.title_guess if matched_chunk else None,
            selected_chunk.title_guess if selected_chunk else None,
            article_selector,
        )
        or "untitled_article"
    )


def _relocate_to_headline_folder(temp_dir: Path, run_id: str, headline: str) -> Path:
    """Move the temp job folder to a filesystem-safe headline slug."""
    import shutil

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify_title(headline, max_len=80)
    target = ARTIFACTS_DIR / slug
    if target.exists():
        target = ARTIFACTS_DIR / f"{slug}_{run_id}"
    if temp_dir.resolve() == target.resolve():
        return target
    try:
        shutil.move(str(temp_dir), str(target))
    except OSError:
        # Windows can deny rename while files are briefly locked; copy then remove.
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(temp_dir, target)
        shutil.rmtree(temp_dir, ignore_errors=True)
    return target


def run_pipeline(
    *,
    text: str | None = None,
    pdf_path: Path | None = None,
    exam_focus: str = "UPSC Prelims",
    voice_id: str = "en_US-lessac-medium",
    speed: float = 1.0,
    volume: float = 1.0,
    article_selector: str | None = None,
    page_number: int | None = None,
    selected_chunk: ArticleChunk | None = None,
    article_txt_path: Path | None = None,
    force_ocr: bool = False,
    pdf_fallback_text: str | None = None,
    generate_hindi_audio: bool = True,
    hindi_voice_id: str = HINDI_VOICE_DEFAULT,
) -> PipelineResult:
    """Run extract → filter → analyze → PDF → audio for one news item."""
    run_id = uuid.uuid4().hex[:10]
    job_dir = ARTIFACTS_DIR / run_id
    job_dir.mkdir(parents=True, exist_ok=True)

    filtered_text_path: Path | None = None
    pre_filtered = False
    matched_chunk: ArticleChunk | None = None
    source_title = ""

    # Preferred path: clean TXT already extracted from PDF
    if article_txt_path is not None and Path(article_txt_path).exists():
        from pipeline.article_store import load_article_txt

        title, body = load_article_txt(Path(article_txt_path))
        source_title = title
        news_text = normalize_text(body)
        pre_filtered = True
        filtered_text_path = job_dir / "source_filtered.txt"
        filtered_text_path.write_text(news_text, encoding="utf-8")
        (job_dir / "target_article.txt").write_text(
            f"Source TXT: {Path(article_txt_path).name}\nTitle: {title}",
            encoding="utf-8",
        )
        # Keep a copy of the selected article TXT in the job folder
        (job_dir / "article_for_llm.txt").write_text(
            Path(article_txt_path).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        if pdf_path is not None:
            saved_pdf = job_dir / pdf_path.name
            saved_pdf.write_bytes(pdf_path.read_bytes())
    elif pdf_path is not None and pdf_fallback_text and pdf_fallback_text.strip():
        news_text = normalize_text(pdf_fallback_text)
        pre_filtered = True
        filtered_text_path = job_dir / "source_filtered.txt"
        filtered_text_path.write_text(news_text, encoding="utf-8")
        (job_dir / "target_article.txt").write_text("Source: manual paste (PDF fallback)", encoding="utf-8")
        saved_pdf = job_dir / pdf_path.name
        saved_pdf.write_bytes(pdf_path.read_bytes())
        if selected_chunk and selected_chunk.title_guess:
            source_title = selected_chunk.title_guess
    elif pdf_path is not None:
        full_text = extract_text_from_pdf(pdf_path, force_ocr=force_ocr)
        (job_dir / "source_full.txt").write_text(full_text, encoding="utf-8")

        filtered_text, matched_chunk, _detected = extract_filtered_article(
            pdf_path,
            article_selector=article_selector or "",
            page_number=page_number,
            chunk_override=selected_chunk,
            force_ocr=force_ocr,
        )
        news_text = normalize_text(filtered_text)
        pre_filtered = True
        source_title = matched_chunk.title_guess if matched_chunk else ""

        filtered_text_path = job_dir / "source_filtered.txt"
        filtered_text_path.write_text(news_text, encoding="utf-8")

        meta_lines = [
            f"Target article: {article_selector or matched_chunk.title_guess}",
            f"Matched title: {matched_chunk.title_guess}",
            f"Page: {matched_chunk.page}",
            f"Match score: {matched_chunk.score:.0f}%" if matched_chunk.score else "Selected manually",
            f"Filtered chars: {len(news_text):,} (full PDF: {len(full_text):,})",
        ]
        (job_dir / "target_article.txt").write_text("\n".join(meta_lines), encoding="utf-8")

        saved_pdf = job_dir / pdf_path.name
        saved_pdf.write_bytes(pdf_path.read_bytes())
    elif text:
        news_text = normalize_text(text)
        if article_selector and article_selector.strip():
            from pipeline.pdf_articles import detect_articles_from_text, select_best_article

            chunks = detect_articles_from_text(news_text)
            if len(chunks) > 1:
                matched_chunk = select_best_article(chunks, article_selector)
                news_text = normalize_text(matched_chunk.text)
                pre_filtered = True
                source_title = matched_chunk.title_guess
                filtered_text_path = job_dir / "source_filtered.txt"
                filtered_text_path.write_text(news_text, encoding="utf-8")
            else:
                source_title = article_selector.strip()
        # First line of pasted text as a weak headline fallback
        if not source_title:
            first_line = news_text.splitlines()[0].strip() if news_text else ""
            if 8 <= len(first_line) <= 140:
                source_title = first_line
    else:
        raise ValueError("Provide either text or a PDF path.")

    if not source_title and selected_chunk and selected_chunk.title_guess:
        source_title = selected_chunk.title_guess

    source_text_path = job_dir / "source.txt"
    source_text_path.write_text(news_text, encoding="utf-8")

    usable, quality_reason = article_text_is_usable(news_text)
    if not usable:
        preview = news_text[:400].replace("\n", " ")
        raise ValueError(
            f"{quality_reason}\n\n"
            f"Preview of what was extracted: {preview!r}\n\n"
            "Claude cannot analyze garbled text. Paste the article in the fallback box instead."
        )

    analysis = analyze_news(
        news_text,
        exam_focus,
        article_selector=(
            matched_chunk.title_guess if matched_chunk else article_selector
        ),
        page_number=page_number if not pre_filtered else None,
        pre_filtered=pre_filtered,
    )

    headline = _resolve_headline(
        analysis,
        source_title=source_title,
        matched_chunk=matched_chunk,
        selected_chunk=selected_chunk,
        article_selector=article_selector,
    )
    job_dir = _relocate_to_headline_folder(job_dir, run_id, headline)
    job_id = job_dir.name
    source_text_path = job_dir / "source.txt"
    if filtered_text_path is not None:
        filtered_text_path = job_dir / filtered_text_path.name

    (job_dir / "headline.txt").write_text(headline + "\n", encoding="utf-8")

    # Full Claude structured response (primary save)
    claude_json = analysis.model_dump_json(indent=2)
    claude_response_path = job_dir / "claude_response.json"
    claude_response_path.write_text(claude_json, encoding="utf-8")
    json_path = job_dir / "analysis.json"
    json_path.write_text(claude_json, encoding="utf-8")

    md_path = job_dir / "claude_response.md"
    md_path.write_text(analysis.full_report_markdown, encoding="utf-8")
    (job_dir / "notes.md").write_text(analysis.full_report_markdown, encoding="utf-8")

    # Save individual educational asset parts for social / teaching reuse
    assets_dir = job_dir / "educational_assets"
    assets_dir.mkdir(exist_ok=True)
    asset_map = {
        "01_hindi_study_notes.md": analysis.hindi_study_notes,
        "02_complete_background.md": analysis.complete_background,
        "03_youtube_script.txt": analysis.youtube_script or analysis.hindi_narration_script,
        "03_youtube_meta.md": analysis.youtube_meta,
        "04_powerpoint_slides.md": analysis.powerpoint_slides,
        "05_infographic_spec.md": analysis.infographic_spec,
        "06_image_generation_prompt.txt": analysis.image_generation_prompt,
        "07_instagram_carousel.md": analysis.instagram_carousel,
        "08_telegram_notes.md": analysis.telegram_notes,
        "09_pdf_notes.md": analysis.pdf_notes,
        "10_mcqs.md": analysis.mcqs,
        "11_pyqs.md": analysis.pyqs,
        "12_mind_map.md": analysis.mind_map,
        "13_quick_revision.md": "\n".join(f"• {b}" for b in analysis.quick_revision),
        "14_keywords.md": analysis.keywords,
        "15_memory_tricks.md": analysis.memory_tricks,
        "16_expected_questions.md": analysis.expected_questions,
    }
    for fname, content in asset_map.items():
        if content and str(content).strip():
            (assets_dir / fname).write_text(str(content).strip() + "\n", encoding="utf-8")

    pdf_path_out = job_dir / "report.pdf"
    generate_pdf_report(analysis, pdf_path_out)

    # Always prefer Hindi coaching voice for social / YouTube narration
    spoken = (
        analysis.hindi_narration_script
        or analysis.youtube_script
        or analysis.narration_script
    ).strip()
    if not spoken:
        raise ValueError(
            "Claude did not return a Hindi narration / YouTube script. "
            "Try Analyze again, or shorten the article text."
        )

    # Force Hindi voice even if an English Piper voice was selected in older UI state
    primary_voice = hindi_voice_id if hindi_voice_id.startswith(("hi_IN", "bh_IN")) else HINDI_VOICE_DEFAULT
    if voice_id.startswith(("hi_IN", "bh_IN")):
        primary_voice = voice_id

    hindi_script_path = job_dir / "hindi_script.txt"
    hindi_script_path.write_text(spoken, encoding="utf-8")

    hindi_summary_path: Path | None = None
    if analysis.hindi_summary:
        hindi_summary_path = job_dir / "hindi_summary.txt"
        hindi_summary_path.write_text(
            "\n".join(f"• {line}" for line in analysis.hindi_summary),
            encoding="utf-8",
        )
    elif analysis.quick_revision:
        hindi_summary_path = job_dir / "hindi_summary.txt"
        hindi_summary_path.write_text(
            "\n".join(f"• {line}" for line in analysis.quick_revision[:12]),
            encoding="utf-8",
        )

    hindi_audio_path: Path | None = None
    audio_path: Path
    if generate_hindi_audio:
        hindi_audio = generate_narration_audio(
            spoken,
            primary_voice,
            output_name=f"{slugify_title(headline, max_len=40)}_hindi_narration.mp3",
            speed=speed,
            volume=volume,
        )
        job_hindi_audio = job_dir / hindi_audio.name
        if hindi_audio.resolve() != job_hindi_audio.resolve():
            job_hindi_audio.write_bytes(hindi_audio.read_bytes())
        hindi_audio_path = job_hindi_audio
        audio_path = job_hindi_audio
    else:
        hindi_audio = generate_narration_audio(
            spoken,
            primary_voice,
            output_name=f"{slugify_title(headline, max_len=40)}_narration.mp3",
            speed=speed,
            volume=volume,
        )
        job_audio = job_dir / hindi_audio.name
        if hindi_audio.resolve() != job_audio.resolve():
            job_audio.write_bytes(hindi_audio.read_bytes())
        audio_path = job_audio
        hindi_audio_path = job_audio

    return PipelineResult(
        job_id=job_id,
        analysis=analysis,
        pdf_path=pdf_path_out,
        audio_path=audio_path,
        json_path=json_path,
        md_path=md_path,
        source_text_path=source_text_path,
        filtered_text_path=filtered_text_path,
        hindi_summary_path=hindi_summary_path,
        hindi_script_path=hindi_script_path,
        hindi_audio_path=hindi_audio_path,
        headline=headline,
        artifact_dir=job_dir,
        claude_response_path=claude_response_path,
    )
