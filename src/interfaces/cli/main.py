import os
import sys
import uuid

from src.infrastructure.config.config import get_settings
from src.infrastructure.persistence.db import init_db
from src.infrastructure.config.logging_setup import get_task_logger, setup_logging
from src.application.orchestration.orchestrator import Orchestrator
from src.infrastructure.obsidian.vault_manager import sync_vault


def main() -> None:
    settings = get_settings()

    # Session ID used for DB history + log file name.
    task_id = str(uuid.uuid4())[:8]
    setup_logging(settings, task_id)
    log = get_task_logger(__name__, task_id)

    print("Starting AI Team Assistant (F2P)...")
    print(f"Session Task ID: {task_id}")
    log.info("Session started")

    init_db()

    # Optional: sync Obsidian vault into SQLite for context (tree, links, tags).
    if settings.obsidian_vault_path:
        vault_path = settings.obsidian_vault_path
        print(f"Syncing vault: {os.path.basename(vault_path)}...")
        log.info("Syncing Obsidian vault: %s", vault_path)
        sync_vault(vault_path)

    if len(sys.argv) > 1:
        initial_prompt = " ".join(sys.argv[1:])
    else:
        initial_prompt = input("Enter your task for the team: ")

    if not initial_prompt.strip():
        print("Empty task. Exiting.")
        log.warning("Empty task prompt. Exiting.")
        return

    orch = Orchestrator()
    orch.process_task(task_id, initial_prompt)


if __name__ == "__main__":
    main()
