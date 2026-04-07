import os
import sys
import json
import sqlite3
import time
import uuid
import hashlib
import traceback
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# Ensure the project root is in the Python path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.core.callbacks import BaseCallback
from src.infrastructure.config.config import get_settings, set_obsidian_vault_path
from src.infrastructure.persistence.db import DB_PATH, clear_vault_index, init_db
from src.application.orchestration.orchestrator import Orchestrator
from src.infrastructure.obsidian.vault_catalog import create_vault, list_vaults
from src.infrastructure.obsidian.vault_manager import sync_vault
from src.infrastructure.obsidian.file_processor import extract_text_from_file, get_model_capabilities
from src.interfaces.streamlit.streamlit_compat import apply_streamlit_shutdown_patch
from src.prompts.personas import PERSONAS

apply_streamlit_shutdown_patch()

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Second Brain — Claude",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Theme State
# ─────────────────────────────────────────────────────────────────────────────
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "light"

# ─────────────────────────────────────────────────────────────────────────────
# Design system — Claude Editorial (Dynamic)
# ─────────────────────────────────────────────────────────────────────────────

def inject_custom_css(mode: str):
    # ── Parchment (Light) vs Near Black (Dark) ──────────────────────────────
    is_light = mode == "light"

    bg_page       = "#f5f4ed" if is_light else "#141413"
    bg_card       = "#faf9f5" if is_light else "#1e1e1c"
    bg_popover    = "#ffffff" if is_light else "#252523"
    bg_sidebar    = "#e8e6dc" if is_light else "#141413"
    bg_input      = "#ffffff" if is_light else "#252523"

    text_primary  = "#141413" if is_light else "#faf9f5"
    text_secondary= "#5e5d59" if is_light else "#87867f"
    text_light    = "#faf9f5"  # for use on dark surfaces

    border_color  = "#e8e6dc" if is_light else "#30302e"
    accent        = "#c96442"
    ring_warm     = "#d1cfc5" if is_light else "#4d4c48"
    warm_sand     = "#e8e6dc" if is_light else "#2a2a28"
    charcoal_warm = "#4d4c48" if is_light else "#b0aea5"

    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap');

/* ── CSS Tokens ─────────────────────────────────────────────────────── */
:root {{
    --bg-page:      {bg_page};
    --bg-card:      {bg_card};
    --bg-popover:   {bg_popover};
    --bg-input:     {bg_input};
    --text-primary: {text_primary};
    --text-secondary:{text_secondary};
    --border-color: {border_color};
    --accent:       {accent};
    --ring-warm:    {ring_warm};
    --warm-sand:    {warm_sand};
    --charcoal-warm:{charcoal_warm};
    --font-serif: 'Source Serif 4', Georgia, serif;
    --font-sans:  system-ui, Arial, sans-serif;
    --font-mono:  'IBM Plex Mono', monospace;
}}

/* ── Global Canvas ──────────────────────────────────────────────────── */
.stApp, .stApp > div, .main, .block-container {{
    background-color: {bg_page} !important;
    color: {text_primary} !important;
    font-family: var(--font-sans);
}}

header[data-testid="stHeader"] {{
    background-color: {bg_page} !important;
    border-bottom: 1px solid {border_color} !important;
}}

/* ── Sidebar (Always Dark) ──────────────────────────────────────────── */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {{
    background-color: {bg_sidebar} !important;
}}

section[data-testid="stSidebar"] * {{
    color: {("#141413" if is_light else "#faf9f5")} !important;
}}

/* Extra specific for headings and captions in sidebar */
section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2, 
section[data-testid="stSidebar"] h3, 
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] p {{
    color: {("#141413" if is_light else "#faf9f5")} !important;
    opacity: 1 !important;
}}

section[data-testid="stSidebar"] .stButton > button {{
    background: {("#ffffff" if is_light else "#262624")} !important;
    color: {("#141413" if is_light else "#faf9f5")} !important;
    border: 1px solid {("#e8e6dc" if is_light else "#30302e")} !important;
    border-radius: 8px !important;
    box-shadow: {("0 1px 2px rgba(0,0,0,0.05)" if is_light else "none")} !important;
    transition: all 0.15s ease !important;
    font-weight: 500 !important;
    text-align: left !important;
    padding-left: 12px !important;
}}

section[data-testid="stSidebar"] .stButton > button:hover {{
    background: {("#f5f4ed" if is_light else "#2d2d2b")} !important;
    border-color: {accent} !important;
    color: {accent} !important;
    box-shadow: {("0 2px 4px rgba(0,0,0,0.08)" if is_light else "none")} !important;
}}

/* ── Typography  ──────────────────────────────────────────────────── */
h1, h2, h3 {{
    font-family: var(--font-serif) !important;
    font-weight: 500 !important;
    color: {text_primary} !important;
    line-height: 1.25 !important;
}}

/* ── Main Area All Text ────────────────────────────────────────────── */
.main label,
.main p,
.main span,
.main small,
.main .stCaption,
.stMarkdown, .stMarkdown * {{
    color: {text_primary} !important;
}}

/* Force non-sidebar text */
.stApp *:not(section[data-testid="stSidebar"] *) {{
    color: {text_primary};
}}

/* Force override colors on sidebar */
section[data-testid="stSidebar"] * {{
    color: {("#141413" if is_light else "#faf9f5")} !important;
}}

/* ── Buttons: All Non-Sidebar ─────────────────────────────────────── */
.stButton > button {{
    background: {warm_sand} !important;
    color: {charcoal_warm} !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 8px 18px !important;
    font-weight: 600 !important;
    box-shadow: {ring_warm} 0px 0px 0px 1px !important;
    transition: all 0.15s ease !important;
    font-size: 0.9rem !important;
}}

.stButton > button:hover {{
    background: {warm_sand} !important;
    box-shadow: {accent} 0px 0px 0px 1px !important;
    color: {accent} !important;
}}

/* Sidebar buttons dynamic matching */
section[data-testid="stSidebar"] .stButton > button {{
    background: {("#faf9f5" if is_light else "#262624")} !important;
    color: {("#141413" if is_light else "#faf9f5")} !important;
    border: 1px solid {("#d1cfc5" if is_light else "#30302e")} !important;
    box-shadow: none !important;
    font-weight: 500 !important;
}}

section[data-testid="stSidebar"] .stButton > button:hover {{
    border-color: {accent} !important;
    color: {accent} !important;
    background: {("#ffffff" if is_light else "#262624")} !important;
}}

/* Popover trigger button ─────────────────────────────────────────── */
div[data-testid="stPopover"] button {{
    background: {warm_sand} !important;
    color: {charcoal_warm} !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 8px 18px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    box-shadow: {ring_warm} 0px 0px 0px 1px !important;
    transition: all 0.15s ease !important;
}}

div[data-testid="stPopover"] button:hover {{
    box-shadow: {accent} 0px 0px 0px 1px !important;
    color: {accent} !important;
}}

/* ── Text Inputs ──────────────────────────────────────────────────── */
div[data-testid="stTextArea"] textarea,
div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input {{
    background: {bg_input} !important;
    color: {text_primary} !important;
    border: 1px solid {border_color} !important;
    border-radius: 10px !important;
}}

div[data-testid="stTextArea"] textarea:focus,
div[data-testid="stTextInput"] input:focus {{
    border-color: var(--focus-blue) !important;
    box-shadow: 0 0 0 1px var(--focus-blue) !important;
}}

/* Placeholder Contrast */
::placeholder {{
    color: {("#5e5d59" if mode == "light" else "#87867f")} !important;
    opacity: 1 !important;
}}

/* ── Selectbox ───────────────────────────────────────────────────── */
div[data-testid="stSelectbox"] > div > div > div,
div[data-testid="stSelectbox"] > label {{
    color: {text_primary} !important;
}}

div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div {{
    background: {bg_input} !important;
    border: 1px solid {border_color} !important;
    border-radius: 10px !important;
    color: {text_primary} !important;
}}

/* ── Popover & Dropdown Panels ───────────────────────────────────── */
div[data-baseweb="popover"],
div[data-baseweb="popover"] > div,
div[data-baseweb="menu"],
div[data-baseweb="select"] div[role="listbox"],
ul[role="listbox"],
ul[data-baseweb="menu"] {{
    background: {bg_popover} !important;
    border: 1px solid {border_color} !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,{'0.08' if is_light else '0.4'}) !important;
}}

div[data-baseweb="popover"] *,
div[data-baseweb="menu"] *,
div[role="listbox"] *,
ul[role="listbox"] *,
ul[role="listbox"] li {{
    background: transparent !important;
    color: {text_primary} !important;
}}

li[data-baseweb="menu-item"]:hover {{
    background: {warm_sand} !important;
}}

/* ── Stacked container (popover wrapper) ─────────────────────────── */
[data-testid="stPopover"] > div:last-child,
[data-testid="stPopover"] > div:last-child * {{
    background: {bg_popover} !important;
    color: {text_primary} !important;
}}

/* ── Chat Messages ───────────────────────────────────────────────── */
.stChatMessage {{
    background: {bg_card} !important;
    border: 1px solid {border_color} !important;
    border-radius: 12px !important;
    margin-bottom: 10px !important;
}}

.stChatMessage * {{
    color: {text_primary} !important;
}}

/* ── Tabs ────────────────────────────────────────────────────────── */
div[data-baseweb="tab-list"] {{
    background: transparent !important;
    gap: 24px;
}}

div[data-baseweb="tab"] {{
    background: transparent !important;
    color: {text_secondary} !important;
    border-bottom: 2px solid transparent !important;
}}

div[aria-selected="true"][data-baseweb="tab"] {{
    border-bottom: 2px solid {accent} !important;
    color: {accent} !important;
}}

/* ── Agent Cards ─────────────────────────────────────────────────── */
.agent-card {{
    border-radius: 12px;
    padding: 1rem 1.25rem;
    background: {bg_card};
    border: 1px solid {border_color} !important;
    margin: 8px 0 !important;
    width: 100% !important;
    box-shadow: 0 2px 12px rgba(0,0,0,{'0.03' if is_light else '0.15'});
    text-align: left !important;
    min-height: 48px;
    display: flex;
    align-items: center;
}}

.agent-card-role {{
    font-size: 0.85rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: {accent} !important;
    font-family: var(--font-sans);
    font-weight: 600 !important;
    text-align: left !important;
}}

.agent-tag {{
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    background: rgba(201, 100, 66, 0.08);
    border: 1px solid rgba(201, 100, 66, 0.2);
    color: {accent};
    font-size: 0.75rem;
    margin-bottom: 0.75rem;
}}

/* ── Address Badges ─────────────────────────────────────────────── */
.address-badge, 
section[data-testid="stSidebar"] .address-badge {{
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.75rem !important;
    background: {("#faf9f5" if is_light else "#1f1f1e")} !important;
    color: {("#141413" if is_light else "#faf9f5")} !important;
    padding: 0.2rem 0.6rem !important;
    border-radius: 6px !important;
    border: 1px solid var(--border-warm) !important;
    display: inline-block !important;
    word-break: break-all !important;
    font-weight: 500 !important;
    margin-top: 0.25rem;
}}

/* ── Primary Buttons ─────────────────────────────────────────────── */
button[kind="primary"],
div[data-testid="stFormSubmitButton"] button {{
    background: {accent} !important;
    color: #faf9f5 !important;
    border-radius: 10px !important;
    border: none !important;
}}

/* ── Dividers ────────────────────────────────────────────────────── */
hr {{
    border-color: {border_color} !important;
}}

/* ── Info / Alert Boxes ──────────────────────────────────────────── */
div[data-testid="stInfoBox"] {{
    background: {bg_card} !important;
    border-color: {border_color} !important;
    color: {text_primary} !important;
}}

/* ── Expanders ───────────────────────────────────────────────────── */
div[data-testid="stExpander"] {{
    background: {bg_card} !important;
    border: 1px solid {border_color} !important;
    border-radius: 8px !important;
}}

div[data-testid="stExpander"] details summary {{
    color: {text_primary} !important;
    background: {bg_card} !important;
}}

div[data-testid="stExpander"] details summary:hover {{
    color: {accent} !important;
}}

div[data-testid="stExpander"] > div[role="region"] {{
    background: {bg_card} !important;
    color: {text_primary} !important;
}}

/* ── Code Blocks (Force Theme Match) ────────────────────────────── */
code {{
    background: {("#f5f4ed" if is_light else "#2d2d2b")} !important;
    color: {("#c96442" if is_light else "#e8e6dc")} !important;
    padding: 0.2rem 0.4rem !important;
    border-radius: 4px !important;
}}

pre, [data-testid="stCode"] {{
    background: {("#f8f7f2" if is_light else "#1a1a19")} !important;
    border: 1px solid {border_color} !important;
    border-radius: 8px !important;
}}

[data-testid="stCode"] * {{
    background: transparent !important;
}}

/* ── Minimalist Loader ────────────────────────────────────────────── */
.minimal-loader-container {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 1rem 0;
    color: {text_secondary};
    font-family: var(--font-sans);
    font-size: 0.85rem;
}}

.dots-loader {{
    display: flex;
    gap: 4px;
}}

.dot {{
    width: 5px;
    height: 5px;
    background-color: {text_secondary};
    border-radius: 50%;
    animation: dot-pulse 1.4s infinite ease-in-out;
}}
.dot:nth-child(2) {{ animation-delay: 0.2s; }}
.dot:nth-child(3) {{ animation-delay: 0.4s; }}

@keyframes dot-pulse {{
    0%, 80%, 100% {{ transform: scale(0.6); opacity: 0.3; }}
    40% {{ transform: scale(1.1); opacity: 0.8; }}
}}

.loader-timer {{
    font-family: var(--font-mono);
    opacity: 0.6;
    font-size: 0.75rem;
}}

/* ── Result States ───────────────────────────────────────────────── */
.success-banner {{
    background: rgba(46, 125, 50, 0.05);
    border: 1px solid rgba(46, 125, 50, 0.2);
    color: #2e7d32;
    padding: 1rem;
    border-radius: 10px;
    margin: 1rem 0;
    font-size: 0.9rem;
}}

.refinement-box {{
    background: rgba(2, 136, 209, 0.05);
    border: 1px solid rgba(2, 136, 209, 0.2);
    color: #0288d1;
    padding: 1rem;
    border-radius: 10px;
    margin: 1rem 0;
}}

.refinement-box ul {{
    margin: 0.5rem 0 0 1.25rem;
    padding: 0;
}}
</style>
""", unsafe_allow_html=True)

inject_custom_css(st.session_state.theme_mode)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers & Cache
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def cached_init_db(): init_db()

@st.cache_resource
def cached_get_settings(): return get_settings()

@st.cache_data(ttl=60)
def get_vault_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT name, path, type FROM vault_nodes", conn)
        conn.close()
        if not df.empty: df["path"] = df["path"].str.replace("\\", "/", regex=False)
        return df
    except: return pd.DataFrame()

def _vault_name_from_path(path: str | None) -> str | None:
    if not path: return None
    clean = path.rstrip("/\\")
    return os.path.basename(clean) or clean

def get_active_vault_path(): return st.session_state.get("active_vault_path")
def get_active_vault_name(): return st.session_state.get("active_vault_name") or _vault_name_from_path(get_active_vault_path())

def _try_parse_json(raw_text: str):
    try: return json.loads(raw_text)
    except: return None

def render_minimal_loader():
    if not st.session_state.processing_start_time:
        return
    
    elapsed = time.time() - st.session_state.processing_start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    timer_str = f"{minutes:02d}:{seconds:02d}s"
    
    st.markdown(f"""
        <div class="minimal-loader-container">
            <div class="dots-loader">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
            <div class="loader-phrase">{st.session_state.loading_phrase}</div>
            <div class="loader-timer">{timer_str}</div>
        </div>
    """, unsafe_allow_html=True)

def _format_agent_result(agent_name: str, raw_text: str) -> dict:
    parsed = _try_parse_json(raw_text) if isinstance(raw_text, str) else None
    
    # Minimalist status indicators for all agents
    status_map = {
        "Manager": "◈ Coordinando",
        "Planner": "◈ Planificando",
        "Researcher": "◈ Investigando",
        "Builder": "◈ Construyendo/Escribiendo",
        "Standard": "◈ Procesando"
    }
    
    title_prefix = status_map.get(agent_name, f"◈ {agent_name}")
    
    if agent_name == "Manager" and isinstance(parsed, dict):
        next_agent = parsed.get("next_agent")
        instruction = parsed.get("instruction", "")
        
        if next_agent == "User":
            return {
                "title": "◈ ¡Todo listo! Revisión requerida",
                "body_html": f'<div class="success-banner"><strong>Fase finalizada:</strong><br>{instruction[:250]}...</div>',
                "show_raw": True
            }
        
        # Simplified Natural Language summary for intermediate steps
        npl_summary = f"El Coordinador ha asignado la siguiente fase a **{next_agent}**." if next_agent else "El Coordinador está procesando la solicitud."
        
        return {
            "title": f"{title_prefix}: {next_agent}" if next_agent else title_prefix,
            "body_html": f'<div class="agent-card-body">{npl_summary}</div>', 
            "show_raw": True
        }
            
    # For other agents, provide a short summary or just the title
    safe_text = str(raw_text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    
    return {
        "title": title_prefix, 
        "body_html": f'<div class="agent-card-body">{safe_text}</div>', 
        "show_raw": False
    }

def render_agent_output(agent_name: str, raw_text: str):
    view = _format_agent_result(agent_name, raw_text)
    
    # Render the minimalist badge
    st.markdown(f'<div class="agent-card"><div class="agent-card-role">{view["title"]}</div></div>', unsafe_allow_html=True)
    
    # Hide verbose content in a discreet expander
    if view["body_html"] or view["show_raw"]:
        with st.expander(f"Ver reporte de {agent_name}"):
            if view["body_html"]:
                st.markdown(view["body_html"], unsafe_allow_html=True)
            if view["show_raw"]:
                st.code(raw_text, language="json")

# ─────────────────────────────────────────────────────────────────────────────
# Async Runner
# ─────────────────────────────────────────────────────────────────────────────

def _bg_sync_vault(vault_path: str):
    try:
        st.session_state.syncing_vault = True
        sync_vault(vault_path)
    finally:
        st.session_state.syncing_vault = False
        st.session_state.last_sync_ts = datetime.now().strftime("%H:%M:%S")

def _run_orchestrator_bg(task_id: str, final_prompt: str, mode: str, workflow: str):
    try:
        st.session_state.is_processing = True
        class BGCallback(BaseCallback):
            def on_agent_start(self, name, instr):
                st.session_state.agent_status_updates.append(f"● {name} working...")
            def on_agent_end(self, name, res):
                st.session_state.messages.append({"role": "assistant", "agent": name, "content": res})
                st.session_state.agent_status_updates.append(f"✓ {name} done.")
            def on_system_message(self, msg, mtype="info"): pass
        callback = BGCallback()
        orchestrator = Orchestrator(callback=callback)
        orchestrator.process_task(task_id, final_prompt, mode=mode, workflow=workflow)
    except Exception as e:
        st.session_state.messages.append({"role": "assistant", "content": f"🚨 Error: {e}"})
    finally:
        st.session_state.is_processing = False

def activate_vault(vault_path: str):
    normalized = set_obsidian_vault_path(vault_path, persist=True)
    if not normalized: return None
    st.session_state.active_vault_path = normalized
    st.session_state.active_vault_name = _vault_name_from_path(normalized)
    st.session_state.selected_note = None
    clear_vault_index()
    
    t = threading.Thread(target=_bg_sync_vault, args=(normalized,), daemon=True)
    add_script_run_ctx(t)
    t.start()
    
    return normalized

# ─────────────────────────────────────────────────────────────────────────────
# Session State Init
# ─────────────────────────────────────────────────────────────────────────────
cached_init_db()
settings = cached_get_settings()

if "messages" not in st.session_state: st.session_state.messages = []
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())[:8]
if "active_vault_path" not in st.session_state:
    initial = set_obsidian_vault_path(settings.obsidian_vault_path) if settings.obsidian_vault_path else None
    st.session_state.active_vault_path = initial
if "vault_palette_open" not in st.session_state: st.session_state.vault_palette_open = True
if "syncing_vault" not in st.session_state: st.session_state.syncing_vault = False
if "last_sync_ts" not in st.session_state: st.session_state.last_sync_ts = "Never"
if "agent_status_updates" not in st.session_state: st.session_state.agent_status_updates = []
if "is_processing" not in st.session_state: st.session_state.is_processing = False
if "active_mode" not in st.session_state:
    st.session_state.active_mode = list(PERSONAS.keys())[0] if PERSONAS else None
if "active_workflow" not in st.session_state: st.session_state.active_workflow = "Plan"
if "uploaded_files_signature" not in st.session_state: st.session_state.uploaded_files_signature = ()
if "extra_context_files" not in st.session_state: st.session_state.extra_context_files = ""
if "extra_context_pasted" not in st.session_state: st.session_state.extra_context_pasted = ""
if "processing_start_time" not in st.session_state: st.session_state.processing_start_time = None
if "loading_phrase" not in st.session_state: st.session_state.loading_phrase = ""

# ─────────────────────────────────────────────────────────────────────────────
# UI: Vault Launcher (Full Page)
# ─────────────────────────────────────────────────────────────────────────────

def render_vault_launcher():
    st.markdown("""<div style="max-width: 800px; margin: 10vh auto; text-align: center;"><h1>Vault Launcher</h1><p style="color: var(--text-secondary);">Select the foundation for your second brain.</p></div>""", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 2, 1])
    with center:
        tab_recent, tab_browse, tab_new = st.tabs(["Recent Vaults", "Browse Local", "Create New"])
        with tab_recent:
            vaults = list_vaults(active_path=get_active_vault_path())
            if vaults:
                for vault in vaults:
                    col_info, col_btn = st.columns([3.5, 1], vertical_alignment="center")
                    with col_info: 
                        st.markdown(f"**{vault.name}**")
                        st.markdown(f'<div class="address-badge">{vault.path}</div>', unsafe_allow_html=True)
                    with col_btn:
                        if st.button("Open", key=f"open_{vault.path}", use_container_width=True):
                            activate_vault(vault.path)
                            st.session_state.vault_palette_open = False
                            st.rerun()
                    st.divider()
            else: st.info("No recent vaults found.")
        
        with tab_browse:
            st.markdown("Select a folder as your vault using Windows Explorer.")
            if st.button("Browse via File Explorer...", use_container_width=True):
                import tkinter as tk; from tkinter import filedialog
                root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
                folder_path = filedialog.askdirectory(master=root, title="Select Vault Directory")
                root.destroy()
                if folder_path:
                    activate_vault(os.path.abspath(folder_path))
                    st.session_state.vault_palette_open = False
                    st.rerun()

        with tab_new:
            new_name = st.text_input("Vault Name", placeholder="e.g. My Notes")
            if st.button("Create & Open", use_container_width=True, type="primary"):
                if new_name:
                    new_v = create_vault(new_name)
                    activate_vault(new_v.path)
                    st.session_state.vault_palette_open = False
                    st.rerun()

if st.session_state.vault_palette_open or not get_active_vault_path():
    render_vault_launcher()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ◈ Second Brain")
    
    # Theme Toggle
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1: st.caption(f"Session: `{st.session_state.session_id}`")
    with col_t2:
        if st.button("☾" if st.session_state.theme_mode == "light" else "☀"):
            st.session_state.theme_mode = "dark" if st.session_state.theme_mode == "light" else "light"
            st.rerun()
            
    st.divider()
    st.markdown(f"**Vault** — {get_active_vault_name()}")
    st.markdown(f'<div class="address-badge">{get_active_vault_path()}</div>', unsafe_allow_html=True)
    if st.button("↗ Switch Vault", use_container_width=True):
        st.session_state.vault_palette_open = True
        st.rerun()
        
    if st.session_state.syncing_vault: st.markdown("**(↻ Syncing...)**")
    else: 
        st.caption(f"Last sync: {st.session_state.last_sync_ts}")
        if st.button("↻ Force refresh", use_container_width=True):
            activate_vault(get_active_vault_path())
            st.rerun()
    st.divider()
    if st.button("＋ New conversation", use_container_width=True):
        st.session_state.messages = []; st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Main Interface
# ─────────────────────────────────────────────────────────────────────────────
chat_area = st.container(height=520, border=False)
with chat_area:
    if not st.session_state.messages:
        st.markdown("""<div style="text-align: center; padding-top: 10vh;"><h2>Start building...</h2><p style="color: var(--text-secondary);">Describe your request below.</p></div>""", unsafe_allow_html=True)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if "agent" in msg: render_agent_output(msg["agent"], msg["content"])
            else: st.markdown(msg["content"])
    
    # Inline loader as the next assistant message
    if st.session_state.is_processing:
        with st.chat_message("assistant"):
            render_minimal_loader()

# ── Composer (Input Bar) ─────────────────────────────────────────────
with st.container(border=True):
    toolbar_l, toolbar_m, toolbar_r = st.columns([0.2, 0.5, 0.3], vertical_alignment="bottom")
    
    with toolbar_l:
        with st.popover("Attach", use_container_width=True):
            uploaded = st.file_uploader("Upload context", type=["md", "txt", "pdf"], accept_multiple_files=True)
            if uploaded:
                texts = []
                for f in uploaded: texts.append(f"--- {f.name} ---\n{extract_text_from_file(f)}")
                st.session_state.extra_context_files = "\n\n".join(texts)
                st.success("Files attached.")
            pasted = st.text_area("Paste text", placeholder="Context...", height=80)
            st.session_state.extra_context_pasted = pasted

    with toolbar_m:
        col_wf, col_md = st.columns(2, vertical_alignment="bottom")
        with col_wf:
            workflow = st.selectbox("Workflow", ["Plan", "Execute"], index=0 if st.session_state.active_workflow=="Plan" else 1)
            st.session_state.active_workflow = workflow
        with col_md:
            mode = st.selectbox("Mode", list(PERSONAS.keys()), index=list(PERSONAS.keys()).index(st.session_state.active_mode))
            st.session_state.active_mode = mode

    prompt = st.text_area("Prompt", placeholder="What do you need?", height=85, key="main_prompt", label_visibility="collapsed")
    
    with toolbar_r:
        if st.button("Send", type="primary", use_container_width=True, disabled=st.session_state.is_processing):
            if prompt.strip():
                st.session_state.messages.append({"role": "user", "content": prompt.strip()})
                # Prepare final prompt with context
                ctx = []
                if st.session_state.extra_context_files: ctx.append(st.session_state.extra_context_files)
                if st.session_state.extra_context_pasted: ctx.append(st.session_state.extra_context_pasted)
                final = prompt.strip()
                if ctx: final = f"=== CONTEXT ===\n" + "\n\n".join(ctx) + f"\n\nTask: {final}"
                
                st.session_state.agent_status_updates = []
                st.session_state.processing_start_time = time.time()
                import random
                phrases = ["Synthesizing context...", "Orchestrating agents...", "Structuring response...", "Parsing vault details...", "Refining proposed plan...", "Optimizing agent output...", "Finalizing results..."]
                st.session_state.loading_phrase = random.choice(phrases)
                
                t = threading.Thread(target=_run_orchestrator_bg, args=(st.session_state.session_id, final, st.session_state.active_mode, st.session_state.active_workflow), daemon=True)
                add_script_run_ctx(t)
                t.start()
                st.rerun()

if st.session_state.is_processing:
    time.sleep(1.0)
    st.rerun()
