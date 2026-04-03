import os
import uuid
import sys
from dotenv import load_dotenv
from src.db import init_db
from src.orchestrator import Orchestrator
from src.vault_manager import sync_vault

def main():
    print("Iniciando AI Team Assistant (F2P)...")
    init_db()
    
    # Sincronización automática de Obsidian
    load_dotenv()
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if vault_path:
        print(f"📦 Sincronizando Vault: {os.path.basename(vault_path)}...")
        sync_vault(vault_path)
    
    # Generar un random UUID para esta sesión (o permitir volver a una existente)
    task_id = str(uuid.uuid4())[:8]
    print(f"Session Task ID: {task_id}")
    
    if len(sys.argv) > 1:
        initial_prompt = " ".join(sys.argv[1:])
    else:
        initial_prompt = input("Ingresa tu tarea para el equipo: ")
        
    if not initial_prompt.strip():
        print("Tarea vacía. Saliendo.")
        return

    orch = Orchestrator()
    orch.process_task(task_id, initial_prompt)

if __name__ == "__main__":
    main()
