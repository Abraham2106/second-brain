import json
import re
import os
import sqlite3
import logging
from typing import Optional, List
from colorama import Fore, Style
from .base_agent import AI_Agent
from .prompts import MANAGER_PROMPT, PLANNER_PROMPT, BUILDER_PROMPT, CRITIC_PROMPT, RESEARCHER_PROMPT
from .executor import (
    write_file_tool,
    execute_command,
    write_obsidian_tool,
    write_vault_asset_tool,
    create_vault_folder,
    patch_vault_file_tool,
)
from .vault_manager import get_vault_tree, get_note_relationships, sync_vault, sync_node
from .config import get_settings
from .db import DB_PATH
from .errors import AppError
from .builder_json import parse_builder_files_from_text
from .callbacks import BaseCallback

class Orchestrator:
    def __init__(self, callback: Optional[BaseCallback] = None):
        self.callback = callback or BaseCallback()
        self.manager = AI_Agent("Manager", MANAGER_PROMPT, require_json=True)
        self.planner = AI_Agent("Planner", PLANNER_PROMPT)
        self.researcher = AI_Agent("Researcher", RESEARCHER_PROMPT)
        self.builder = AI_Agent("Builder", BUILDER_PROMPT)
        self.critic = AI_Agent("Critic", CRITIC_PROMPT)

    def _sync_vault_node(self, filepath: str):
        """Helper para sincronizar un nodo específico con la DB tras guardarlo."""
        try:
            settings = get_settings()
            if not settings.obsidian_vault_path:
                return
            conn = sqlite3.connect(DB_PATH)
            sync_node(settings.obsidian_vault_path, filepath, conn.cursor())
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"{Fore.RED}[Error Sync]{Style.RESET_ALL} No se pudo sincronizar {filepath}: {e}")

    def extract_and_save_code(self, builder_output: str):
        """Busca bloques de código que indican filepath y los guarda."""
        # Regex más robusto para capturar con o sin bloques de código estrictos
        pattern = r"(?:^|\n)#\s*[fF]ilepath:\s*(.+?)\n(.*?)(?=\n#\s*(?:[fF]ilepath|[vV]ault|_|$))"
        matches = re.finditer(pattern, builder_output, re.DOTALL)
        
        for match in matches:
            filepath = match.group(1).strip()
            code_content = match.group(2).strip()
            # Ya no hacemos re.sub agresivo para permitir bloques anidados
            
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Guardando archivo a través de Builder: {filepath}")
            res = write_file_tool(filepath, code_content)
            self.callback.on_system_message(f"Archivo guardado: {filepath}")
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            
    def extract_and_save_vault_notes(self, builder_output: str) -> int:
        """Busca bloques de markdown que indican vault_file y los guarda en Obsidian."""
        # Regex robusto para Obsidian notes (soporta variantes de tag)
        pattern = r"(?:^|\n)#\s*[vV]ault[\s\-_]*[fF]ile:\s*(.+?)\n(.*?)(?=\n#\s*(?:[vV]ault|[fF]ilepath)|$)"
        matches = re.finditer(pattern, builder_output, re.DOTALL)
        count = 0

        for match in matches:
            filepath = match.group(1).strip()
            content = match.group(2).strip()
            # Mantenemos el contenido tal cual se extrajo para no romper bloques internos (Mermaid, etc.)
            
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Guardando nota en Obsidian: {filepath}")
            res = write_obsidian_tool(filepath, content)
            self._sync_vault_node(filepath)
            self.callback.on_system_message(f"Nota guardada y sincronizada: {filepath}")
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            count += 1

        return count

    def extract_and_save_vault_assets(self, builder_output: str) -> int:
        """Busca bloques que indican vault_asset y los guarda."""
        pattern = r"(?:^|\n)#\s*[vV]ault[\s\-_]*[aA]sset:\s*(.+?)\n(.*?)(?=\n#\s*(?:[vV]ault|[fF]ilepath)|$)"
        matches = re.finditer(pattern, builder_output, re.DOTALL)
        count = 0

        for match in matches:
            filepath = match.group(1).strip()
            content = match.group(2).strip()
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Guardando asset en Obsidian: {filepath}")
            res = write_vault_asset_tool(filepath, content)
            self._sync_vault_node(filepath)
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            count += 1

        return count

    def extract_and_save_vault_json_files(self, builder_output: str) -> int:
        """
        Fallback: some Builder outputs come as a JSON-ish block with:
          [{ "file_path": "...", "content": "..." }, ...]
        This extracts that list and saves each entry into the Obsidian vault.
        """
        files = parse_builder_files_from_text(builder_output)
        if not files:
            return 0

        count = 0
        for item in files:
            file_path = item["file_path"].strip().replace("\\", "/").lstrip("/")
            content = item["content"]

            # Basic safety: never allow path traversal or absolute paths.
            if ".." in file_path or re.match(r"^[A-Za-z]:", file_path) or file_path.startswith("/"):
                print(f"{Fore.RED}[Sistema]{Style.RESET_ALL} Rechazando ruta insegura: {file_path}")
                continue

            if file_path.lower().endswith(".md") or "." not in os.path.basename(file_path):
                print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Guardando nota (JSON): {file_path}")
                res = write_obsidian_tool(file_path, content)
                self._sync_vault_node(file_path)
                print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            else:
                print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Guardando asset (JSON): {file_path}")
                res = write_vault_asset_tool(file_path, content)
                self._sync_vault_node(file_path)
                print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            count += 1

        return count
            
    def extract_and_create_folders(self, builder_output: str) -> int:
        """Busca líneas que indican creación de carpetas."""
        pattern = r"(?:^|\n)#\s*vault_folder:\s*(.+?)(?:\n|$)"
        matches = re.finditer(pattern, builder_output)
        count = 0
        for match in matches:
            folder_path = match.group(1).strip()
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Creando carpeta en Obsidian: {folder_path}")
            res = create_vault_folder(folder_path)
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            count += 1
        return count

    def extract_and_apply_patches(self, builder_output: str, task_id: str) -> int:
        """Busca bloques diff que indican patch_vault_file y los aplica."""
        pattern = r"(?:^|\n)#\s*[pP]atch[\s\-_]*[vV]ault[\s\-_]*[fF]ile:\s*(.+?)\n(.*?)(?=\n#\s*(?:[vV]ault|[fF]ilepath)|$)"
        matches = re.finditer(pattern, builder_output, re.DOTALL)
        count = 0

        for match in matches:
            filepath = match.group(1).strip()
            patch_text = match.group(2).strip()
            # Limpiar posibles cierres de bloque ``` sobrantes
            patch_text = re.sub(r"\n```$", "", patch_text).strip()
            
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Aplicando parche a: {filepath}")
            res = patch_vault_file_tool(filepath, patch_text, task_id, "Builder")
            self._sync_vault_node(filepath)
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            count += 1

        return count
            
    def extract_and_run_commands(self, text: str) -> str:
        """Busca bloques bash y los intenta correr y devuelve la salida."""
        pattern = r"```(?:bash|sh|cmd|powershell)\n(.*?)```"
        matches = re.finditer(pattern, text, re.DOTALL)
        outputs = []
        for match in matches:
            cmd = match.group(1).strip()
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Encontrado comando para ejecutar.")
            stdout = execute_command(cmd)
            outputs.append(f"Result for `{cmd}`:\n{stdout}")
        return "\n".join(outputs) if outputs else ""

    def _expects_vault_writes(self, instruction: str) -> bool:
        s = (instruction or "").lower()
        keywords = [
            "obsidian",
            "vault",
            "vault_file",
            "vault_folder",
            "vault_asset",
            "patch_vault_file",
            "wikilink",
            "cloud/",
        ]
        return any(k in s for k in keywords)

    def _build_builder_reemit_instruction(self, original_instruction: str, previous_output: str) -> str:
        return (
            "Your previous response did NOT create any files in the Obsidian vault because it did not use the saving "
            "directives. Re-emit the SAME content using ONLY these directives:\n"
            "- # vault_folder: <path>\n"
            "- # vault_file: <path/note.md>\n"
            "- # vault_asset: <path/file.ext>\n\n"
            "Rules:\n"
            "- Do NOT output JSON.\n"
            "- Do NOT wrap wikilinks like [[Note]] in backticks.\n"
            "- Do NOT include any ```bash/cmd/powershell``` command blocks.\n"
            "- Keep the content identical; just change the packaging/format so the Orchestrator can save it.\n\n"
            f"Original Builder instruction:\n{original_instruction}\n\n"
            f"Previous output to reformat:\n{previous_output}"
        )

    def process_task(self, task_id: str, prompt: str):
        print(f"\n{Fore.GREEN}[Usuario]{Style.RESET_ALL}: {prompt}\n")
        
        log = logging.LoggerAdapter(logging.getLogger(__name__), {"task_id": task_id, "agent": "Orchestrator"})
        log.info("Task loop started")

        current_prompt = prompt
        
        while True:
            # 1. El Manager decide
            self.callback.on_agent_start("Manager", f"Decidiendo siguiente paso para: {current_prompt[:50]}...")
            print(f"{Fore.MAGENTA}[Manager]{Style.RESET_ALL} procesando siguiente paso...")
            try:
                mgr_response = self.manager.execute(task_id, current_prompt)
            except AppError as e:
                log.error("Manager execution failed: %s", e)
                self.callback.on_agent_end("Manager", f"Error: {e}")
                print(f"[Error] {e}")
                break
            except Exception as e:
                log.exception("Unexpected error calling Manager: %s", e)
                self.callback.on_agent_end("Manager", f"Error: {e}")
                print(f"[Error] Unexpected error calling Manager: {e}")
                break
            
            self.callback.on_agent_end("Manager", mgr_response)
            try:
                decision = json.loads(mgr_response)
                next_agent_name = decision.get("next_agent")
                instruction = decision.get("instruction")
            except Exception as e:
                print(f"[Error] Manager no regresó JSON válido. Abortando. {mgr_response}")
                log.error("Manager returned invalid JSON: %s", mgr_response)
                break
                
            print(f"{Fore.MAGENTA}[Manager]{Style.RESET_ALL} llama a {Fore.YELLOW}{next_agent_name}{Style.RESET_ALL}: {instruction}\n")
            
            if next_agent_name.lower() == "user":
                print(f"\n{Fore.GREEN}[Fin de la tarea]{Style.RESET_ALL} {instruction}")
                break
                
            # 2. Llamada dinámica a los agentes
            if next_agent_name.lower() == "planner":
                vault_tree = get_vault_tree()
                
                # Intentar detectar si el usuario está hablando de una nota específica para dar contexto relacional
                relational_context = ""
                potential_note = re.search(r"nota ['\"]?([^'\"]+)['\"]?", prompt)
                if potential_note:
                    note_name = potential_note.group(1)
                    # Buscar la ruta real en el árbol
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT path FROM vault_nodes WHERE name LIKE ? AND type='file'",
                        (f"%{note_name}%",),
                    )
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        relational_context = f"\n=== RELATIONS FOR '{row[0]}' ===\n{get_note_relationships(row[0])}"

                planner_prompt = f"{instruction}\n\n=== CURRENT VAULT STRUCTURE ===\n{vault_tree}{relational_context}"
                self.callback.on_agent_start("Planner", instruction)
                try:
                    result = self.planner.execute(task_id, planner_prompt)
                except AppError as e:
                    self.callback.on_agent_end("Planner", f"Error: {e}")
                    log.error("Planner execution failed: %s", e)
                    print(f"[Error] {e}")
                    break
                except Exception as e:
                    self.callback.on_agent_end("Planner", f"Error: {e}")
                    log.exception("Unexpected error calling Planner: %s", e)
                    print(f"[Error] Unexpected error calling Planner: {e}")
                    break
                self.callback.on_agent_end("Planner", result)
                print(f"{Fore.BLUE}[Planner]{Style.RESET_ALL}:\n{result}\n")
                current_prompt = f"Planner ended its work. Result: {result}. Manager, who should go next?"
                
            elif next_agent_name.lower() == "researcher":
                self.callback.on_agent_start("Researcher", instruction)
                try:
                    result = self.researcher.execute(task_id, instruction)
                except AppError as e:
                    self.callback.on_agent_end("Researcher", f"Error: {e}")
                    log.error("Researcher execution failed: %s", e)
                    print(f"[Error] {e}")
                    break
                except Exception as e:
                    self.callback.on_agent_end("Researcher", f"Error: {e}")
                    log.exception("Unexpected error calling Researcher: %s", e)
                    print(f"[Error] Unexpected error calling Researcher: {e}")
                    break
                self.callback.on_agent_end("Researcher", result)
                print(f"{Fore.YELLOW}[Researcher]{Style.RESET_ALL}:\n{result}\n")
                current_prompt = f"Researcher ended its work. Finding: {result}. Manager, pass this to the next agent."
                
            elif next_agent_name.lower() == "builder":
                self.callback.on_agent_start("Builder", instruction)
                try:
                    result = self.builder.execute(task_id, instruction)
                except AppError as e:
                    self.callback.on_agent_end("Builder", f"Error: {e}")
                    log.error("Builder execution failed: %s", e)
                    print(f"[Error] {e}")
                    break
                except Exception as e:
                    self.callback.on_agent_end("Builder", f"Error: {e}")
                    log.exception("Unexpected error calling Builder: %s", e)
                    print(f"[Error] Unexpected error calling Builder: {e}")
                    break
                self.callback.on_agent_end("Builder", result)
                print(f"{Fore.CYAN}[Builder]{Style.RESET_ALL}:\n{result}\n")
                
                # Acciones automáticas basadas en el output del Builder
                self.extract_and_save_code(result)
                vault_writes = 0
                vault_writes += self.extract_and_save_vault_notes(result)
                vault_writes += self.extract_and_save_vault_assets(result)
                vault_writes += self.extract_and_create_folders(result)
                vault_writes += self.extract_and_apply_patches(result, task_id)
                # Fallback: if Builder returns JSON-ish files, save them too.
                vault_writes += self.extract_and_save_vault_json_files(result)

                # Avoid "false success": if we expected vault output but saved nothing, force a single re-emit.
                if vault_writes == 0 and self._expects_vault_writes(instruction):
                    log.warning("Builder produced no vault writes. Forcing a re-emit in save-directive format.")
                    print(
                        f"{Fore.YELLOW}[Sistema]{Style.RESET_ALL} Builder no guardo nada en el vault. "
                        "Solicitando re-emision en formato # vault_file...\n"
                    )
                    reemit_instruction = self._build_builder_reemit_instruction(instruction, result)
                    try:
                        reformatted = self.builder.execute(task_id, reemit_instruction)
                    except AppError as e:
                        log.error("Builder re-emit failed: %s", e)
                        reformatted = ""
                    except Exception as e:
                        log.exception("Unexpected error calling Builder re-emit: %s", e)
                        reformatted = ""
                    if reformatted:
                        print(f"{Fore.CYAN}[Builder]{Style.RESET_ALL} (re-emit):\n{reformatted}\n")
                        # Apply side-effects from reformatted output.
                        vault_writes = 0
                        self.extract_and_save_code(reformatted)
                        vault_writes += self.extract_and_save_vault_notes(reformatted)
                        vault_writes += self.extract_and_save_vault_assets(reformatted)
                        vault_writes += self.extract_and_create_folders(reformatted)
                        vault_writes += self.extract_and_apply_patches(reformatted, task_id)
                        vault_writes += self.extract_and_save_vault_json_files(reformatted)
                        if vault_writes > 0:
                            result = reformatted
                cmd_results = self.extract_and_run_commands(result)
                
                builder_feedback = result
                if cmd_results:
                    builder_feedback += f"\n\nExecuted Commands Results:\n{cmd_results}"
                    
                current_prompt = f"Builder ended its work. Feedback: {builder_feedback}. Manager, should Critic review it?"
                
            elif next_agent_name.lower() == "critic":
                self.callback.on_agent_start("Critic", instruction)
                try:
                    result = self.critic.execute(task_id, instruction)
                except AppError as e:
                    self.callback.on_agent_end("Critic", f"Error: {e}")
                    log.error("Critic execution failed: %s", e)
                    print(f"[Error] {e}")
                    break
                except Exception as e:
                    self.callback.on_agent_end("Critic", f"Error: {e}")
                    log.exception("Unexpected error calling Critic: %s", e)
                    print(f"[Error] Unexpected error calling Critic: {e}")
                    break
                self.callback.on_agent_end("Critic", result)
                print(f"{Fore.RED}[Critic]{Style.RESET_ALL}:\n{result}\n")
                
                if "CRITIC_APPROVED" in result:
                    current_prompt = "Critic approved the work. Manager, please finalize."
                else:
                    current_prompt = f"Critic found issues: {result}. Manager, please send back to Builder to fix."
            else:
                print(f"Agente desconocido: {next_agent_name}")
                break
