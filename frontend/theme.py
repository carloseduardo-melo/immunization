"""Design system compartilhado do frontend: tokens de cor/tipografia e o CSS
global injetado em todas as telas (login, sidebar, registros, municípios)."""

import streamlit as st

COLORS = {
    "primary": "#5b5bf6",
    "primary_hover": "#4f46e5",
    "primary_soft": "#eef2ff",
    "ink": "#18181b",
    "text": "#3f3f46",
    "muted": "#71717a",
    "border": "#e4e4e7",
    "surface": "#ffffff",
    "bg": "#fafafa",
    "sidebar_bg": "#5551ff",
    "sidebar_bg_active": "#4541e6",
    "sidebar_text": "#e8e8ff",
    "sidebar_text_active": "#ffffff",
}

BADGE_TONES = {
    "success": ("#dcfce7", "#15803d"),
    "warning": ("#fef3c7", "#b45309"),
    "neutral": ("#f4f4f5", "#52525b"),
    "alta": ("#f3e8ff", "#7e22ce"),
    "danger": ("#fee2e2", "#b91c1c"),
}


def badge_html(label: str, tone: str) -> str:
    bg, color = BADGE_TONES.get(tone, BADGE_TONES["neutral"])
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'font-size:12px;font-weight:500;background:{bg};color:{color};">{label}</span>'
    )


def inject_global_styles() -> None:
    c = COLORS
    st.markdown(
        f"""
        <style>
        :root {{
            --font-sans: -apple-system, "Segoe UI", Inter, system-ui, sans-serif;
        }}

        html, body, [data-testid="stAppViewContainer"], .stApp {{
            font-family: var(--font-sans);
            background: {c["bg"]} !important;
        }}

        /* --- TIPOGRAFIA --- */
        .page-title {{
            font-size: 24px;
            font-weight: 600;
            color: {c["ink"]};
            letter-spacing: -0.3px;
            margin-bottom: 4px;
        }}
        .page-subtitle {{
            font-size: 14px;
            color: {c["muted"]};
            margin-top: 0px;
            margin-bottom: 24px;
        }}
        .card-title {{
            font-size: 15px;
            font-weight: 600;
            color: {c["text"]};
            margin-bottom: 16px;
        }}

        /* --- BOTÕES --- */
        button[kind="primary"] {{
            background-color: {c["primary"]} !important;
            border-color: {c["primary"]} !important;
            color: #ffffff !important;
            border-radius: 6px !important;
            font-weight: 500 !important;
        }}
        button[kind="primary"]:hover {{
            background-color: {c["primary_hover"]} !important;
            border-color: {c["primary_hover"]} !important;
        }}
        button[kind="secondary"] {{
            background-color: {c["surface"]} !important;
            border: 1px solid {c["border"]} !important;
            color: {c["text"]} !important;
            border-radius: 6px !important;
            font-size: 13px !important;
            min-height: 34px !important;
        }}
        button[kind="secondary"]:hover {{
            border-color: #d4d4d8 !important;
            color: {c["ink"]} !important;
        }}

        /* --- INPUTS E FORMULÁRIOS --- */
        [data-baseweb="input"],
        [data-baseweb="select"] > div {{
            background-color: {c["surface"]} !important;
            border: 1px solid {c["border"]} !important;
            border-radius: 6px !important;
        }}
        [data-baseweb="input"]:focus-within,
        [data-baseweb="select"] > div:focus-within {{
            border-color: {c["primary"]} !important;
        }}
        input, .stSelectbox div {{
            font-size: 14px !important;
            color: {c["text"]} !important;
        }}
        [data-testid="stCheckbox"] label span {{
            font-size: 13px !important;
            color: {c["text"]} !important;
        }}

        /* --- CARDS / CONTAINERS --- */
        [data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 8px !important;
            border-color: {c["border"]} !important;
            background: {c["surface"]} !important;
            padding: 1rem !important;
        }}
        hr {{
            margin: 0.75rem 0 !important;
            border-color: {c["bg"]} !important;
        }}

        /* --- SIDEBAR DE NAVEGAÇÃO --- */
        [data-testid="stSidebar"] {{
            background: {c["sidebar_bg"]} !important;
        }}
        [data-testid="stSidebar"] * {{
            color: {c["sidebar_text"]} !important;
        }}
        [data-testid="stSidebar"] hr {{
            border-color: rgba(255,255,255,0.18) !important;
        }}
        .sidebar-brand {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 4px 0 20px 0;
        }}
        .sidebar-brand-mark {{
            width: 34px;
            height: 34px;
            border-radius: 9px;
            background: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .sidebar-brand-mark-inner {{
            width: 13px;
            height: 13px;
            border-radius: 3px;
            background: {c["sidebar_bg"]};
        }}
        .sidebar-brand-text {{
            font-size: 15px;
            font-weight: 700;
            color: #ffffff !important;
            line-height: 1.25;
            letter-spacing: -0.2px;
        }}
        .sidebar-section-label {{
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: {c["sidebar_text"]} !important;
            opacity: 0.7;
            margin: 4px 0 8px 4px;
        }}
        .sidebar-profile {{
            font-size: 13px;
            color: {c["sidebar_text"]} !important;
            margin-bottom: 10px;
        }}
        [data-testid="stSidebar"] button[kind="secondary"] {{
            background: transparent !important;
            border: 1px solid transparent !important;
            text-align: left !important;
            justify-content: flex-start !important;
            font-weight: 500 !important;
        }}
        [data-testid="stSidebar"] button[kind="secondary"] p {{
            color: {c["sidebar_text"]} !important;
        }}
        [data-testid="stSidebar"] button[kind="secondary"]:hover {{
            background: rgba(255,255,255,0.12) !important;
        }}
        [data-testid="stSidebar"] button[kind="secondary"]:hover p {{
            color: #ffffff !important;
        }}
        [data-testid="stSidebar"] button[kind="primary"] {{
            background: #ffffff !important;
            border-color: #ffffff !important;
            text-align: left !important;
            justify-content: flex-start !important;
        }}
        [data-testid="stSidebar"] button[kind="primary"] p {{
            color: {c["sidebar_bg"]} !important;
            font-weight: 600 !important;
        }}
        [data-testid="stSidebar"] button[kind="primary"]:hover {{
            background: #f4f4ff !important;
        }}
        [data-testid="stSidebar"] [data-testid="stButton"] button p {{
            font-size: 14px !important;
        }}

        /* --- CHROME GLOBAL (aplicado em toda a app, inclusive login) --- */
        [data-testid="stHeader"] {{ display: none !important; }}
        footer {{ display: none !important; }}
        #MainMenu {{ display: none !important; }}
        
        /* Anula o card branco indesejado injetado internamente na Sidebar */
        [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {{
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            box-shadow: none !important;
        }}
        
        </style>
        """,
        unsafe_allow_html=True,
    )
