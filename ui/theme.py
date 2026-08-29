"""Light design system for Hindi Voice Generator."""

import streamlit as st

COLORS = {
    "bg": "#f8fafc",
    "surface": "#ffffff",
    "surface_soft": "#f1f5f9",
    "border": "#e2e8f0",
    "border_light": "#cbd5e1",
    "text": "#0f172a",
    "text_muted": "#64748b",
    "text_subtle": "#94a3b8",
    "primary": "#0d9488",
    "primary_hover": "#0f766e",
    "primary_soft": "rgba(13, 148, 136, 0.1)",
    "accent": "#f59e0b",
    "accent_soft": "rgba(245, 158, 11, 0.12)",
    "success": "#059669",
    "success_soft": "rgba(5, 150, 105, 0.1)",
    "danger": "#dc2626",
    "gradient_start": "#ecfeff",
    "gradient_end": "#f8fafc",
}


def inject_theme() -> None:
    c = COLORS
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .stApp {{
            background: linear-gradient(180deg, {c['gradient_start']} 0%, {c['bg']} 35%, {c['bg']} 100%);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: {c['text']};
        }}

        #MainMenu, footer, header[data-testid="stHeader"] {{
            visibility: hidden;
        }}

        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 3rem;
            max-width: 1100px;
        }}

        h1, h2, h3, h4, h5, h6, p, label, .stMarkdown {{
            font-family: 'Inter', sans-serif !important;
        }}

        section[data-testid="stSidebar"] {{
            background: {c['surface']};
            border-right: 1px solid {c['border']};
        }}

        section[data-testid="stSidebar"] .block-container {{
            padding-top: 2rem;
        }}

        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {c['primary']} 0%, {c['primary_hover']} 100%);
            color: white;
            border: none;
            border-radius: 12px;
            padding: 0.7rem 1.5rem;
            font-weight: 600;
            font-size: 0.95rem;
            box-shadow: 0 8px 20px rgba(13, 148, 136, 0.25);
            transition: all 0.2s ease;
        }}

        .stButton > button[kind="primary"]:hover {{
            transform: translateY(-1px);
            box-shadow: 0 10px 24px rgba(13, 148, 136, 0.32);
        }}

        .stTextArea textarea, .stTextInput input {{
            background: {c['surface']} !important;
            border: 1px solid {c['border']} !important;
            border-radius: 12px !important;
            color: {c['text']} !important;
            font-size: 0.95rem !important;
            line-height: 1.6 !important;
        }}

        .stTextArea textarea:focus, .stTextInput input:focus {{
            border-color: {c['primary']} !important;
            box-shadow: 0 0 0 3px {c['primary_soft']} !important;
        }}

        [data-testid="stFileUploader"] {{
            background: {c['surface']};
            border: 2px dashed {c['border_light']};
            border-radius: 14px;
            padding: 0.5rem;
        }}

        [data-testid="stFileUploader"]:hover {{
            border-color: {c['primary']};
            background: {c['surface_soft']};
        }}

        .stDownloadButton > button {{
            background: {c['surface']} !important;
            border: 1px solid {c['border']} !important;
            border-radius: 12px !important;
            color: {c['text']} !important;
            font-weight: 500 !important;
        }}

        .stDownloadButton > button:hover {{
            border-color: {c['primary']} !important;
            color: {c['primary']} !important;
        }}

        .app-hero {{
            background: linear-gradient(135deg, {c['surface']} 0%, {c['surface_soft']} 100%);
            border: 1px solid {c['border']};
            border-radius: 20px;
            padding: 2rem 2.25rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
        }}

        .app-hero h1 {{
            font-size: 2rem;
            font-weight: 700;
            color: {c['text']};
            margin: 0 0 0.5rem 0;
            letter-spacing: -0.03em;
        }}

        .app-hero p {{
            color: {c['text_muted']};
            font-size: 1rem;
            margin: 0;
            line-height: 1.6;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.35rem 0.8rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }}

        .badge-primary {{
            background: {c['primary_soft']};
            color: {c['primary']};
            border: 1px solid rgba(13, 148, 136, 0.2);
        }}

        .badge-accent {{
            background: {c['accent_soft']};
            color: {c['accent']};
            border: 1px solid rgba(245, 158, 11, 0.25);
        }}

        .card {{
            background: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
        }}

        .card-title {{
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: {c['text_subtle']};
            margin-bottom: 0.75rem;
        }}

        .section-label {{
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: {c['text_subtle']};
            margin-bottom: 0.5rem;
        }}

        .meta-row {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            color: {c['text_muted']};
            font-size: 0.88rem;
            margin-top: 0.75rem;
        }}

        .meta-pill {{
            background: {c['surface_soft']};
            border: 1px solid {c['border']};
            border-radius: 999px;
            padding: 0.35rem 0.8rem;
        }}

        .footer-note {{
            text-align: center;
            color: {c['text_subtle']};
            font-size: 0.8rem;
            margin-top: 2.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid {c['border']};
        }}

        audio {{
            width: 100%;
            border-radius: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
