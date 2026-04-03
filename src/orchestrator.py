import json
import re
import os
import sqlite3
from colorama import Fore, Style
from .base_agent import AI_Agent
from .prompts import MANAGER_PROMPT, PLANNER_PROMPT, BUILDER_PROMPT, CRITIC_PROMPT, RESEARCHER_PROMPT
from .executor import write_file_tool, execute_command, write_obsidian_tool, create_vault_folder, patch_vault_file_tool
from .vault_manager import get_vault_tree, get_note_relationships, sync_vault

class Orchestrator:
    def __init__(self):
        self.manager = AI_Agent("Manager", MANAGER_PROMPT, require_json=True)
        self.planner = AI_Agent("Planner", PLANNER_PROMPT)
        self.researcher = AI_Agent("Researcher", RESEARCHER_PROMPT)
        self.builder = AI_Agent("Builder", BUILDER_PROMPT)
        self.critic = AI_Agent("Critic", CRITIC_PROMPT)

    def extract_and_save_code(self, builder_output: str):
        """Busca bloques de código que indican filepath y los guarda."""
        # Regex más robusto para capturar con o sin bloques de código estrictos
        pattern = r"(?:^|\n)#\s*filepath:\s*(.+?)\n(.*?)(?=\n#\s*filepath:|\n#\s*vault_file:|\n#\s*vault_folder:|$)"
        matches = re.finditer(pattern, builder_output, re.DOTALL)
        
        for match in matches:
            filepath = match.group(1).strip()
            code_content = match.group(2).strip()
            # Ya no hacemos re.sub agresivo para permitir bloques anidados
            
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Guardando archivo a través de Builder: {filepath}")
            res = write_file_tool(filepath, code_content)
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            
    def extract_and_save_vault_notes(self, builder_output: str):
        """Busca bloques de markdown que indican vault_file y los guarda en Obsidian."""
        # Regex robusto para Obsidian notes (permite bloques anidados)
        pattern = r"(?:^|\n)#\s*vault_file:\s*(.+?)\n(.*?)(?=\n#\s*vault_file:|\n#\s*vault_folder:|\n#\s*filepath:|$)"
        matches = re.finditer(pattern, builder_output, re.DOTALL)
        
        for match in matches:
            filepath = match.group(1).strip()
            content = match.group(2).strip()
            # Mantenemos el contenido tal cual se extrajo para no romper bloques internos (Mermaid, etc.)
            
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Guardando nota en Obsidian: {filepath}")
            res = write_obsidian_tool(filepath, content)
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            
    def extract_and_create_folders(self, builder_output: str):
        """Busca líneas que indican creación de carpetas."""
        pattern = r"(?:^|\n)#\s*vault_folder:\s*(.+?)(?:\n|$)"
        matches = re.finditer(pattern, builder_output)
        for match in matches:
            folder_path = match.group(1).strip()
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Creando carpeta en Obsidian: {folder_path}")
            res = create_vault_folder(folder_path)
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")

    def extract_and_apply_patches(self, builder_output: str, task_id: str):
        """Busca bloques diff que indican patch_vault_file y los aplica."""
        pattern = r"(?:^|\n)#\s*patch_vault_file:\s*(.+?)\n(.*?)(?=\n#\s*patch_vault_file:|\n#\s*vault_file:|\n#\s*filepath:|\n```|$)"
        matches = re.finditer(pattern, builder_output, re.DOTALL)
        
        for match in matches:
            filepath = match.group(1).strip()
            patch_text = match.group(2).strip()
            # Limpiar posibles cierres de bloque ``` sobrantes
            patch_text = re.sub(r"\n```$", "", patch_text).strip()
            
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Aplicando parche a: {filepath}")
            res = patch_vault_file_tool(filepath, patch_text, task_id, "Builder")
            print(f"{Fore.CYAN}[Sistema]{Style.RESET_ALL} Resultado: {res}")
            
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

    def process_task(self, task_id: str, prompt: str):
        print(f"\n{Fore.GREEN}[Usuario]{Style.RESET_ALL}: {prompt}\n")
        
        current_prompt = prompt
        
        while True:
            # 1. El Manager decide
            print(f"{Fore.MAGENTA}[Manager]{Style.RESET_ALL} procesando siguiente paso...")
            mgr_response = self.manager.execute(task_id, current_prompt)
            try:
                decision = json.loads(mgr_response)
                next_agent_name = decision.get("next_agent")
                instruction = decision.get("instruction")
            except Exception as e:
                print(f"[Error] Manager no regresó JSON válido. Abortando. {mgr_response}")
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
                    cursor = sqlite3.connect(os.path.join(os.path.dirname(__file__), '..', 'ai_team.db')).cursor()
                    cursor.execute("SELECT path FROM vault_nodes WHERE name LIKE ? AND type='file'", (f"%{note_name}%",))
                    row = cursor.fetchone()
                    if row:
                        relational_context = f"\n=== RELATIONS FOR '{row[0]}' ===\n{get_note_relationships(row[0])}"

                planner_prompt = f"{instruction}\n\n=== CURRENT VAULT STRUCTURE ===\n{vault_tree}{relational_context}"
                result = self.planner.execute(task_id, planner_prompt)
                print(f"{Fore.BLUE}[Planner]{Style.RESET_ALL}:\n{result}\n")
                current_prompt = f"Planner ended its work. Result: {result}. Manager, who should go next?"
                
            elif next_agent_name.lower() == "researcher":
                result = self.researcher.execute(task_id, instruction)
                print(f"{Fore.YELLOW}[Researcher]{Style.RESET_ALL}:\n{result}\n")
                current_prompt = f"Researcher ended its work. Finding: {result}. Manager, pass this to the next agent."
                
            elif next_agent_name.lower() == "builder":
                result = self.builder.execute(task_id, instruction)
                print(f"{Fore.CYAN}[Builder]{Style.RESET_ALL}:\n{result}\n")
                
                # Acciones automáticas basadas en el output del Builder
                self.extract_and_save_code(result)
                self.extract_and_save_vault_notes(result)
                self.extract_and_create_folders(result)
                self.extract_and_apply_patches(result, task_id)
                cmd_results = self.extract_and_run_commands(result)
                
                builder_feedback = result
                if cmd_results:
                    builder_feedback += f"\n\nExecuted Commands Results:\n{cmd_results}"
                    
                current_prompt = f"Builder ended its work. Feedback: {builder_feedback}. Manager, should Critic review it?"
                
            elif next_agent_name.lower() == "critic":
                result = self.critic.execute(task_id, instruction)
                print(f"{Fore.RED}[Critic]{Style.RESET_ALL}:\n{result}\n")
                
                if "CRITIC_APPROVED" in result:
                    current_prompt = "Critic approved the work. Manager, please finalize."
                else:
                    current_prompt = f"Critic found issues: {result}. Manager, please send back to Builder to fix."
            else:
                print(f"Agente desconocido: {next_agent_name}")
                break
