import sqlite3
from typing import Optional

from src.builder_json import parse_builder_files_from_text
from src.executor import write_obsidian_tool, write_vault_asset_tool


def _get_latest_builder_message(task_id: str) -> Optional[str]:
    conn = sqlite3.connect("ai_team.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT content FROM messages WHERE task_id=? AND agent_role=? ORDER BY timestamp DESC LIMIT 1",
        (task_id, "Builder"),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def main() -> None:
    task_id = "9bd61c80"
    text = _get_latest_builder_message(task_id)
    if not text:
        print(f"No Builder message found for task_id={task_id}")
        return

    files = parse_builder_files_from_text(text)
    if not files:
        print("No JSON-ish files found in Builder message.")
        return

    saved = 0
    for item in files:
        path = item["file_path"].strip().replace("\\", "/").lstrip("/")
        content = item["content"]

        if path.lower().endswith(".md") or "." not in path.split("/")[-1]:
            res = write_obsidian_tool(path, content)
        else:
            res = write_vault_asset_tool(path, content)
        saved += 1
        print(res)

    print(f"Saved {saved} files from task_id={task_id}")


if __name__ == "__main__":
    main()

