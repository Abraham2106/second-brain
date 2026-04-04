import os
import sqlite3
from src.infrastructure.execution.executor import patch_vault_file_tool

def test_patch():
    # Mock task/agent
    task_id = "test_patch_001"
    agent_role = "Tester"
    filename = "Bases de Datos/redis.md"

    # Parche de prueba (insertar al final)
    patch = """--- Bases de Datos/redis.md
    +++ Bases de Datos/redis.md
    @@ -7,2 +7,4 @@
             Key3["Key: session:abc"] --> Value3("Value: {user_id: 1, expiry: 1h}")
         end
    +```
    +
    +### Auditoría: Este archivo ha sido procesado por el Patch System.
    """

    print(f"Probando parche en {filename}...")
    res = patch_vault_file_tool(filename, patch, task_id, agent_role)
    print(f"Resultado: {res}")

    # Verificar DB
    conn = sqlite3.connect("ai_team.db")
    cursor = conn.cursor()
    cursor.execute("SELECT filepath, status, before_sha256, after_sha256 FROM file_edits WHERE task_id=?", (task_id,))
    row = cursor.fetchone()
    if row:
        after_sha = row[3][:8] if row[3] else "None"
        print(f"Registro en DB: File={row[0]}, Status={row[1]}, Before={row[2][:8]}, After={after_sha}")
    else:
        print("Error: No se encontró registro en la base de datos.")
    conn.close()

if __name__ == "__main__":
    test_patch()
