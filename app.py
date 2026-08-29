"""Hindi Voice Generator — Streamlit app."""

import streamlit as st
from dotenv import load_dotenv

from ui.components import (
    render_audio_output,
    render_generate_button,
    render_header,
    render_input_panel,
    render_sidebar_settings,
)
from ui.theme import inject_theme

load_dotenv()

st.set_page_config(
    page_title="Hindi Voice Generator",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()
settings = render_sidebar_settings()
render_header()

text, _uploaded = render_input_panel()
render_generate_button(settings, text)
render_audio_output()

st.markdown(
    '<p class="footer-note">Hindi Voice Generator · Neural TTS for YouTube creators</p>',
    unsafe_allow_html=True,
)
