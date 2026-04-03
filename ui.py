import streamlit as st
import pandas as pd
import sqlite3
import os
import uuid
import time
import hashlib
from datetime import datetime
from src.orchestrator import Orchestrator
from src.callbacks import BaseCallback
from src.db import DB_PATH
from src.config import get_settings
from src.vault_manager import sync_vault

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="AI Team Assistant - Elite OS",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILOS CUSTOM (MODO INDUSTRIAL) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
code, pre, .stMetric [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
}
.stApp { background-color: #0A0A0A; }
section[data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #262626; }
.stChatMessage { background-color: #141414; border: 1px solid #262626; border-radius: 8px; margin-bottom: 12px; }

/* Tree view styling */
.stButton > button {
    width: 100%;
    text-align: left;
    background-color: transparent !important;
    border: none !important;
    color: #AAA !important;
    padding: 2px 10px !important;
    font-size: 14px !important;
}
.stButton > button:hover {
    color: #6B9EFF !important;
    background-color: #1A1A1A !important;
}

div[data-testid="stStatus"] {
    background-color: #1A1A1A;
    border: 1px solid #262626;
}
</style>
""", unsafe_allow_html=True)

# --- CALLBACK PARA STREAMLIT (TRANSPARENCIA) ---
class StreamlitCallback(BaseCallback):
    def __init__(self, agent_status_placeholders):
        self.placeholders = agent_status_placeholders
        self.agent_icons = {
            "Manager": "🧠", "Planner": "📐", "Researcher": "🔍", "Builder": "🔨", "Critic": "⚖️"
        }
        
    def on_agent_start(self, agent_name: str, instruction: str):
        if agent_name in self.placeholders:
            self.placeholders[agent_name].update(label=f"● {agent_name}: Procesando...", state="running")
            with st.session_state.chat_history_container:
                with st.chat_message("assistant", avatar=self.agent_icons.get(agent_name, "🤖")):
                    st.caption(f"**{agent_name}** recibió instrucción:")
                    st.info(instruction)

    def on_agent_end(self, agent_name: str, result: str):
        if agent_name in self.placeholders:
            self.placeholders[agent_name].update(label=f"● {agent_name}: Finalizado", state="complete")
            with st.session_state.chat_history_container:
                with st.chat_message("assistant", avatar=self.agent_icons.get(agent_name, "🤖")):
                    with st.expander(f"📄 Resultado final de {agent_name}", expanded=False):
                        st.markdown(result)
            st.session_state.messages.append({
                "role": "assistant", "agent": agent_name, "content": result, "avatar": self.agent_icons.get(agent_name, "🤖")
            })
            
    def on_system_message(self, message: str, mtype: str = "info"):
        st.toast(message, icon="ℹ️")

# --- INICIALIZAR ESTADO ---
if "messages" not in st.session_state: st.session_state.messages = []
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())[:8]
if "selected_note" not in st.session_state: st.session_state.selected_note = None

# --- SIDEBAR: Navigation & Agent Nucleus ---
with st.sidebar:
    st.title("🧠 Elite Assistant")
    st.caption(f"Cluster: {st.session_state.session_id}")
    st.divider()
    
    # NAVEGACION PRINCIPAL
    main_mode = st.radio("Módulos", ["🚀 Solicitar", "🌳 Visualizar"], index=0)
    
    st.divider()
    if st.button("🔄 Sincronizar Vault", use_container_width=True):
        settings = get_settings()
        if settings.obsidian_vault_path:
            with st.spinner("Escaneando archivos y reconstruyendo grafo..."):
                # Limpiar DB para forzar sync fresco si el usuario le da al botón
                try:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("DELETE FROM vault_nodes")
                    conn.commit()
                    conn.close()
                except: pass
                
                sync_vault(settings.obsidian_vault_path)
                st.success("¡Vault sincronizado con éxito!")
                time.sleep(1)
                st.rerun()
        else:
            st.error("No se encontró la ruta del vault en .env")

    st.divider()
    st.subheader("Estado de Nodos")
    agent_placeholders = {}
    for agent in ["Manager", "Planner", "Researcher", "Builder", "Critic"]:
        agent_placeholders[agent] = st.status(f"{agent}", state="complete")
        with agent_placeholders[agent]:
            st.caption("Esperando...")

# --- DATA HELPERS ---
def get_note_content(rel_path):
    try:
        settings = get_settings()
        full_path = os.path.join(settings.obsidian_vault_path, rel_path)
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
    except: return None
    return None

def render_vault_tree(df_all, parent_path=""):
    try:
        # Filtramos para que solo sean hijos directos
        def is_direct_child(path, parent):
            if not parent:
                return "/" not in path
            if not path.startswith(parent + "/"):
                return False
            sub = path[len(parent)+1:]
            return "/" not in sub and len(sub) > 0

        # Carpetas en este nivel
        direct_folders = df_all[(df_all['type'] == 'folder') & (df_all['path'].apply(lambda x: is_direct_child(x, parent_path)))]
        # Archivos en este nivel
        direct_files = df_all[(df_all['type'] == 'file') & (df_all['path'].apply(lambda x: is_direct_child(x, parent_path)))]

        for _, row in direct_folders.sort_values('name').iterrows():
            with st.expander(f"📁 {row['name']}", expanded=False):
                render_vault_tree(df_all, row['path'])
        
        for _, row in direct_files.sort_values('name').iterrows():
            if st.button(f"📝 {row['name']}", key=f"btn_{row['path']}", use_container_width=True):
                st.session_state.selected_note = row['path']
                st.rerun()
    except Exception as e:
        st.error(f"Error renderizando árbol: {e}")

# --- DATA HELPERS (CACHED) ---
def get_vault_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT name, path, type FROM vault_nodes", conn)
        conn.close()
        if not df.empty:
            df['path'] = df['path'].str.replace('\\', '/')
        return df
    except:
        return pd.DataFrame()

def render_audit_log():
    st.subheader("📋 Registro de Auditoría Crítica")
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("""
            SELECT timestamp, filepath, agent, change_type, status 
            FROM file_edits ORDER BY timestamp DESC LIMIT 15
        """, conn)
        conn.close()
        
        if not df.empty:
            # Formatear narrativa
            audit_events = []
            for _, row in df.iterrows():
                hora = datetime.fromisoformat(row['timestamp']).strftime('%H:%M:%S')
                icon = "📝" if row['change_type'] == 'create' else "🩹"
                evento = f"[{hora}] {icon} Agente {row['agent']} realizó {row['change_type']} en {row['filepath']} ({row['status']})"
                audit_events.append(evento)
            
            with st.container(border=True, height=300):
                for ev in audit_events:
                    st.caption(ev)
        else:
            st.info("Sin eventos recientes.")
    except: st.info("Sincroniza el vault para ver logs.")

# --- MODO 1: SOLICITAR (CHAT + LOGS) ---
if main_mode == "🚀 Solicitar":
    st.subheader("💬 Active Operations Center")
    
    # CHAT AREA
    chat_container = st.container(height=500)
    st.session_state.chat_history_container = chat_container
    with chat_container:
        for msg in st.session_state.messages:
            avatar = msg.get("avatar") if msg["role"] == "assistant" else "👤"
            with st.chat_message(msg["role"], avatar=avatar):
                if "agent" in msg: st.caption(f"**Agent {msg['agent']}**:")
                st.markdown(msg["content"])
    
    # AUDIT LOG (PIE DE PAGINA)
    st.divider()
    render_audit_log()

    # INPUT USUARIO
    if prompt := st.chat_input("¿Qué tarea quieres ejecutar?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()

    # LOGICA DE EXEC
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
            last_prompt = st.session_state.messages[-1]["content"]
            callback = StreamlitCallback(agent_placeholders)
            orchestrator = Orchestrator(callback=callback)
            
            st.info("⏳ Tarea en curso. Los agentes están procesando...")
            try:
                orchestrator.process_task(st.session_state.session_id, last_prompt)
                st.balloons()
                st.success("✅ Operación completada.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Falla crítica: {e}")

# --- MODO 2: VISUALIZAR (TREE + VIEWER) ---
else:
    st.subheader("🌳 Vault Explorer")
    col_tree, col_viewer = st.columns([1, 2])
    
    with col_tree:
        st.markdown("##### Estructura del Vault")
        df_vault = get_vault_data()
        with st.container(border=True, height=600):
            if not df_vault.empty:
                render_vault_tree(df_vault)
            else:
                st.info("El vault está vacío. Haz clic en 'Sincronizar' en el sidebar.")
            
    with col_viewer:
        st.markdown(f"##### Lector: `{st.session_state.selected_note or 'Ninguna nota seleccionada'}`")
        with st.container(border=True, height=600):
            if st.session_state.selected_note:
                content = get_note_content(st.session_state.selected_note)
                if content:
                    tab_view, tab_raw = st.tabs(["✨ Rendered", "📄 Source"])
                    with tab_view: st.markdown(content)
                    with tab_raw: st.code(content, language="markdown")
                else:
                    st.warning("No se pudo leer el archivo.")
            else:
                st.info("Utiliza el explorador de la izquierda para seleccionar una nota.")
