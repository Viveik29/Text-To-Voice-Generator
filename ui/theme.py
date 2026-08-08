"""Professional design system for Streamlit UI."""

import streamlit as st

# Design tokens
COLORS = {
    "bg": "#0b1120",
    "surface": "#111827",
    "surface_elevated": "#1a2234",
    "border": "#243044",
    "border_light": "#334155",
    "text": "#f1f5f9",
    "text_muted": "#94a3b8",
    "text_subtle": "#64748b",
    "primary": "#3b82f6",
    "primary_hover": "#2563eb",
    "primary_soft": "rgba(59, 130, 246, 0.12)",
    "accent": "#06b6d4",
    "success": "#10b981",
    "success_soft": "rgba(16, 185, 129, 0.12)",
    "warning": "#f59e0b",
    "warning_soft": "rgba(245, 158, 11, 0.12)",
    "danger": "#ef4444",
    "danger_soft": "rgba(239, 68, 68, 0.12)",
    "gradient_start": "#1e3a5f",
    "gradient_end": "#0f172a",
}


def inject_theme() -> None:
    """Inject global CSS theme."""
    c = COLORS
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        :root {{
            --bg: {c['bg']};
            --surface: {c['surface']};
            --surface-elevated: {c['surface_elevated']};
            --border: {c['border']};
            --text: {c['text']};
            --text-muted: {c['text_muted']};
            --primary: {c['primary']};
            --primary-soft: {c['primary_soft']};
            --success: {c['success']};
            --accent: {c['accent']};
        }}

        .stApp {{
            background: linear-gradient(165deg, {c['gradient_start']} 0%, {c['bg']} 38%, #070b14 100%);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        #MainMenu, footer, header[data-testid="stHeader"] {{
            visibility: hidden;
        }}

        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 3rem;
            max-width: 1280px;
        }}

        h1, h2, h3, h4, h5, h6, p, label, .stMarkdown {{
            font-family: 'Inter', sans-serif !important;
        }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {c['surface']} 0%, {c['bg']} 100%);
            border-right: 1px solid {c['border']};
        }}

        section[data-testid="stSidebar"] .block-container {{
            padding-top: 2rem;
        }}

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.5rem;
            background: transparent;
            border-bottom: 1px solid {c['border']};
            padding-bottom: 0;
        }}

        .stTabs [data-baseweb="tab"] {{
            background: transparent;
            border-radius: 8px 8px 0 0;
            color: {c['text_muted']};
            font-weight: 500;
            font-size: 0.9rem;
            padding: 0.65rem 1.25rem;
            border: none;
        }}

        .stTabs [aria-selected="true"] {{
            background: {c['primary_soft']} !important;
            color: {c['primary']} !important;
            border-bottom: 2px solid {c['primary']} !important;
        }}

        /* Buttons */
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {c['primary']} 0%, {c['primary_hover']} 100%);
            color: white;
            border: none;
            border-radius: 10px;
            padding: 0.65rem 1.5rem;
            font-weight: 600;
            font-size: 0.95rem;
            letter-spacing: 0.01em;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.35);
            transition: all 0.2s ease;
        }}

        .stButton > button[kind="primary"]:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.45);
        }}

        .stButton > button[kind="secondary"] {{
            background: {c['surface_elevated']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 10px;
            font-weight: 500;
        }}

        /* Inputs */
        .stTextArea textarea, .stTextInput input {{
            background: {c['surface_elevated']} !important;
            border: 1px solid {c['border']} !important;
            border-radius: 10px !important;
            color: {c['text']} !important;
            font-size: 0.92rem !important;
        }}

        .stTextArea textarea:focus, .stTextInput input:focus {{
            border-color: {c['primary']} !important;
            box-shadow: 0 0 0 3px {c['primary_soft']} !important;
        }}

        .stSelectbox > div > div, .stSlider > div {{
            background: {c['surface_elevated']};
            border-color: {c['border']};
        }}

        /* File uploader */
        [data-testid="stFileUploader"] {{
            background: {c['surface_elevated']};
            border: 2px dashed {c['border_light']};
            border-radius: 12px;
            padding: 0.5rem;
            transition: border-color 0.2s ease;
        }}

        [data-testid="stFileUploader"]:hover {{
            border-color: {c['primary']};
        }}

        [data-testid="stFileUploader"] section {{
            padding: 1.5rem;
        }}

        /* Metrics override */
        [data-testid="stMetric"] {{
            background: {c['surface_elevated']};
            border: 1px solid {c['border']};
            border-radius: 12px;
            padding: 1rem 1.25rem;
        }}

        [data-testid="stMetric"] label {{
            color: {c['text_muted']} !important;
            font-size: 0.78rem !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}

        [data-testid="stMetric"] [data-testid="stMetricValue"] {{
            color: {c['text']} !important;
            font-weight: 700 !important;
        }}

        /* Download buttons */
        .stDownloadButton > button {{
            background: {c['surface_elevated']} !important;
            border: 1px solid {c['border']} !important;
            border-radius: 10px !important;
            color: {c['text']} !important;
            font-weight: 500 !important;
        }}

        .stDownloadButton > button:hover {{
            border-color: {c['primary']} !important;
            color: {c['primary']} !important;
        }}

        /* Expander */
        .streamlit-expanderHeader {{
            background: {c['surface_elevated']};
            border-radius: 10px;
            font-weight: 600;
        }}

        details {{
            background: {c['surface_elevated']};
            border: 1px solid {c['border']};
            border-radius: 10px;
        }}

        /* Audio player */
        audio {{
            width: 100%;
            border-radius: 8px;
        }}

        /* Custom component classes */
        .app-hero {{
            background: linear-gradient(135deg, rgba(30, 58, 95, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%);
            border: 1px solid {c['border']};
            border-radius: 16px;
            padding: 2rem 2.5rem;
            margin-bottom: 1.75rem;
            position: relative;
            overflow: hidden;
        }}

        .app-hero::before {{
            content: '';
            position: absolute;
            top: -50%;
            right: -10%;
            width: 300px;
            height: 300px;
            background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%);
            pointer-events: none;
        }}

        .app-hero h1 {{
            font-size: 1.85rem;
            font-weight: 700;
            color: {c['text']};
            margin: 0 0 0.5rem 0;
            letter-spacing: -0.02em;
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
            padding: 0.3rem 0.75rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }}

        .badge-success {{
            background: {c['success_soft']};
            color: {c['success']};
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .badge-warning {{
            background: {c['warning_soft']};
            color: {c['warning']};
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}

        .badge-primary {{
            background: {c['primary_soft']};
            color: {c['primary']};
            border: 1px solid rgba(59, 130, 246, 0.3);
        }}

        .card {{
            background: {c['surface_elevated']};
            border: 1px solid {c['border']};
            border-radius: 14px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }}

        .card-title {{
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: {c['text_subtle']};
            margin-bottom: 0.75rem;
        }}

        .card-highlight {{
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(6, 182, 212, 0.05) 100%);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            margin: 1rem 0;
            border-left: 4px solid {c['primary']};
        }}

        .card-highlight p {{
            color: {c['text']};
            font-size: 1.05rem;
            font-weight: 500;
            line-height: 1.65;
            margin: 0;
        }}

        .section-label {{
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: {c['text_subtle']};
            margin-bottom: 0.5rem;
        }}

        .result-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: {c['text']};
            line-height: 1.35;
            margin: 0 0 0.25rem 0;
            letter-spacing: -0.02em;
        }}

        .result-meta {{
            color: {c['text_muted']};
            font-size: 0.88rem;
            margin-bottom: 1.25rem;
        }}

        .bullet-item {{
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            padding: 0.65rem 0;
            border-bottom: 1px solid {c['border']};
            color: {c['text']};
            font-size: 0.92rem;
            line-height: 1.55;
        }}

        .bullet-item:last-child {{
            border-bottom: none;
        }}

        .bullet-dot {{
            flex-shrink: 0;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: {c['primary']};
            margin-top: 0.55rem;
        }}

        .empty-state {{
            text-align: center;
            padding: 3.5rem 2rem;
            background: {c['surface_elevated']};
            border: 1px dashed {c['border_light']};
            border-radius: 16px;
        }}

        .empty-state-icon {{
            font-size: 2.5rem;
            margin-bottom: 1rem;
            opacity: 0.5;
        }}

        .empty-state h3 {{
            color: {c['text']};
            font-size: 1.1rem;
            font-weight: 600;
            margin: 0 0 0.5rem 0;
        }}

        .empty-state p {{
            color: {c['text_muted']};
            font-size: 0.9rem;
            margin: 0;
            max-width: 360px;
            margin-left: auto;
            margin-right: auto;
        }}

        .input-panel-header {{
            font-size: 1rem;
            font-weight: 600;
            color: {c['text']};
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .step-indicator {{
            display: flex;
            gap: 0.5rem;
            margin: 1rem 0;
        }}

        .step {{
            flex: 1;
            text-align: center;
            padding: 0.5rem;
            border-radius: 8px;
            font-size: 0.75rem;
            font-weight: 500;
            color: {c['text_subtle']};
            background: {c['surface']};
            border: 1px solid {c['border']};
        }}

        .step-active {{
            color: {c['primary']};
            background: {c['primary_soft']};
            border-color: rgba(59, 130, 246, 0.4);
        }}

        .footer-note {{
            text-align: center;
            color: {c['text_subtle']};
            font-size: 0.78rem;
            margin-top: 2.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid {c['border']};
        }}

        .syllabus-tag {{
            display: inline-block;
            background: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 0.35rem 0.7rem;
            margin: 0.25rem 0.25rem 0.25rem 0;
            font-size: 0.82rem;
            color: {c['accent']};
        }}

        /* Hide radio circle styling for segmented control look */
        div[data-testid="stRadio"] > div {{
            gap: 0.5rem;
        }}

        div[data-testid="stRadio"] label {{
            background: {c['surface_elevated']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            padding: 0.5rem 1rem !important;
            font-weight: 500;
        }}

        div[data-testid="stRadio"] label[data-checked="true"] {{
            border-color: {c['primary']};
            background: {c['primary_soft']};
            color: {c['primary']};
        }}

        /* Markdown report content */
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3 {{
            color: {c['text']} !important;
            font-weight: 600 !important;
            margin-top: 1.25rem !important;
            margin-bottom: 0.5rem !important;
        }}

        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li {{
            color: {c['text_muted']} !important;
            line-height: 1.7 !important;
        }}

        [data-testid="stMarkdownContainer"] table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            font-size: 0.88rem;
        }}

        [data-testid="stMarkdownContainer"] th {{
            background: {c['surface']};
            color: {c['text']};
            padding: 0.6rem 0.75rem;
            border: 1px solid {c['border']};
            text-align: left;
        }}

        [data-testid="stMarkdownContainer"] td {{
            padding: 0.55rem 0.75rem;
            border: 1px solid {c['border']};
            color: {c['text_muted']};
        }}

        [data-testid="stMarkdownContainer"] code {{
            background: {c['surface']};
            color: {c['accent']};
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85em;
        }}

        [data-testid="stMarkdownContainer"] blockquote {{
            border-left: 3px solid {c['primary']};
            padding-left: 1rem;
            color: {c['text_muted']};
            margin: 0.75rem 0;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
