"""Reusable Streamlit UI components."""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any

import streamlit as st

from pipeline.article_store import (
    list_saved_articles,
    list_skipped_articles,
    pdf_extract_folder,
    save_single_article_txt,
)
from pipeline.pdf_articles import (
    ArticleChunk,
    PdfInspection,
    fetch_article_by_headline,
    inspect_pdf,
    rank_articles,
)
from pipeline.schemas import ExamNotesReport
from pipeline.pdf_extract import article_text_quality, tesseract_available
from pipeline.text_clean import extract_body_from_txt
from tts_engine import list_voices, synthesize


def _esc(text: str) -> str:
    return html.escape(text or "")


def render_header(*, api_configured: bool) -> None:
    status_badge = (
        '<span class="badge badge-success">● API Connected</span>'
        if api_configured
        else '<span class="badge badge-warning">● API Key Required</span>'
    )
    st.markdown(
        f"""
        <div class="app-hero">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1rem;">
                <div>
                    <h1>News Analyst</h1>
                    <p>Hindi educational content generator — study notes, YouTube script, PPT slides, Instagram carousel, and teacher audio for competitive exams.</p>
                </div>
                <div>{status_badge}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_settings() -> dict[str, Any]:
    """Render sidebar controls and return settings dict."""
    with st.sidebar:
        st.markdown("### ⚙️ Analysis Settings")
        st.markdown('<p class="section-label">Exam Focus</p>', unsafe_allow_html=True)

        from pipeline.analyzer import EXAM_FOCUS_LABELS

        exam_focus = st.selectbox(
            "Exam focus",
            list(EXAM_FOCUS_LABELS.keys()),
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown('<p class="section-label">हिंदी आवाज़ (YouTube / Reels)</p>', unsafe_allow_html=True)
        st.caption("सभी educational content हिंदी में आता है। Audio हमेशा हिंदी speaker पर बनेगा।")

        hindi_voices = {
            "Hindi Female (Indian accent)": "hi_IN-female",
            "Hindi Male (Indian accent)": "hi_IN-male",
        }
        hindi_voice_id = st.selectbox(
            "Hindi voice",
            options=list(hindi_voices.values()),
            format_func=lambda v: next(k for k, val in hindi_voices.items() if val == v),
            label_visibility="collapsed",
        )
        generate_hindi_audio = st.checkbox(
            "Generate Hindi teacher audio",
            value=True,
            help="YouTube script को Indian Hindi accent (gTTS co.in) में MP3 बनाता है।",
        )
        speed = st.slider("Speed", 0.5, 2.0, 1.0, key="news_speed")
        volume = st.slider("Volume", 0.1, 2.0, 1.0, key="news_volume")

        # Analyst pipeline always uses Hindi voice as primary
        voice_id = hindi_voice_id

        st.markdown("---")
        st.markdown(
            '<p style="font-size:0.78rem; color:#64748b; line-height:1.5;">'
            "Claude Educational Content · Hindi TTS · ReportLab"
            "</p>",
            unsafe_allow_html=True,
        )

    return {
        "exam_focus": exam_focus,
        "voice_id": voice_id,
        "speed": speed,
        "volume": volume,
        "generate_hindi_audio": generate_hindi_audio,
        "hindi_voice_id": hindi_voice_id,
    }


def _pdf_preview_path(uploaded_pdf) -> Path:
    tmp_dir = Path("uploads")
    tmp_dir.mkdir(exist_ok=True)
    path = tmp_dir / f"_preview_{uploaded_pdf.name}"
    path.write_bytes(uploaded_pdf.getvalue())
    return path


def _pdf_file_hash(uploaded_pdf) -> str:
    return hashlib.md5(uploaded_pdf.getvalue()).hexdigest()


def _pdf_scan_cache_key(uploaded_pdf, page_number: int | None, force_ocr: bool) -> str:
    page_key = page_number if page_number else 0
    return f"{_pdf_file_hash(uploaded_pdf)}:{page_key}:{int(force_ocr)}"


def _run_pdf_inspection(
    uploaded_pdf,
    *,
    page_number: int | None,
    force_ocr: bool,
    article_selector: str = "",
) -> PdfInspection:
    """Scan PDF for pages and articles; cache in session state."""
    cache_key = _pdf_scan_cache_key(uploaded_pdf, page_number, force_ocr)
    if st.session_state.get("pdf_scan_cache_key") == cache_key and st.session_state.get("pdf_inspection"):
        inspection: PdfInspection = st.session_state["pdf_inspection"]
    else:
        preview_path = _pdf_preview_path(uploaded_pdf)
        with st.spinner("Extracting articles → clean TXT files..."):
            inspection = inspect_pdf(
                preview_path,
                page_number=page_number,
                force_ocr=force_ocr,
                txt_folder_name=Path(uploaded_pdf.name).stem,
            )
        st.session_state["pdf_inspection"] = inspection
        st.session_state["pdf_scan_cache_key"] = cache_key
        st.session_state["detected_pdf_name"] = uploaded_pdf.name
        # Clear old/new picker keys so a fresh extract does not keep a stale choice
        for key in ("pdf_article_pick", "pdf_article_pick_path", "pdf_article_pick_chunk"):
            st.session_state.pop(key, None)

    chunks = list(inspection.articles)
    if article_selector.strip():
        chunks = rank_articles(chunks, article_selector.strip())
    st.session_state["detected_articles"] = chunks
    return inspection


def _article_option_label(chunk: ArticleChunk, index: int) -> str:
    title = chunk.title_guess.strip()
    if len(title) < 8 or article_text_quality(title)[1] < 3:
        title = chunk.preview[:90]
    words = len(chunk.text.split())
    score = f" · match {chunk.score:.0f}%" if chunk.score else ""
    return f"{index + 1}. p.{chunk.page} · {title[:100]} (~{words:,} words){score}"


def render_input_panel() -> tuple[str, Any, str, str, int | None, ArticleChunk | None, bool, str, Path | None]:
    """Render input section.

    Returns:
        news_text, uploaded_pdf, input_mode, article_selector, page_number,
        selected_chunk, force_ocr, pdf_fallback_text, article_txt_path
    """
    input_mode = st.radio(
        "Input mode",
        ["Paste text", "Upload PDF"],
        horizontal=True,
        label_visibility="collapsed",
    )

    news_text = ""
    uploaded_pdf = None
    article_selector = ""
    page_number: int | None = None
    selected_chunk: ArticleChunk | None = None
    force_ocr = False
    pdf_fallback_text = ""
    article_txt_path: Path | None = None

    if input_mode == "Paste text":
        news_text = st.text_area(
            "News content",
            height=280,
            placeholder="Paste your news article, editorial, or current affairs content here...\n\nTip: Include the full article for best analysis quality.",
            label_visibility="collapsed",
        )
        if news_text.strip():
            word_count = len(news_text.split())
            st.caption(f"{word_count:,} words · {len(news_text):,} characters")

        with st.expander("Multiple articles in pasted text? (optional)", expanded=False):
            article_selector = st.text_input(
                "Which article to analyze",
                placeholder='e.g. "RBI monetary policy", "Article on Article 370", headline keywords...',
                help="Use when your pasted text contains more than one story.",
                key="paste_article_selector",
            )
    else:
        uploaded_pdf = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
            help="Upload a news article or editorial PDF (max 50 pages)",
            label_visibility="collapsed",
        )
        if uploaded_pdf is not None:
            if st.session_state.get("detected_pdf_name") != uploaded_pdf.name:
                st.session_state.pop("detected_articles", None)
                st.session_state.pop("detected_pdf_name", None)
                st.session_state.pop("pdf_inspection", None)
                st.session_state.pop("pdf_scan_cache_key", None)
                st.session_state.pop("saved_article_txts", None)
                st.session_state.pop("skipped_article_txts", None)
                st.session_state.pop("headline_fetch_ok", None)

            size_kb = len(uploaded_pdf.getvalue()) / 1024
            st.markdown(
                f'<div class="card" style="padding:1rem; margin-top:0.5rem;">'
                f'<span style="color:#94a3b8;">File:</span> '
                f'<strong style="color:#f1f5f9;">{uploaded_pdf.name}</strong>'
                f'<span style="color:#64748b; margin-left:0.75rem;">({size_kb:.1f} KB)</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            """
            <div class="card" style="margin-top:1rem; border-color:rgba(59,130,246,0.35); background:rgba(59,130,246,0.06);">
                <p class="card-title" style="margin-bottom:0.5rem;">Extract Articles → TXT → LLM</p>
                <p style="color:#94a3b8; margin:0; font-size:0.88rem; line-height:1.55;">
                    Prefer <strong>Fetch by headline</strong> when you know the article title.
                    Or run full-page <strong>Extract → TXT</strong> — low-quality chunks are skipped, not forced.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        force_ocr = st.checkbox(
            "Use OCR (recommended for newspaper PDFs)",
            value=True,
            help="Requires Tesseract. Reads scanned / custom-font PDFs and saves clean article TXT files.",
            key="pdf_force_ocr",
        )

        col_page, col_refresh = st.columns([2, 1])
        with col_page:
            page_input = st.number_input(
                "Limit scan to page",
                min_value=0,
                max_value=50,
                value=1,
                step=1,
                help="0 = scan all pages. For single-page PDFs leave as 1.",
                key="pdf_page_number",
            )
            page_number = page_input if page_input > 0 else None
        with col_refresh:
            st.markdown("<br>", unsafe_allow_html=True)
            refresh_clicked = st.button("Extract → TXT", use_container_width=True, key="rescan_pdf_articles")

        st.markdown('<p class="section-label" style="margin-top:0.75rem;">Fetch by headline</p>', unsafe_allow_html=True)
        hed_col, hed_btn = st.columns([3, 1])
        with hed_col:
            headline_query = st.text_input(
                "Headline to fetch",
                placeholder='e.g. "Santiago to Shopian and Delhi" or "A call for disaster drills"',
                help="OCR finds this headline on the page and extracts only that article.",
                key="pdf_headline_fetch",
                label_visibility="collapsed",
            )
        with hed_btn:
            fetch_clicked = st.button("Fetch headline", use_container_width=True, key="pdf_fetch_headline_btn")

        col_article, _ = st.columns([3, 1])
        with col_article:
            article_selector = st.text_input(
                "Filter articles (optional keywords)",
                placeholder='e.g. "ecology" — ranks matching articles first',
                help="Optional. Narrows or re-orders the detected article list.",
                key="pdf_article_selector",
            )

        inspection: PdfInspection | None = None
        if uploaded_pdf is not None:
            if force_ocr and not tesseract_available():
                st.error(
                    "Tesseract OCR is not available. Run `python check_pdf_ocr.py` "
                    "in the same terminal you use for Streamlit."
                )
            elif refresh_clicked:
                st.session_state.pop("pdf_scan_cache_key", None)

            preview_path = _pdf_preview_path(uploaded_pdf)
            txt_stem = Path(uploaded_pdf.name).stem
            txt_folder = pdf_extract_folder(preview_path, folder_name=txt_stem)

            # Full-page extract first (cached). Headline fetch runs after so pick path is not cleared.
            inspection = _run_pdf_inspection(
                uploaded_pdf,
                page_number=page_number,
                force_ocr=force_ocr,
                article_selector=article_selector,
            )

            if fetch_clicked:
                if not headline_query.strip():
                    st.warning("Enter a headline (or a few distinctive keywords) to fetch.")
                else:
                    try:
                        with st.spinner(f"Finding headline: {headline_query.strip()[:60]}..."):
                            hit = fetch_article_by_headline(
                                preview_path,
                                headline_query.strip(),
                                page_number=page_number or 1,
                                force_ocr=force_ocr,
                            )
                            saved_one = save_single_article_txt(
                                preview_path,
                                hit,
                                folder_name=txt_stem,
                                clear_existing=False,
                            )
                        st.session_state["pdf_article_pick_path"] = saved_one.label
                        st.session_state["headline_fetch_ok"] = (
                            f"Fetched `{saved_one.path.name}` · ~{saved_one.word_count:,} words "
                            f"(match {hit.score:.0f}%)"
                        )
                        st.success(st.session_state["headline_fetch_ok"])
                    except Exception as exc:
                        st.error(str(exc))

            if st.session_state.get("headline_fetch_ok") and not fetch_clicked:
                st.caption(st.session_state["headline_fetch_ok"])

            saved = list_saved_articles(preview_path, folder_name=txt_stem)
            skipped = list_skipped_articles(preview_path, folder_name=txt_stem)
            st.session_state["saved_article_txts"] = saved
            st.session_state["skipped_article_txts"] = skipped

            if inspection.extraction_method == "ocr_failed":
                st.error(
                    "OCR could not read this PDF. Install Tesseract or paste article text in the fallback box."
                )
            elif not inspection.readable and not force_ocr:
                st.warning(
                    f"PDF text layer looks garbled ({inspection.readable_ratio:.0%} readable). "
                    "Enable **Use OCR** and click **Extract → TXT**."
                )

            m_pages, m_scanned, m_articles = st.columns(3)
            with m_pages:
                st.metric("Total pages", inspection.page_count)
            with m_scanned:
                st.metric("Pages scanned", inspection.pages_scanned)
            with m_articles:
                st.metric("Articles saved", len(saved))

            if saved:
                st.success(f"Saved {len(saved)} clean article TXT file(s) in `{txt_folder}`")
                with st.expander("TXT files on disk", expanded=False):
                    for s in saved:
                        st.caption(f"`{s.path.name}` — {s.title}")

            if skipped:
                st.warning(f"Skipped {len(skipped)} low-quality extract(s) (not sent to Claude).")
                with st.expander("Skipped extracts", expanded=False):
                    for sk in skipped:
                        st.caption(f"p.{sk.page} · {sk.title[:80]} — {sk.reason}")

            if inspection.articles_by_page and (page_number is None) and inspection.page_count > 1:
                breakdown = ", ".join(
                    f"p.{pg}: {count}"
                    for pg, count in sorted(inspection.articles_by_page.items())
                )
                st.caption(f"Articles per page — {breakdown}")

        chunks: list[ArticleChunk] = st.session_state.get("detected_articles") or []
        saved_txts = st.session_state.get("saved_article_txts") or []

        if uploaded_pdf is not None and (chunks or saved_txts):
            if saved_txts:
                label_options = [s.label for s in saved_txts]
                label_to_saved = {s.label: s for s in saved_txts}

                current = st.session_state.get("pdf_article_pick_path")
                if current is not None and current not in label_options:
                    st.session_state.pop("pdf_article_pick_path", None)

                chosen_label = st.radio(
                    "Select article TXT to send to LLM",
                    options=label_options,
                    key="pdf_article_pick_path",
                    help="Pick which extracted TXT file is sent to Claude.",
                )
                chosen = label_to_saved[chosen_label]
                article_txt_path = chosen.path
                body = chosen.path.read_text(encoding="utf-8")

                selected_chunk = ArticleChunk(
                    title_guess=chosen.title,
                    text=extract_body_from_txt(body),
                    page=chosen.page,
                )
                st.caption(
                    f"TXT: `{chosen.path.name}` · ~{chosen.word_count:,} words · will be sent to Claude"
                )
                with st.expander("Preview selected article TXT", expanded=False):
                    st.text(selected_chunk.text[:3000] + ("..." if len(selected_chunk.text) > 3000 else ""))
                    _ratio, words, _alpha = article_text_quality(selected_chunk.text)
                    if words < 25:
                        st.error(
                            f"This extract looks garbled ({words} readable words). "
                            "Use **Fetch by headline**, re-run **Extract → TXT**, or paste text."
                        )
            else:
                chunk_labels = [_article_option_label(c, i) for i, c in enumerate(chunks)]
                unique_labels = [
                    f"{label} [{i}]" if chunk_labels.count(label) > 1 else label
                    for i, label in enumerate(chunk_labels)
                ]
                current = st.session_state.get("pdf_article_pick_chunk")
                if current is not None and current not in unique_labels:
                    st.session_state.pop("pdf_article_pick_chunk", None)

                chosen_label = st.radio(
                    "Select article to summarize",
                    options=unique_labels,
                    key="pdf_article_pick_chunk",
                )
                pick_idx = unique_labels.index(chosen_label)
                selected_chunk = chunks[pick_idx]
                st.caption(
                    f"Selected: {len(selected_chunk.text):,} chars · "
                    f"~{len(selected_chunk.text.split()):,} words"
                )
                with st.expander("Preview selected article", expanded=False):
                    st.text(selected_chunk.text[:2500] + ("..." if len(selected_chunk.text) > 2500 else ""))
        elif uploaded_pdf is not None and (
            (inspection and inspection.article_count == 0) or not saved_txts
        ):
            st.warning(
                "No usable articles yet. Try **Fetch by headline**, **Extract → TXT** with OCR, "
                "or paste text below."
            )

        with st.expander("Paste article text (fallback for unreadable PDFs)", expanded=False):
            st.caption(
                "Do **not** copy from the PDF viewer (Ctrl+C) — newspaper PDFs often paste as garbled symbols. "
                "Instead: **Fetch by headline**, enable **Use OCR** and Extract → TXT, or paste from the website."
            )
            pdf_fallback_text = st.text_area(
                "Article text",
                height=160,
                placeholder="Paste article text from the newspaper website (not from the PDF)...",
                key="pdf_fallback_text",
                label_visibility="collapsed",
            )

        if uploaded_pdf is not None and not pdf_fallback_text.strip() and selected_chunk is None:
            st.caption("Tip: **Fetch by headline** for one article, or **Extract → TXT** then pick from the list.")
        elif (
            uploaded_pdf is None
            and not article_selector.strip()
            and selected_chunk is None
            and not pdf_fallback_text.strip()
        ):
            st.caption("Tip: Enable **Use OCR** for newspaper PDFs, then Fetch by headline or Extract → TXT.")

    selector = article_selector.strip()
    if selected_chunk and not selector:
        selector = selected_chunk.title_guess
    return (
        news_text,
        uploaded_pdf,
        input_mode,
        selector,
        page_number,
        selected_chunk,
        force_ocr,
        pdf_fallback_text.strip(),
        article_txt_path,
    )


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="empty-state">
            <div class="empty-state-icon">📊</div>
            <h3>No analysis yet</h3>
            <p>Submit news text or upload a PDF to generate exam-focused analysis, PDF report, and audio narration.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_bullet_list(items: list[str], dot_color: str = "#3b82f6") -> None:
    if not items:
        st.markdown('<p style="color:#64748b; font-style:italic;">No items generated.</p>', unsafe_allow_html=True)
        return
    bullets = "".join(
        f'<div class="bullet-item"><span class="bullet-dot" style="background:{dot_color};"></span>'
        f"<span>{_esc(item)}</span></div>"
        for item in items
    )
    st.markdown(f'<div class="card" style="padding:0.75rem 1.25rem;">{bullets}</div>', unsafe_allow_html=True)


def render_analysis_results(result: dict[str, Any]) -> None:
    """Render Hindi educational multi-asset results panel."""
    analysis: ExamNotesReport = result["analysis"]
    job_id = result["job_id"]
    artifact_dir = result.get("artifact_dir") or f"artifacts/{job_id}"
    headline = result.get("headline") or analysis.title or analysis.topic or job_id

    meta_parts = []
    if analysis.theme:
        meta_parts.append(_esc(analysis.theme))
    if analysis.topic:
        meta_parts.append(_esc(analysis.topic))
    meta_line = " · ".join(meta_parts)

    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem;">
            <p class="section-label">Educational Content Pack (Hindi)</p>
            <h2 class="result-title">{_esc(analysis.title or analysis.topic)}</h2>
            <p class="result-meta">
                <span class="badge badge-primary">{_esc(analysis.exam_focus)}</span>
                {f'<span class="badge badge-primary" style="margin-left:0.35rem;">{_esc(analysis.gs_paper_mapping)}</span>' if analysis.gs_paper_mapping else ''}
                <span style="margin-left:0.5rem;">{_esc(headline)}</span>
            </p>
            {f'<p class="result-meta" style="margin-top:0.35rem;">{meta_line}</p>' if meta_line else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Prelims", analysis.prelims_relevance)
    with m2:
        st.metric("Mains", analysis.mains_relevance)
    with m3:
        st.metric("Interview", analysis.interview_relevance)
    with m4:
        st.metric("State PCS", analysis.state_pcs_relevance)

    if analysis.upsc_subjects or analysis.state_pcs_subjects:
        tags = "".join(f'<span class="syllabus-tag">{_esc(s)}</span>' for s in analysis.upsc_subjects)
        tags += "".join(f'<span class="syllabus-tag">{_esc(s)}</span>' for s in analysis.state_pcs_subjects)
        st.markdown(f'<div style="margin:0.75rem 0;">{tags}</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="card-highlight">
            <p class="card-title" style="margin-bottom:0.5rem;">Exam One-Liner</p>
            <p>{_esc(analysis.exam_one_liner)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(
        [
            "Full Pack",
            "Study Notes",
            "Background",
            "YouTube Script",
            "PowerPoint",
            "Instagram",
            "MCQs / PYQs",
            "Revision",
        ]
    )

    with tabs[0]:
        st.markdown(analysis.full_report_markdown or "_No full pack returned._")

    with tabs[1]:
        st.markdown(analysis.hindi_study_notes or analysis.pdf_notes or "_No study notes._")

    with tabs[2]:
        st.markdown(analysis.complete_background or "_No background._")

    with tabs[3]:
        if analysis.youtube_meta:
            with st.expander("YouTube meta / outline", expanded=False):
                st.markdown(analysis.youtube_meta)
        spoken = analysis.youtube_script or analysis.hindi_narration_script
        st.markdown('<p class="card-title">Spoken Hindi Script (TTS)</p>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="card"><p style="color:#cbd5e1; line-height:1.7; margin:0; font-size:0.9rem;">{_esc(spoken)}</p></div>',
            unsafe_allow_html=True,
        )

    with tabs[4]:
        st.caption("Camera-ready slides for YouTube / Instagram / Facebook explainers")
        st.markdown(analysis.powerpoint_slides or "_No PowerPoint slides._")
        if analysis.infographic_spec:
            with st.expander("Infographic specification", expanded=False):
                st.markdown(analysis.infographic_spec)
        if analysis.image_generation_prompt:
            with st.expander("AI image generation prompt (English)", expanded=False):
                st.code(analysis.image_generation_prompt, language=None)

    with tabs[5]:
        st.markdown(analysis.instagram_carousel or "_No Instagram carousel._")
        if analysis.telegram_notes:
            st.markdown("### Telegram Notes")
            st.markdown(analysis.telegram_notes)

    with tabs[6]:
        st.markdown("### MCQs")
        st.markdown(analysis.mcqs or "_No MCQs._")
        st.markdown("### PYQs")
        st.markdown(analysis.pyqs or "_No PYQs._")
        if analysis.expected_questions:
            st.markdown("### Expected Questions")
            st.markdown(analysis.expected_questions)

    with tabs[7]:
        if analysis.quick_revision:
            _render_bullet_list(analysis.quick_revision, "#22c55e")
        elif analysis.hindi_summary:
            _render_bullet_list(analysis.hindi_summary, "#f59e0b")
        else:
            st.markdown("_No revision bullets._")
        if analysis.mind_map:
            st.markdown("### Mind Map")
            st.markdown(analysis.mind_map)
        if analysis.keywords:
            st.markdown("### Keywords")
            st.markdown(analysis.keywords)
        if analysis.memory_tricks:
            st.markdown("### Memory Tricks")
            st.markdown(analysis.memory_tricks)

    st.markdown("---")
    st.markdown('<p class="section-label">हिंदी टीचर ऑडियो (YouTube / Reels)</p>', unsafe_allow_html=True)
    audio_file = result.get("hindi_audio_path") or result.get("audio_path")
    if audio_file:
        st.audio(str(audio_file), format="audio/mp3")
    else:
        st.caption("No Hindi audio generated.")

    st.markdown('<p class="section-label" style="margin-top:1rem;">Export</p>', unsafe_allow_html=True)
    dl1, dl2, dl3, dl4 = st.columns(4)
    with dl1:
        with open(result["pdf_path"], "rb") as f:
            st.download_button(
                "PDF Report",
                f.read(),
                file_name=Path(result["pdf_path"]).name,
                use_container_width=True,
                type="primary",
            )
    with dl2:
        if result.get("md_path"):
            with open(result["md_path"], "rb") as f:
                st.download_button(
                    "Full Markdown",
                    f.read(),
                    file_name=Path(result["md_path"]).name,
                    use_container_width=True,
                )
    with dl3:
        script_path = result.get("hindi_script_path")
        if script_path:
            with open(script_path, "rb") as f:
                st.download_button(
                    "Hindi Script",
                    f.read(),
                    file_name=Path(script_path).name,
                    use_container_width=True,
                )
    with dl4:
        if audio_file:
            with open(audio_file, "rb") as f:
                st.download_button(
                    "Hindi MP3",
                    f.read(),
                    file_name=Path(str(audio_file)).name,
                    use_container_width=True,
                )

    if result.get("hindi_summary_path") or result.get("json_path"):
        h1, h2 = st.columns(2)
        with h1:
            if result.get("hindi_summary_path"):
                with open(result["hindi_summary_path"], "rb") as f:
                    st.download_button(
                        "Hindi Summary Bullets",
                        f.read(),
                        file_name=Path(result["hindi_summary_path"]).name,
                        use_container_width=True,
                    )
        with h2:
            with open(result["json_path"], "rb") as f:
                st.download_button(
                    "JSON Data",
                    f.read(),
                    file_name=Path(result["json_path"]).name,
                    use_container_width=True,
                )

    st.caption(
        f"Saved under `{artifact_dir}` — includes `claude_response.json`, "
        f"`claude_response.md`, and `educational_assets/`"
    )


def render_tts_tab() -> None:
    """Render the Text-to-Voice tab."""
    st.markdown(
        """
        <div class="card" style="margin-bottom:1.5rem;">
            <p class="card-title">Text-to-Voice</p>
            <p style="color:#94a3b8; margin:0; font-size:0.92rem;">
                Convert any text to natural speech using offline Piper voices or online Hindi/Bhojpuri engines.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_input, col_settings = st.columns([2, 1])

    with col_input:
        text = st.text_area(
            "Text to convert",
            height=200,
            placeholder="Enter the text you want to convert to speech...",
            key="tts_text",
            label_visibility="collapsed",
        )

    with col_settings:
        tts_voices = list_voices()
        tts_voice = st.selectbox(
            "Voice",
            options=list(tts_voices.values()),
            format_func=lambda v: next(k for k, val in tts_voices.items() if val == v),
            key="tts_voice",
        )
        tts_speed = st.slider("Speed", 0.5, 2.0, 1.0, key="tts_speed")
        tts_volume = st.slider("Volume", 0.1, 2.0, 1.0, key="tts_volume")

    if st.button("Generate Audio", type="primary", use_container_width=True):
        if not text.strip():
            st.warning("Please enter some text first.")
        else:
            with st.spinner("Synthesizing speech..."):
                try:
                    audio_path = synthesize(text, tts_voice, speed=tts_speed, volume=tts_volume)
                    st.session_state["last_audio"] = str(audio_path)
                    st.success("Audio generated successfully.")
                except Exception as exc:
                    st.error(str(exc))

    if "last_audio" in st.session_state:
        st.markdown("---")
        st.markdown('<p class="section-label">Generated Audio</p>', unsafe_allow_html=True)
        fmt = "audio/mp3" if st.session_state["last_audio"].endswith(".mp3") else "audio/wav"
        st.audio(st.session_state["last_audio"], format=fmt)
        with open(st.session_state["last_audio"], "rb") as f:
            st.download_button(
                "Download Audio",
                data=f.read(),
                file_name=Path(st.session_state["last_audio"]).name,
                mime=fmt,
                use_container_width=True,
            )
