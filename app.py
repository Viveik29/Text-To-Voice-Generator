"""Streamlit UI for News Analyst + Text-to-Voice."""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from pipeline.runner import run_pipeline
from ui.components import (
    render_analysis_results,
    render_empty_state,
    render_header,
    render_input_panel,
    render_sidebar_settings,
    render_tts_tab,
)
from ui.theme import inject_theme

load_dotenv()

st.set_page_config(
    page_title="News Analyst",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

api_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
settings = render_sidebar_settings()

render_header(api_configured=api_configured)

tab_analyst, tab_tts = st.tabs(["News Analyst", "Text to Voice"])

with tab_analyst:
    if not api_configured:
        st.markdown(
            """
            <div class="card" style="border-color:rgba(245,158,11,0.4); background:rgba(245,158,11,0.06);">
                <p style="margin:0; color:#f59e0b; font-weight:500;">
                    API key required — set <code>ANTHROPIC_API_KEY</code> in your <code>.env</code> file.
                    Get a key from the <a href="https://console.anthropic.com/settings/keys" target="_blank" style="color:#3b82f6;">Anthropic Console</a>.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="input-panel-header">📥 Input Source</div>', unsafe_allow_html=True)
    (
        news_text,
        uploaded_pdf,
        input_mode,
        article_selector,
        page_number,
        selected_chunk,
        force_ocr,
        pdf_fallback_text,
        article_txt_path,
    ) = render_input_panel()

    run_clicked = st.button(
        "Analyze & Generate",
        type="primary",
        disabled=not api_configured,
        use_container_width=False,
    )

    st.markdown("---")
    st.markdown('<div class="input-panel-header">📤 Analysis Output</div>', unsafe_allow_html=True)

    result = st.session_state.get("pipeline_result")

    if run_clicked:
        if input_mode == "Paste text" and not news_text.strip():
            st.error("Please paste news text before running analysis.")
        elif input_mode == "Upload PDF" and uploaded_pdf is None:
            st.error("Please upload a PDF file before running analysis.")
        elif (
            input_mode == "Upload PDF"
            and not pdf_fallback_text.strip()
            and selected_chunk is None
            and article_txt_path is None
        ):
            st.error(
                "Fetch by headline, select an article TXT from the list, "
                "or paste article text in the fallback box."
            )
        else:
            progress = st.progress(0, text="Starting pipeline...")
            try:
                progress.progress(10, text="Loading clean article TXT for Claude...")
                pdf_tmp = None
                if uploaded_pdf is not None:
                    tmp_dir = Path("uploads")
                    tmp_dir.mkdir(exist_ok=True)
                    pdf_tmp = tmp_dir / uploaded_pdf.name
                    pdf_tmp.write_bytes(uploaded_pdf.getvalue())

                progress.progress(25, text="Claude se Hindi educational pack bana raha hai...")
                pipeline_result = run_pipeline(
                    text=news_text if input_mode == "Paste text" else None,
                    pdf_path=pdf_tmp,
                    exam_focus=settings["exam_focus"],
                    voice_id=settings["voice_id"],
                    speed=settings["speed"],
                    volume=settings["volume"],
                    article_selector=article_selector or None,
                    page_number=page_number,
                    selected_chunk=selected_chunk,
                    article_txt_path=article_txt_path,
                    force_ocr=force_ocr,
                    pdf_fallback_text=pdf_fallback_text or None,
                    generate_hindi_audio=settings.get("generate_hindi_audio", True),
                    hindi_voice_id=settings.get("hindi_voice_id", "hi_IN-female"),
                )

                progress.progress(75, text="Hindi teacher audio generate ho raha hai...")
                st.session_state["pipeline_result"] = {
                    "job_id": pipeline_result.job_id,
                    "headline": pipeline_result.headline,
                    "artifact_dir": (
                        str(pipeline_result.artifact_dir)
                        if pipeline_result.artifact_dir
                        else None
                    ),
                    "claude_response_path": (
                        str(pipeline_result.claude_response_path)
                        if pipeline_result.claude_response_path
                        else None
                    ),
                    "analysis": pipeline_result.analysis,
                    "pdf_path": str(pipeline_result.pdf_path),
                    "audio_path": str(pipeline_result.audio_path),
                    "json_path": str(pipeline_result.json_path),
                    "md_path": str(pipeline_result.md_path),
                    "filtered_text_path": (
                        str(pipeline_result.filtered_text_path)
                        if pipeline_result.filtered_text_path
                        else None
                    ),
                    "hindi_summary_path": (
                        str(pipeline_result.hindi_summary_path)
                        if pipeline_result.hindi_summary_path
                        else None
                    ),
                    "hindi_script_path": (
                        str(pipeline_result.hindi_script_path)
                        if pipeline_result.hindi_script_path
                        else None
                    ),
                    "hindi_audio_path": (
                        str(pipeline_result.hindi_audio_path)
                        if pipeline_result.hindi_audio_path
                        else None
                    ),
                }
                progress.progress(100, text="Complete!")
                st.rerun()
            except Exception as exc:
                progress.empty()
                st.error(f"Pipeline failed: {exc}")

    if result:
        render_analysis_results(result)
    else:
        render_empty_state()

with tab_tts:
    render_tts_tab()

st.markdown(
    '<p class="footer-note">News Analyst MVP · For educational and study purposes only</p>',
    unsafe_allow_html=True,
)
