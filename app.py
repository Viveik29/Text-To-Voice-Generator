import streamlit as st
from pathlib import Path
from tts_engine import synthesize, list_voices

# Apply custom CSS (above block)

st.title("🎙️ Text-to-Voice Generator")
st.subheader("🔵 Convert text into speech with style 🔵")

text = st.text_area("📝 Enter text to convert:", height=150)
voices = list_voices()
#voice_id = st.selectbox("🎤 Choose a voice:", options=list(voices.values()), format_func=lambda v: [k for k, val in voices.items() if val == v][0])
voices = list_voices()
voice_id = st.selectbox(
    "🎤 Choose a voice:",
    options=list(voices.values()),
    format_func=lambda v: [k for k, val in voices.items() if val == v][0]
)

speed = st.slider("⚡ Speed", 0.5, 2.0, 1.0)
volume = st.slider("🔊 Volume", 0.1, 2.0, 1.0)

if st.button("🎶 Generate Audio"):
    if not text.strip():
        st.warning("⚠️ Please enter some text first.")
    else:
        with st.spinner("🎼 Generating audio... (first run may download the voice model)"):
            try:
                audio_path = synthesize(text, voice_id, speed=speed, volume=volume)
                st.session_state["last_audio"] = str(audio_path)
                st.success("✅ Done!")
            except Exception as exc:
                st.error(f"❌ {exc}")

if "last_audio" in st.session_state:
    st.audio(st.session_state["last_audio"], format="audio/wav")
    with open(st.session_state["last_audio"], "rb") as f:
        st.download_button(
            label="⬇️ Download WAV",
            data=f.read(),
            file_name=Path(st.session_state["last_audio"]).name,
            mime="audio/wav",
            use_container_width=True,
        )
