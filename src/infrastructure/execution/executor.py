import subprocess
import os
import re
import sqlite3
from pathlib import Path
from colorama import Fore, Style
from src.infrastructure.obsidian.vault_paths import get_vault_dir, resolve_file_path, resolve_folder_path

WORKSPACE_DIR = ".workspace"

def is_high_risk_command(command: str) -> bool:
    """Returns True when a command looks destructive or installation-heavy."""
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
    print(f"\n{Fore.RED}[SECURITY ALERT]{Style.RESET_ALL} The agent wants to run a high-risk command:")
    print(f"{Fore.YELLOW}{command}{Style.RESET_ALL}")
    choice = input("Allow execution? [y/N]: ")
    return choice.strip().lower() == 'y'

def execute_command(command: str) -> str:
    """Executes a shell command inside the workspace after a simple risk check."""
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
            output = "[Execution completed successfully with no text output]"
            
        return output
    except subprocess.TimeoutExpired:
        return "[Error: Command timed out]"
    except Exception as e:
        return f"[Unexpected error: {str(e)}]"

from src.infrastructure.obsidian.vault_manager import sync_node
from src.infrastructure.persistence.redis_manager import RedisManager
from src.infrastructure.persistence.db import DB_PATH
from src.infrastructure.obsidian.patcher import apply_unified_patch
import hashlib

redis_mgr = RedisManager()

def get_file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def _delete_indexed_node(cursor, rel_path: str) -> None:
    note_name = os.path.splitext(os.path.basename(rel_path))[0]
    cursor.execute("DELETE FROM vault_links WHERE source_path = ?", (rel_path,))
    cursor.execute("DELETE FROM vault_links WHERE target_name = ?", (note_name,))
    cursor.execute("DELETE FROM vault_tags WHERE node_path = ?", (rel_path,))
    cursor.execute("DELETE FROM vault_nodes WHERE path = ?", (rel_path,))

def patch_vault_file_tool(filename: str, patch_text: str, task_id: str, agent_role: str) -> str:
    """Aplica un parche quirúrgico coordinado por Redis y auditado en SQLite."""
    try:
        vault_dir = get_vault_dir()
    except ValueError:
        return "Error: OBSIDIAN_VAULT_PATH not set"
    resolved_filename, filepath = resolve_file_path(vault_dir, filename, ".md")
    filename = resolved_filename

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
            conn = sqlite3.connect(DB_PATH)
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
        conn = sqlite3.connect(DB_PATH)
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
    try:
        vault_dir = get_vault_dir()
    except ValueError:
        return "Error: OBSIDIAN_VAULT_PATH not set in .env"
    
    resolved_filename, filepath = resolve_file_path(vault_dir, filename, ".md")
        
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Sincronización en tiempo real con la DB
        rel_path = os.path.relpath(filepath, vault_dir).replace('\\', '/')
        conn = sqlite3.connect(DB_PATH)
        sync_node(vault_dir, rel_path, conn.cursor())
        conn.commit()
        conn.close()
        
        return f"Obsidian note '{resolved_filename}' saved and indexed successfully."
    except Exception as e:
        return f"Error saving Obsidian note: {str(e)}"

def write_vault_asset_tool(filename: str, content: str) -> str:
    """
    Guarda un archivo de texto arbitrario dentro del Vault de Obsidian (no solo .md).
    Ejemplos: .pl, .py, .json, etc.
    """
    try:
        vault_dir = get_vault_dir()
    except ValueError:
        return "Error: OBSIDIAN_VAULT_PATH not set in .env"

    resolved_filename, filepath_str = resolve_file_path(vault_dir, filename)
    filepath = Path(filepath_str)

    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return f"Vault asset '{resolved_filename}' saved successfully."
    except Exception as e:
        return f"Error saving vault asset: {str(e)}"

def create_vault_folder(folder_path: str) -> str:
    """Crea una carpeta dentro del Vault de Obsidian."""
    try:
        vault_dir = get_vault_dir()
    except ValueError:
        return "Error: OBSIDIAN_VAULT_PATH not set in .env"
    requested_folder_path = folder_path.replace('\\', '/').strip("/")
    resolved_folder_path, full_path = resolve_folder_path(vault_dir, requested_folder_path)
    
    try:
        os.makedirs(full_path, exist_ok=True)
        
        # Sincronizar carpeta con la DB
        conn = sqlite3.connect(DB_PATH)
        sync_node(vault_dir, resolved_folder_path, conn.cursor())
        conn.commit()
        conn.close()

        if requested_folder_path and resolved_folder_path != requested_folder_path and os.path.exists(full_path):
            return f"Folder '{requested_folder_path}' mapped to existing '{resolved_folder_path}' and indexed successfully."
        return f"Folder '{resolved_folder_path or requested_folder_path}' created and indexed successfully."
    except Exception as e:
        return f"Error creating folder: {str(e)}"

def delete_vault_file_tool(filename: str, task_id: str, agent_role: str) -> str:
    """Elimina un archivo del vault y limpia sus referencias indexadas."""
    try:
        vault_dir = get_vault_dir()
    except ValueError:
        return "Error: OBSIDIAN_VAULT_PATH not set in .env"

    rel_path, filepath = resolve_file_path(
        vault_dir,
        filename,
        ".md" if "." not in os.path.basename(filename.replace("\\", "/").lstrip("/")) else None
    )

    if not os.path.exists(filepath):
        return f"Error: File '{filename}' does not exist."
    if os.path.isdir(filepath):
        return f"Error: '{filename}' is a folder. Use a file path."

    lock_owner = f"{agent_role}:{task_id}"
    if not redis_mgr.acquire_lock(rel_path, lock_owner):
        return f"Error: File '{rel_path}' is locked by another process."

    try:
        before_sha = None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                before_sha = get_file_sha256(f.read())
        except Exception:
            before_sha = None

        os.remove(filepath)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO file_edits (task_id, agent_role, filepath, before_sha256, status, diff_text) VALUES (?,?,?,?,?,?)",
            (task_id, agent_role, rel_path, before_sha, 'deleted', 'DELETE')
        )
        _delete_indexed_node(cursor, rel_path)
        conn.commit()
        conn.close()

        redis_mgr.log_event({
            "task_id": task_id,
            "agent": agent_role,
            "filepath": rel_path,
            "status": "deleted",
            "before_sha": before_sha or "",
            "after_sha": ""
        })

        return f"Vault file '{rel_path}' deleted successfully."
    except Exception as e:
        return f"Error deleting vault file: {str(e)}"
    finally:
        redis_mgr.release_lock(rel_path, lock_owner)
