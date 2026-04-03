import os
from dotenv import load_dotenv
from src.executor import write_obsidian_tool

load_dotenv()

content = "# Test Note\nThis is a test note for Obsidian."
filename = "Test Note 123"

print("Trying to write to vault...")
res = write_obsidian_tool(filename, content)
print(f"Result: {res}")

vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
# Tratar como en el script
if vault_path:
    vault_path = vault_path.strip('"').strip("'").strip()
    full_path = os.path.join(vault_path, filename + ".md")
    print(f"Checking path: {full_path}")
    if os.path.exists(full_path):
        print("✅ SUCCESS: File exists!")
    else:
        print("❌ FAILURE: File does not exist.")
else:
    print("❌ FAILURE: Vault path not found in .env")
