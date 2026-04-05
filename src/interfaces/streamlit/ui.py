import os
import sys

# Ensure the project root is in the Python path so that 'src' can be found.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
import sqlite3
import time
import uuid
import hashlib
import traceback
from datetime import datetime

import pandas as pd
import streamlit as st

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
    page_title="Second Brain — AI Team",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Design system — Editorial warm-dark
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --canvas:   #0c0c0c;
    --surface:  #171717;
    --surface2: #1f1f1f;
    --border:   #2a2a2a;
    --border-l: #363636;
    --text-1:   #e8e4de;
    --text-2:   #8a857e;
    --text-3:   #5c5850;
    --accent:   #d4a853;
    --accent-m: rgba(212, 168, 83, 0.10);
    --accent-s: rgba(212, 168, 83, 0.22);
    --green:    #5cb87a;
    --red:      #d45555;
    --amber:    #d4a853;
}

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    color: var(--text-1);
}

code, pre, .stCodeBlock, [data-testid="stCodeBlock"] {
    font-family: 'IBM Plex Mono', monospace !important;
}

/* ── App canvas ────────────────────────────────────────────────────── */
.stApp {
    background: var(--canvas);
}

[data-testid="stMainBlockContainer"] {
    padding-bottom: 0.5rem !important;
    padding-top: 1.2rem !important;
}

/* ── Sidebar ───────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--surface);
    border-right: 1px solid var(--border);
}

section[data-testid="stSidebar"] [data-testid="stMarkdown"] p {
    color: var(--text-2);
    font-size: 0.88rem;
}

/* ── Chat messages ─────────────────────────────────────────────────── */
.stChatMessage {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    margin-bottom: 10px !important;
    padding: 1rem 1.15rem !important;
}

/* ── Buttons — refined, not chunky ─────────────────────────────────── */
.stButton > button {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    padding: 0.5rem 1rem !important;
    border: 1px solid var(--border) !important;
    background: transparent !important;
    color: var(--text-2) !important;
    transition: all 0.15s ease;
    text-align: center !important;
}

.stButton > button:hover {
    color: var(--accent) !important;
    border-color: var(--accent-s) !important;
    background: var(--accent-m) !important;
}

.stButton > button[kind="primary"] {
    background: var(--accent) !important;
    color: #0c0c0c !important;
    border-color: var(--accent) !important;
    font-weight: 600 !important;
}

.stButton > button[kind="primary"]:hover {
    background: #c49a48 !important;
    border-color: #c49a48 !important;
}

/* ── Inputs ─────────────────────────────────────────────────────────── */
div[data-testid="stTextArea"] textarea,
div[data-testid="stTextInput"] input {
    font-family: 'DM Sans', sans-serif !important;
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-1) !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
}

div[data-testid="stTextArea"] textarea:focus,
div[data-testid="stTextInput"] input:focus {
    border-color: var(--accent-s) !important;
    box-shadow: 0 0 0 1px var(--accent-m) !important;
}

div[data-testid="stTextArea"] textarea::placeholder,
div[data-testid="stTextInput"] input::placeholder {
    color: var(--text-3) !important;
}

/* ── Selectbox ─────────────────────────────────────────────────────── */
div[data-baseweb="select"] > div {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

div[data-baseweb="select"] * {
    color: var(--text-1) !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Status widget ─────────────────────────────────────────────────── */
div[data-testid="stStatus"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* ── Expander ──────────────────────────────────────────────────────── */
div[data-testid="stExpander"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}

/* ── Agent output panels ───────────────────────────────────────────── */
.agent-card {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.85rem 1rem;
    background: var(--surface2);
    margin-top: 0.3rem;
}

.agent-card-role {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
    margin-bottom: 0.35rem;
}

.agent-card-body {
    font-family: 'Source Serif 4', serif;
    color: var(--text-1);
    line-height: 1.6;
    font-size: 0.95rem;
}

.agent-tag {
    display: inline-block;
    padding: 0.12rem 0.5rem;
    margin-bottom: 0.4rem;
    border-radius: 4px;
    background: var(--accent-m);
    border: 1px solid var(--accent-s);
    color: var(--accent);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.03em;
}

/* ── Vault launcher ────────────────────────────────────────────────── */
.vault-hero {
    max-width: 720px;
    margin: 8vh auto 0 auto;
    text-align: center;
}

.vault-hero h1 {
    font-family: 'Source Serif 4', serif;
    font-size: 2.2rem;
    font-weight: 600;
    color: var(--text-1);
    margin-bottom: 0.3rem;
}

.vault-hero p {
    font-size: 0.92rem;
    color: var(--text-2);
    max-width: 480px;
    margin: 0 auto 1.5rem;
    line-height: 1.55;
}

.vault-hero .kicker {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--accent);
    margin-bottom: 0.5rem;
}

/* ── Vault cards ───────────────────────────────────────────────────── */
.vault-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.8rem 1rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface);
    margin-bottom: 0.5rem;
    transition: border-color 0.15s ease;
}

.vault-card:hover {
    border-color: var(--border-l);
}

.vault-card.active {
    border-color: var(--accent-s);
    background: var(--accent-m);
}

.vault-card .name {
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--text-1);
}

.vault-card .meta {
    font-size: 0.76rem;
    color: var(--text-3);
    font-family: 'IBM Plex Mono', monospace;
    margin-top: 0.15rem;
}

/* ── Welcome empty state ───────────────────────────────────────────── */
.welcome-state {
    text-align: center;
    padding: 6rem 2rem 4rem;
}

.welcome-state .glyph {
    font-size: 2.8rem;
    margin-bottom: 0.6rem;
    opacity: 0.4;
}

.welcome-state h2 {
    font-family: 'Source Serif 4', serif;
    font-size: 1.35rem;
    font-weight: 600;
    color: var(--text-2);
    margin-bottom: 0.25rem;
}

.welcome-state p {
    font-size: 0.85rem;
    color: var(--text-3);
}

/* ── Audit table ───────────────────────────────────────────────────── */
.audit-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.84rem;
}

.audit-row .ts {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.74rem;
    color: var(--text-3);
    white-space: nowrap;
}

.audit-row .agent {
    font-weight: 600;
    color: var(--text-1);
    white-space: nowrap;
}

.audit-row .file {
    font-family: 'IBM Plex Mono', monospace;
    color: var(--text-2);
    font-size: 0.78rem;
}

.audit-status {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.audit-status.applied { background: rgba(92,184,122,0.12); color: var(--green); }
.audit-status.conflict { background: rgba(212,85,85,0.12); color: var(--red); }
.audit-status.deleted { background: rgba(212,168,83,0.12); color: var(--amber); }

/* ── Hide Streamlit chrome ─────────────────────────────────────────── */
div[data-testid="stTextArea"] label,
div[data-testid="stSelectbox"] label {
    display: none !important;
}

/* ── Dividers ──────────────────────────────────────────────────────── */
hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 0.6rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _try_parse_json(raw_text: str):
    try:
        return json.loads(raw_text)
    except Exception:
        return None


def _format_agent_result(agent_name: str, raw_text: str) -> dict:
    parsed = _try_parse_json(raw_text) if isinstance(raw_text, str) else None

    if agent_name == "Manager" and isinstance(parsed, dict):
        next_agent = parsed.get("next_agent")
        instruction = parsed.get("instruction")
        if isinstance(next_agent, str) and isinstance(instruction, str):
            title = "Coordinator Decision"
            if next_agent.lower() == "user":
                title = "Final Result"
            body = (
                f'<div class="agent-tag">Next → {next_agent}</div>'
                f'<div class="agent-card-body">{instruction}</div>'
            )
            return {"title": title, "body_html": body, "show_raw": True}

    if agent_name == "Critic" and "CRITIC_APPROVED" in raw_text:
        body = (
            '<div class="agent-tag">Approved</div>'
            '<div class="agent-card-body">Quality review passed. Workflow can close.</div>'
        )
        return {"title": "Quality Gate", "body_html": body, "show_raw": True}

    if isinstance(parsed, list) and parsed and all(isinstance(item, dict) for item in parsed):
        list_items = "".join(
            f"<li><strong>{item.get('next_agent', 'Step')}</strong>: {item.get('instruction', '')}</li>"
            for item in parsed
        )
        body = f'<div class="agent-card-body"><ul>{list_items}</ul></div>'
        return {"title": f"{agent_name} Output", "body_html": body, "show_raw": True}

    safe_text = raw_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    return {
        "title": f"{agent_name}",
        "body_html": f'<div class="agent-card-body">{safe_text}</div>',
        "show_raw": False,
    }


def render_agent_output(agent_name: str, raw_text: str):
    view = _format_agent_result(agent_name, raw_text)
    st.markdown(
        f"""
<div class="agent-card">
  <div class="agent-card-role">{view['title']}</div>
  {view['body_html']}
</div>
""",
        unsafe_allow_html=True,
    )
    if view["show_raw"]:
        with st.expander("Raw output", expanded=False):
            st.code(raw_text, language="json")


class StreamlitCallback(BaseCallback):
    def __init__(self, agent_status_placeholders):
        self.placeholders = agent_status_placeholders

    def on_agent_start(self, agent_name: str, instruction: str):
        if agent_name in self.placeholders:
            self.placeholders[agent_name].update(label=f"● {agent_name} — working…", state="running")
            with st.session_state.chat_history_container:
                with st.chat_message("assistant"):
                    st.caption(f"**{agent_name}** received instruction:")
                    st.info(instruction)

    def on_agent_end(self, agent_name: str, result: str):
        if agent_name in self.placeholders:
            self.placeholders[agent_name].update(label=f"✓ {agent_name} — done", state="complete")
            with st.session_state.chat_history_container:
                with st.chat_message("assistant"):
                    render_agent_output(agent_name, result)
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "agent": agent_name,
                    "content": result,
                }
            )

    def on_system_message(self, message: str, mtype: str = "info"):
        st.toast(message)


# ─────────────────────────────────────────────────────────────────────────────
# Vault helpers
# ─────────────────────────────────────────────────────────────────────────────

def _vault_name_from_path(path: str | None) -> str | None:
    if not path:
        return None
    clean = path.rstrip("/\\")
    return os.path.basename(clean) or clean


def get_active_vault_path() -> str | None:
    return st.session_state.get("active_vault_path")


def get_active_vault_name() -> str | None:
    return st.session_state.get("active_vault_name") or _vault_name_from_path(get_active_vault_path())


def activate_vault(vault_path: str) -> str:
    """Activate and always auto-sync."""
    normalized = set_obsidian_vault_path(vault_path, persist=True)
    if not normalized:
        raise ValueError("Could not activate the selected vault.")

    st.session_state.active_vault_path = normalized
    st.session_state.active_vault_name = _vault_name_from_path(normalized)
    st.session_state.selected_note = None

    clear_vault_index()
    sync_vault(normalized)

    return normalized


def resync_active_vault() -> None:
    active_path = get_active_vault_path()
    if not active_path:
        raise ValueError("No active vault.")
    clear_vault_index()
    sync_vault(active_path)


def get_vault_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT name, path, type FROM vault_nodes", conn)
        conn.close()
        if not df.empty:
            df["path"] = df["path"].str.replace("\\", "/", regex=False)
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Vault launcher (full-page)
# ─────────────────────────────────────────────────────────────────────────────

def render_vault_launcher():
    active_path = get_active_vault_path()
    active_name = get_active_vault_name()

    st.markdown(
        """
<div class="vault-hero">
  <div class="kicker">Vault Launcher</div>
  <h1>Choose a workspace</h1>
  <p>Open an existing Obsidian vault, browse your files, or create a new one.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.8, 1])
    with center:
        tab_recent, tab_browse, tab_new = st.tabs(["Recent Vaults", "Browse Local", "Create New"])
        
        with tab_recent:
            search = st.text_input(
                "Search vaults",
                key="vault_search",
                placeholder="Filter by name…",
                label_visibility="collapsed",
            )

            vaults = list_vaults(active_path=active_path)
            query = search.strip().lower()
            filtered = [v for v in vaults if not query or query in v.name.lower() or query in v.path.lower()]

            if filtered:
                for vault in filtered:
                    is_active = vault.path == active_path
                    badge = " · current" if is_active else ""
                    source = "workspace" if vault.source == "workspace" else "external"

                    col_info, col_btn = st.columns([3.5, 1])
                    with col_info:
                        st.markdown(f"**{vault.name}{badge}**")
                        st.caption(f"`{source}` · `{vault.path}`")
                    with col_btn:
                        label = "Continue" if is_active else "Open"
                        if st.button(label, key=f"open_{vault.path}", use_container_width=True):
                            with st.spinner(f"Syncing {vault.name}…"):
                                activate_vault(vault.path)
                            st.session_state.vault_palette_open = False
                            st.rerun()
                    st.divider()
            else:
                st.info("No vaults match your search.")
                
        with tab_browse:
            st.markdown("Use the native Windows File Explorer to select an existing folder as your vault.")
            
            if st.button("Browse via Windows Explorer...", use_container_width=True):
                # We use a nested import to avoid slowing down app load or crashing non-desktop environments
                import tkinter as tk
                from tkinter import filedialog
                
                # Setup a hidden root window for the dialog
                root = tk.Tk()
                root.withdraw()
                # Force the dialog to appear on top of the browser
                root.wm_attributes('-topmost', 1)
                
                folder_path = filedialog.askdirectory(master=root, title="Select Vault Directory")
                root.destroy()
                
                if folder_path:
                    try:
                        normalize_path = os.path.abspath(folder_path)
                        with st.spinner(f"Mounting vault at {normalize_path}…"):
                            activate_vault(normalize_path)
                        st.session_state.vault_palette_open = False
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

        with tab_new:
            st.markdown("Create a new tracked vault inside the default workspace.")
            new_name = st.text_input(
                "Name",
                key="new_vault_name",
                placeholder="e.g. Work, Client A, Sandbox",
                label_visibility="collapsed",
            )
            if st.button("Create & open", key="create_vault_btn", use_container_width=True, type="primary"):
                try:
                    new_vault = create_vault(new_name)
                    with st.spinner(f"Creating {new_vault.name}…"):
                        activate_vault(new_vault.path)
                    st.session_state.clear_new_vault_name = True
                    st.session_state.vault_palette_open = False
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Session state init
# ─────────────────────────────────────────────────────────────────────────────

init_db()
settings = get_settings()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if "selected_note" not in st.session_state:
    st.session_state.selected_note = None
if "active_vault_path" not in st.session_state:
    initial = set_obsidian_vault_path(settings.obsidian_vault_path) if settings.obsidian_vault_path else None
    st.session_state.active_vault_path = initial
    st.session_state.active_vault_name = _vault_name_from_path(initial)
if "active_vault_name" not in st.session_state:
    st.session_state.active_vault_name = _vault_name_from_path(st.session_state.active_vault_path)
if "vault_palette_open" not in st.session_state:
    st.session_state.vault_palette_open = True
if "vault_search" not in st.session_state:
    st.session_state.vault_search = ""
if "new_vault_name" not in st.session_state:
    st.session_state.new_vault_name = ""
if "extra_context_files" not in st.session_state:
    st.session_state.extra_context_files = ""
if "extra_context_pasted" not in st.session_state:
    st.session_state.extra_context_pasted = ""
if "uploaded_files_signature" not in st.session_state:
    st.session_state.uploaded_files_signature = ()
if "active_mode" not in st.session_state:
    persona_options = list(PERSONAS.keys())
    st.session_state.active_mode = persona_options[0] if persona_options else None
if "active_model" not in st.session_state:
    st.session_state.active_model = settings.gemini_models[0] if settings.gemini_models else None
if "clear_new_vault_name" not in st.session_state:
    st.session_state.clear_new_vault_name = False
if "composer_prompt" not in st.session_state:
    st.session_state.composer_prompt = ""
if "clear_composer_prompt" not in st.session_state:
    st.session_state.clear_composer_prompt = False
if "show_audit" not in st.session_state:
    st.session_state.show_audit = False
if "active_workflow" not in st.session_state:
    st.session_state.active_workflow = "Plan"
if "browser_path" not in st.session_state:
    st.session_state.browser_path = os.path.expanduser("~")

# Clear flags
if st.session_state.clear_new_vault_name:
    st.session_state.new_vault_name = ""
    st.session_state.clear_new_vault_name = False
if st.session_state.clear_composer_prompt:
    st.session_state.composer_prompt = ""
    st.session_state.clear_composer_prompt = False

# Validate vault path still exists
active_path = get_active_vault_path()
if active_path and not os.path.isdir(active_path):
    st.session_state.active_vault_path = None
    st.session_state.active_vault_name = None
    st.session_state.vault_palette_open = True

# ─────────────────────────────────────────────────────────────────────────────
# Gate: vault launcher if no vault
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.vault_palette_open or not get_active_vault_path():
    render_vault_launcher()
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — minimal
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### ◈ Second Brain")
    st.caption(f"Session `{st.session_state.session_id}`")

    st.divider()

    # Vault info
    vault_name = get_active_vault_name() or "None"
    st.markdown(f"**Vault** — {vault_name}")
    st.caption(f"`{get_active_vault_path() or '—'}`")

    if st.button("↗ Switch vault", use_container_width=True):
        st.session_state.vault_palette_open = True
        st.rerun()

    st.divider()

    # New conversation
    if st.button("＋ New conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())[:8]
        st.session_state.clear_composer_prompt = True
        st.rerun()

    # Audit log
    if st.button("⊞ Audit log", use_container_width=True):
        st.session_state.show_audit = not st.session_state.show_audit
        st.rerun()

    st.divider()

    st.caption("Pipeline status is available in the chat input bar.")


# ─────────────────────────────────────────────────────────────────────────────
# Audit page (overlay)
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.show_audit:
    st.markdown("### ⊞ Audit Log")
    st.caption("Complete history of file operations on this vault.")

    try:
        conn = sqlite3.connect(DB_PATH)
        df_audit = pd.read_sql_query(
            """
            SELECT timestamp, task_id, agent_role, filepath, status, before_sha256, after_sha256
            FROM file_edits ORDER BY timestamp DESC LIMIT 100
            """,
            conn,
        )
        conn.close()

        if not df_audit.empty:
            col_f, col_e = st.columns([3, 1])
            with col_f:
                opts = ["All"] + sorted(df_audit["status"].unique().tolist())
                sel = st.selectbox("Filter by status", opts, key="audit_filter", label_visibility="collapsed")
            with col_e:
                st.download_button(
                    "↓ Export CSV",
                    data=df_audit.to_csv(index=False).encode("utf-8"),
                    file_name="audit_log.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            if sel != "All":
                df_audit = df_audit[df_audit["status"] == sel]

            with st.container(border=True, height=480):
                for _, row in df_audit.iterrows():
                    try:
                        ts = datetime.fromisoformat(row["timestamp"]).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        ts = row["timestamp"]

                    status_class = row["status"]
                    st.markdown(
                        f'<div class="audit-row">'
                        f'<span class="ts">{ts}</span>'
                        f'<span class="agent">{row["agent_role"]}</span>'
                        f'<span class="file">{row["filepath"]}</span>'
                        f'<span class="audit-status {status_class}">{status_class}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No audit events yet. Run a task to start logging.")
    except Exception as exc:
        st.warning(f"Could not read audit log: {exc}")

    st.divider()
    if st.button("← Back to chat", use_container_width=True):
        st.session_state.show_audit = False
        st.rerun()
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Main chat interface
# ─────────────────────────────────────────────────────────────────────────────

mode_options = list(PERSONAS.keys())
model_capabilities = get_model_capabilities(st.session_state.active_model or "")
if mode_options and st.session_state.active_mode not in mode_options:
    st.session_state.active_mode = mode_options[0]

# ── Messages area — scrollable container ─────────────────────────────
chat_area = st.container(height=520, border=False)
st.session_state.chat_history_container = chat_area

with chat_area:
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="welcome-state">
              <div class="glyph">◈</div>
              <h2>What are we building?</h2>
              <p>Type a request below to start. Your agents will plan, build, review, and deliver.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    for msg in st.session_state.messages:
        with st.chat_message(msg.get("role", "assistant")):
            if "agent" in msg:
                render_agent_output(msg["agent"], msg["content"])
            else:
                st.markdown(msg["content"])


# ── Input bar ────────────────────────────────────────────────────────
with st.container(border=True):
    agent_placeholders = {}

    input_toolbar_left, input_toolbar_mid, input_toolbar_right = st.columns([0.18, 0.52, 0.30])

    with input_toolbar_left:
        with st.popover("Attach", use_container_width=True):
            st.markdown("#### Attach context")
            uploaded_files = st.file_uploader(
                "Upload PDF, MD or TXT",
                type=["pdf", "md", "txt"],
                accept_multiple_files=True,
                key="chat_file_uploader",
            )
            if uploaded_files:
                total_files = len(uploaded_files)
                current_signature = tuple(
                    (f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in uploaded_files
                )
                if current_signature != st.session_state.uploaded_files_signature:
                    extra_texts = []
                    progress_bar = st.progress(0, text="Processing files...")
                    for index, f in enumerate(uploaded_files, start=1):
                        progress_bar.progress(
                            int(((index - 1) / total_files) * 100),
                            text=f"Processing {index}/{total_files}: {f.name}",
                        )
                        txt = extract_text_from_file(f)
                        extra_texts.append(f"--- CONTENT OF {f.name} ---\n{txt}")
                    progress_bar.progress(100, text=f"Done: {total_files}/{total_files}")
                    st.session_state.extra_context_files = "\n\n".join(extra_texts)
                    st.session_state.uploaded_files_signature = current_signature
                st.success(f"{total_files} files ready.")
            else:
                st.session_state.extra_context_files = ""
                st.session_state.uploaded_files_signature = ()

            st.divider()
            pasted = st.text_area(
                "Paste from clipboard",
                placeholder="Paste extra context here...",
                key="chat_pasted_text",
                height=90,
            )
            st.session_state.extra_context_pasted = pasted

    with input_toolbar_mid:
        col_wf, col_md = st.columns([1, 1.2])
        with col_wf:
            selected_workflow = st.selectbox(
                "Workflow",
                options=["Plan", "Execute"],
                index=0 if st.session_state.active_workflow == "Plan" else 1,
                label_visibility="collapsed",
                key="workflow_selector",
            )
            if selected_workflow != st.session_state.active_workflow:
                st.session_state.active_workflow = selected_workflow
                # Notification if Execute without history
                if selected_workflow == "Execute" and not st.session_state.messages:
                    st.toast("⚠️ Careful: Executing without a prior plan may lead to undesired results.", icon="⚠️")
                st.rerun()

        with col_md:
            if mode_options:
                selected_mode = st.selectbox(
                    "Mode",
                    options=mode_options,
                    index=mode_options.index(st.session_state.active_mode),
                    label_visibility="collapsed",
                    key="mode_selector",
                )
                st.session_state.active_mode = selected_mode
            else:
                st.caption("No modes available")

    prompt = st.text_area(
        "Prompt",
        key="composer_prompt",
        placeholder="Describe what you need...",
        label_visibility="collapsed",
        height=88,
    )

    with input_toolbar_right:
        tasks_col, send_col = st.columns([1, 1.3])
        with tasks_col:
            with st.popover("Tasks", use_container_width=True):
                st.markdown("#### Agent pipeline")
                for agent in ["Manager", "Planner", "Researcher", "Builder", "Critic"]:
                    agent_placeholders[agent] = st.status(agent, state="complete")
        with send_col:
            submitted = st.button("Send", key="composer_send", use_container_width=True, type="primary")

    if model_capabilities.get("warning"):
        st.caption(f"Warning: {model_capabilities['warning']}")


# ── Handle submit ────────────────────────────────────────────────────
if submitted and prompt.strip():
    st.session_state.messages.append({"role": "user", "content": prompt.strip()})
    st.session_state.clear_composer_prompt = True
    st.rerun()

# ── Run orchestrator ─────────────────────────────────────────────────
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_prompt = st.session_state.messages[-1]["content"]
    callback = StreamlitCallback(agent_placeholders)
    orchestrator = Orchestrator(callback=callback)

    with chat_area:
        st.info("Agents are processing your request...")

    final_prompt = last_prompt
    context_parts = []
    if st.session_state.get("extra_context_files"):
        context_parts.append(st.session_state.extra_context_files)
    if st.session_state.get("extra_context_pasted"):
        context_parts.append(f"--- CLIPBOARD CONTENT ---\n{st.session_state.extra_context_pasted}")

    if context_parts:
        context_block = "\n\n=== USER-ATTACHED CONTEXT ===\n" + "\n\n".join(context_parts) + "\n=============================\n"
        final_prompt = f"{context_block}\n\nRequested task: {last_prompt}"

    try:
        orchestrator.process_task(
            st.session_state.session_id,
            final_prompt,
            mode=st.session_state.active_mode,
            workflow=st.session_state.active_workflow,
        )
        st.balloons()
        st.success("Task completed.")
        time.sleep(1)
        st.rerun()
    except Exception as exc:
        st.error(f"Critical failure: {exc}")
        with st.expander("Technical details", expanded=True):
            st.code(traceback.format_exc(), language="python")
