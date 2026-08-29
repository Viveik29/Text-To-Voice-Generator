"""Streamlit UI components for Hindi Voice Generator."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from tts_engine import estimate_duration_seconds, list_voices, synthesize


def render_header() -> None:
    st.markdown(
        """
        <div class="app-hero">
            <span class="badge badge-primary">Hindi Only</span>
            <span class="badge badge-accent" style="margin-left:0.5rem;">YouTube Ready</span>
            <h1 style="margin-top:1rem;">Hindi Voice Generator</h1>
            <p>Paste your script or upload a .txt file and generate high-quality neural Hindi voice for YouTube videos.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_settings() -> dict:
    st.sidebar.markdown("### Voice Settings")

    voices = list_voices()
    voice_labels = list(voices.keys())
    default_label = next(
        (label for label, voice_id in voices.items() if voice_id == "hi-IN-SwaraNeural"),
        voice_labels[0],
    )
    default_index = voice_labels.index(default_label)

    selected_label = st.sidebar.selectbox("Voice", voice_labels, index=default_index)
    speed = st.sidebar.slider("Speed", 0.5, 2.0, 1.0, 0.05)
    output_format = st.sidebar.radio("Export Format", ["wav", "mp3"], index=0, horizontal=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
        **Tips for YouTube**
        - Use WAV for best editing quality
        - Swara for female narration
        - Madhur for male voiceover
        - Internet connection required
        """
    )

    return {
        "voice_id": voices[selected_label],
        "speed": speed,
        "output_format": output_format,
    }


def render_input_panel() -> tuple[str, object | None]:
    st.markdown('<p class="section-label">Input</p>', unsafe_allow_html=True)

    col_text, col_file = st.columns([1.4, 1])
    with col_file:
        uploaded = st.file_uploader(
            "Upload .txt file",
            type=["txt"],
            help="UTF-8 encoded Hindi text file",
        )
        if uploaded is not None:
            try:
                st.session_state["hindi_script"] = uploaded.getvalue().decode("utf-8")
                st.success(f"Loaded: {uploaded.name}")
            except UnicodeDecodeError:
                st.error("File must be UTF-8 encoded.")

    with col_text:
        text = st.text_area(
            "Hindi script",
            height=280,
            placeholder="यहाँ अपना हिंदी स्क्रिप्ट पेस्ट करें...",
            key="hindi_script",
            label_visibility="collapsed",
        )

    char_count = len(text.strip())
    est_seconds = estimate_duration_seconds(text.strip()) if text.strip() else 0
    minutes, seconds = divmod(int(est_seconds), 60)

    st.markdown(
        f"""
        <div class="meta-row">
            <span class="meta-pill">{char_count:,} characters</span>
            <span class="meta-pill">~{minutes}m {seconds:02d}s estimated</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    return text, uploaded


def render_generate_button(settings: dict, text: str) -> None:
    if st.button("Generate HD Voice", type="primary", use_container_width=True):
        if not text.strip():
            st.warning("Please paste Hindi text or upload a .txt file first.")
            return

        progress = st.progress(0.0, text="Preparing synthesis...")
        status = st.empty()

        def on_progress(done: int, total: int) -> None:
            fraction = done / total
            progress.progress(fraction, text=f"Synthesizing chunk {done}/{total}...")
            status.caption(f"Processing chunk {done} of {total}")

        try:
            audio_path = synthesize(
                text,
                settings["voice_id"],
                speed=settings["speed"],
                output_format=settings["output_format"],
                progress_callback=on_progress,
            )
            st.session_state["last_audio"] = str(audio_path)
            progress.progress(1.0, text="Complete!")
            status.empty()
            st.success("HD voice generated successfully.")
            st.rerun()
        except Exception as exc:
            progress.empty()
            status.empty()
            st.error(str(exc))


def render_audio_output() -> None:
    audio_path = st.session_state.get("last_audio")
    if not audio_path:
        return

    st.markdown("---")
    st.markdown('<p class="section-label">Generated Audio</p>', unsafe_allow_html=True)

    path = Path(audio_path)
    mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
    st.audio(str(path), format=mime)

    with open(path, "rb") as audio_file:
        st.download_button(
            "Download Audio",
            data=audio_file.read(),
            file_name=path.name,
            mime=mime,
            use_container_width=True,
        )

    st.caption(f"Saved to `{path}`")
