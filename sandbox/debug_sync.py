import os
import sqlite3
from dotenv import load_dotenv
from src.infrastructure.obsidian.vault_manager import sync_vault
from src.infrastructure.persistence.db import DB_PATH

load_dotenv()

vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
if not vault_path:
    print("Error: OBSIDIAN_VAULT_PATH not set.")
    exit(1)

vault_path = vault_path.strip("'\"").strip()
test_file = os.path.join(vault_path, "debug_asset.py")

print(f"Creando archivo de prueba: {test_file}")
with open(test_file, 'w', encoding='utf-8') as f:
    f.write('print("debug asset")')

print(f"Sincronizando vault: {vault_path}")
sync_vault(vault_path)

print("Consultando DB...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT path, type, length(content) FROM vault_nodes WHERE path LIKE '%debug_asset.py'")
row = cursor.fetchone()
if row:
    print(f"CONSEGUIDO: Path={row[0]}, Type={row[1]}, Length={row[2]}")
else:
    print("ERROR: El archivo no fue encontrado en la base de datos tras la sincronización.")
conn.close()
