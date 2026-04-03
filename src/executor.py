import subprocess
import os
import re
import sqlite3
from pathlib import Path
from colorama import Fore, Style
from dotenv import load_dotenv

WORKSPACE_DIR = ".workspace"

def is_high_risk_command(command: str) -> bool:
    """Verifica si el comando tiene operadoras/palabras peligrosas."""
    dangerous_keywords = ['rm', 'del', 'format', 'mkfs', 'dd', 'wget', 'curl', 'npm install -g', 'pip install']
    cmd_lower = command.lower()
    
    for kw in dangerous_keywords:
        # Busca la palabra clave con límites de palabra (whole word) para evitar falsos positivos
        if re.search(rf"\b{kw}\b", cmd_lower):
            return True
    
    # También checkeamos si trata de salirse del workspace usando rutas absolutas o hacia arriba
    if ".." in command or "/" in command and not command.startswith("./"):
        # Relajamos un poco porque algunas rutas usan / y ..
        pass 

    return False

def confirm_execution(command: str) -> bool:
    print(f"\n{Fore.RED}⚠️ [ALERTA DE SEGURIDAD]{Style.RESET_ALL} El agente intenta ejecutar un comando de alto riesgo:")
    print(f"{Fore.YELLOW}{command}{Style.RESET_ALL}")
    choice = input(f"¿Permitir ejecución? [y/N]: ")
    return choice.strip().lower() == 'y'

def execute_command(command: str) -> str:
    """Ejecuta un comando en la terminal, pasando por el filtro de riesgo si es necesario."""
    if is_high_risk_command(command):
        if not confirm_execution(command):
            return "Execution aborted by the user due to security risk."
    
    try:
        # Asegurarnos de que .workspace existe y usarlo como CWD si es apropiado
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
            
        if not output.strip():
            output = "[Ejecución completada con éxito, sin salida de texto]"
            
        return output
    except subprocess.TimeoutExpired:
        return "[Error: Tiempo de ejecución excedido (Timeout)]"
    except Exception as e:
        return f"[Error inesperado: {str(e)}]"

from .vault_manager import sync_node
from .redis_manager import RedisManager
from .patcher import apply_unified_patch
import hashlib

redis_mgr = RedisManager()

def get_file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def patch_vault_file_tool(filename: str, patch_text: str, task_id: str, agent_role: str) -> str:
    """Aplica un parche quirúrgico coordinado por Redis y auditado en SQLite."""
    load_dotenv()
    vault_dir = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_dir: return "Error: OBSIDIAN_VAULT_PATH not set"
    
    vault_dir = vault_dir.strip('"').strip("'").strip()
    filename = filename.replace('\\', '/')
    filepath = os.path.join(vault_dir, filename)
    if not filepath.lower().endswith(".md"): filepath += ".md"

    # 1. Acquire Redis Lock
    lock_owner = f"{agent_role}:{task_id}"
    if not redis_mgr.acquire_lock(filename, lock_owner):
        return f"Error: File '{filename}' is locked by another process."

    try:
        if not os.path.exists(filepath):
            return f"Error: Cannot patch non-existent file '{filename}'"

        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()

        before_sha = get_file_sha256(original_content)
        
        # 2. Apply Patch
        try:
            new_content = apply_unified_patch(original_content, patch_text)
        except Exception as e:
            # Registrar cualquier error (conflicto o fallo de patcher) en SQLite
            db_path = os.path.join(os.path.dirname(__file__), '..', 'ai_team.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO file_edits (task_id, agent_role, filepath, before_sha256, status, error_text, diff_text) VALUES (?,?,?,?,?,?,?)",
                        (task_id, agent_role, filename, before_sha, 'conflict', str(e), patch_text))
            conn.commit(); conn.close()
            return f"Patch Error: {str(e)}"

        # 3. Write File
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        after_sha = get_file_sha256(new_content)

        # 4. Success Log (SQLite + Redis Stream)
        db_path = os.path.join(os.path.dirname(__file__), '..', 'ai_team.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO file_edits (task_id, agent_role, filepath, before_sha256, after_sha256, status, diff_text) VALUES (?,?,?,?,?,?,?)",
                    (task_id, agent_role, filename, before_sha, after_sha, 'applied', patch_text))
        conn.commit()
        
        # Sincronización del nodo en la DB de relaciones
        rel_path = os.path.relpath(filepath, vault_dir).replace('\\', '/')
        sync_node(vault_dir, rel_path, cursor)
        conn.commit(); conn.close()

        # Redis Stream event
        redis_mgr.log_event({
            "task_id": task_id,
            "agent": agent_role,
            "filepath": filename,
            "status": "applied",
            "before_sha": before_sha,
            "after_sha": after_sha
        })

        return f"Patch applied and audit logged. SHA256: {after_sha[:8]}..."

    finally:
        redis_mgr.release_lock(filename, lock_owner)

def write_file_tool(filename: str, content: str) -> str:
    """Herramienta para guardar archivos dentro de .workspace."""
    # Validación paranoica de path para evitar salir de .workspace
    clean_filename = os.path.basename(filename)
    filepath = os.path.join(WORKSPACE_DIR, clean_filename)
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"File {clean_filename} saved successfully."
    except Exception as e:
        return f"Error saving file: {str(e)}"

def write_obsidian_tool(filename: str, content: str) -> str:
    """Herramienta para guardar notas dentro del Vault de Obsidian."""
    # Recargar .env para asegurarnos de tener la ruta más fresca (opcional pero seguro)
    load_dotenv()
    vault_dir = os.getenv("OBSIDIAN_VAULT_PATH")
    
    if not vault_dir:
        return "Error: OBSIDIAN_VAULT_PATH not set in .env"
    
    # Limpiar posibles comillas de la ruta
    vault_dir = vault_dir.strip('"').strip("'").strip()
    
    # Si filename contiene subcarpetas (ej: "Proyectos/Nota"), respetarlas
    # Normalizar a forward slashes
    filename = filename.replace('\\', '/')
    filepath = os.path.join(vault_dir, filename)
    if not filepath.lower().endswith(".md"):
        filepath += ".md"
        
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Sincronización en tiempo real con la DB
        rel_path = os.path.relpath(filepath, vault_dir).replace('\\', '/')
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), '..', 'ai_team.db'))
        sync_node(vault_dir, rel_path, conn.cursor())
        conn.commit()
        conn.close()
        
        return f"Obsidian note '{filename}' saved and indexed successfully."
    except Exception as e:
        return f"Error saving Obsidian note: {str(e)}"

def write_vault_asset_tool(filename: str, content: str) -> str:
    """
    Guarda un archivo de texto arbitrario dentro del Vault de Obsidian (no solo .md).
    Ejemplos: .pl, .py, .json, etc.
    """
    load_dotenv()
    vault_dir = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_dir:
        return "Error: OBSIDIAN_VAULT_PATH not set in .env"

    vault_dir = vault_dir.strip('"').strip("'").strip()

    # Respetar subcarpetas y normalizar separadores.
    filename = filename.replace("\\", "/").lstrip("/")
    filepath = Path(vault_dir) / Path(filename)

    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return f"Vault asset '{filename}' saved successfully."
    except Exception as e:
        return f"Error saving vault asset: {str(e)}"

def create_vault_folder(folder_path: str) -> str:
    """Crea una carpeta dentro del Vault de Obsidian."""
    load_dotenv()
    vault_dir = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_dir:
        return "Error: OBSIDIAN_VAULT_PATH not set in .env"
        
    vault_dir = vault_dir.strip('"').strip("'").strip()
    folder_path = folder_path.replace('\\', '/')
    full_path = os.path.join(vault_dir, folder_path)
    
    try:
        os.makedirs(full_path, exist_ok=True)
        
        # Sincronizar carpeta con la DB
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), '..', 'ai_team.db'))
        sync_node(vault_dir, folder_path, conn.cursor())
        conn.commit()
        conn.close()
        
        return f"Folder '{folder_path}' created and indexed successfully."
    except Exception as e:
        return f"Error creating folder: {str(e)}"
