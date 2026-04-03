import os
import sys
import uuid

from src.config import get_settings
from src.db import init_db
from src.logging_setup import get_task_logger, setup_logging
from src.orchestrator import Orchestrator
from src.vault_manager import sync_vault


def main() -> None:
    settings = get_settings()

    # Session ID used for DB history + log file name.
    task_id = str(uuid.uuid4())[:8]
    setup_logging(settings, task_id)
    log = get_task_logger(__name__, task_id)

    print("Iniciando AI Team Assistant (F2P)...")
    print(f"Session Task ID: {task_id}")
    log.info("Session started")

    init_db()

    # Optional: sync Obsidian vault into SQLite for context (tree, links, tags).
    if settings.obsidian_vault_path:
        vault_path = settings.obsidian_vault_path
        print(f"Sincronizando Vault: {os.path.basename(vault_path)}...")
        log.info("Syncing Obsidian vault: %s", vault_path)
        sync_vault(vault_path)

    if len(sys.argv) > 1:
        initial_prompt = " ".join(sys.argv[1:])
    else:
        initial_prompt = input("Ingresa tu tarea para el equipo: ")

    if not initial_prompt.strip():
        print("Tarea vacia. Saliendo.")
        log.warning("Empty task prompt. Exiting.")
        return

    orch = Orchestrator()
    orch.process_task(task_id, initial_prompt)


if __name__ == "__main__":
    main()

