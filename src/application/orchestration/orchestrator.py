import json
import re
import os
import sqlite3
import logging
import unicodedata
from typing import Optional, List
from colorama import Fore, Style
from src.core.agent_protocols import AI_Agent
from src.prompts.prompts import MANAGER_PROMPT, PLANNER_PROMPT, BUILDER_PROMPT, CRITIC_PROMPT, RESEARCHER_PROMPT, SUMMARIZER_PROMPT
from src.infrastructure.execution.executor import (
    write_file_tool,
    execute_command,
    write_obsidian_tool,
    write_vault_asset_tool,
    create_vault_folder,
    patch_vault_file_tool,
    delete_vault_file_tool,
)
from src.infrastructure.obsidian.vault_manager import get_vault_tree, get_note_relationships, sync_vault, sync_node
from src.infrastructure.config.config import get_settings
from src.infrastructure.persistence.db import DB_PATH
from src.core.errors import AppError
from src.infrastructure.llm.builder_json import parse_builder_files_from_text
from src.core.callbacks import BaseCallback
from src.application.language.language import (
    build_manager_language_policy,
    detect_user_language,
    extract_original_user_request,
    with_language_context,
)
from src.prompts.personas import PERSONAS

class Orchestrator:
    def __init__(self, callback: Optional[BaseCallback] = None):
        self.callback = callback or BaseCallback()
        self.manager = AI_Agent("Manager", MANAGER_PROMPT, require_json=True)
        self.planner = AI_Agent("Planner", PLANNER_PROMPT)
        self.researcher = AI_Agent("Researcher", RESEARCHER_PROMPT)
        self.builder = AI_Agent("Builder", BUILDER_PROMPT)
        self.critic = AI_Agent("Critic", CRITIC_PROMPT)
        self.summarizer = AI_Agent("Summarizer", SUMMARIZER_PROMPT)
        self.history = []

    def _extract_plan_of_record(self, task_id: str) -> str:
        """Find the last proposal from the Planner in the history."""
        from src.infrastructure.persistence.db import get_history
        raw = get_history(task_id)
        # Search backwards for the latest Planner output
        for msg in reversed(raw):
            if msg["agent_name"].lower() == "planner":
                return f"\n=== PLAN OF RECORD (from previous planning turn) ===\n{msg['parts'][0][:5000]}... (summary continues)\n"
        return ""

    def _extract_user_feedback(self, task_id: str) -> str:
        """Aggregate all user messages to capture every correction."""
        from src.infrastructure.persistence.db import get_history
        raw = get_history(task_id)
        feedback_parts = []
        for msg in raw:
            if msg["agent_name"].lower() == "user":
                feedback_parts.append(msg["parts"][0])
        
        if not feedback_parts:
            return ""
        
        return "\n=== CONSOLIDATED USER FEEDBACK / AMENDMENTS ===\n" + "\n---\n".join(feedback_parts) + "\n"

    def _parse_manager_decision(self, mgr_response: str) -> tuple[str, str]:
        """
        Manager is configured with response_mime_type=application/json, but models can still return:
        - a JSON object: { "next_agent": "...", "instruction": "..." }
        - a single-item array: [ { ... } ]
        This normalizes to (next_agent, instruction) or raises.
        """
        try:
            decision = json.loads(mgr_response)
        except Exception as e:
            raise ValueError(f"Manager returned non-JSON: {e}") from e

        if isinstance(decision, list):
            if len(decision) == 1 and isinstance(decision[0], dict):
                decision = decision[0]
            else:
                raise ValueError("Manager returned a JSON array (expected an object).")

        if not isinstance(decision, dict):
            raise ValueError("Manager returned JSON that is not an object.")

        next_agent_name = decision.get("next_agent")
        instruction = decision.get("instruction")
        if not isinstance(next_agent_name, str) or not isinstance(instruction, str):
            raise ValueError("Manager JSON missing required keys: next_agent (str), instruction (str).")

        return next_agent_name, instruction

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
            print(f"{Fore.RED}[Sync Error]{Style.RESET_ALL} Failed to sync {filepath}: {e}")

    def _extract_original_user_request(self, prompt: str) -> str:
        return extract_original_user_request(prompt)

    def _detect_user_language(self, text: str) -> str:
        return detect_user_language(text)

    def _with_language_context(self, instruction: str, original_user_request: str) -> str:
        return with_language_context(instruction, original_user_request)

    def _strip_trailing_builder_note(self, text: str) -> str:
        """
        Some model outputs append meta commentary like:
          **Builder Note:** ...
        after the last directive block. If we don't strip it, it can get saved into the last vault_file.
        """
        if not text:
            return text

        pattern = re.compile(r"(?im)^\s*(?:\*\*builder note:\*\*|builder note:)\s*")
        matches = list(pattern.finditer(text))
        if not matches:
            return text

        last = matches[-1]
        # Only strip if this "Builder Note" appears near the end, which is the problematic case.
        if last.start() < max(0, len(text) - 2500):
            return text

        return text[: last.start()].rstrip()

    # ── Unified block splitter ────────────────────────────────────────────────
    # Header tags the Builder is allowed to emit, in canonical lowercase form:
    #   vault_file, vault_asset, vault_folder, patch_vault_file,
    #   delete_vault_file, filepath
    _BLOCK_HEADER_RE = re.compile(
        r"^\s*#\s*"
        r"(?:"
        r"(?P<vault_file>[vV]ault[\s\-_]*[fF]ile)|"
        r"(?P<vault_asset>[vV]ault[\s\-_]*[aA]sset)|"
        r"(?P<vault_folder>[vV]ault[\s\-_]*[fF]older)|"
        r"(?P<patch>[pP]atch[\s\-_]*[vV]ault[\s\-_]*[fF]ile)|"
        r"(?P<delete>[dD]elete[\s\-_]*[vV]ault[\s\-_]*[fF]ile)|"
        r"(?P<filepath>[fF]ilepath)"
        r"):\s*(.+)",
        re.MULTILINE,
    )

    def _split_builder_blocks(self, builder_output: str) -> list[dict]:
        """
        Splits Builder output into typed blocks.
        Returns a list of dicts:
          { "type": "vault_file"|"vault_asset"|"vault_folder"|"patch"|"delete"|"filepath",
            "path": str,
            "body": str }
        This approach guarantees that N directives → N blocks, regardless of
        content length or the absence of a trailing separator.
        """
        lines = builder_output.splitlines(keepends=True)
        blocks: list[dict] = []
        current: dict | None = None
        current_lines: list[str] = []

        for line in lines:
            m = self._BLOCK_HEADER_RE.search(line)
            if m:
                # Save the previous block
                if current is not None:
                    current["body"] = "".join(current_lines).strip()
                    blocks.append(current)
                    current_lines = []

                # Determine type
                if m.group("vault_file"):
                    btype = "vault_file"
                elif m.group("vault_asset"):
                    btype = "vault_asset"
                elif m.group("vault_folder"):
                    btype = "vault_folder"
                elif m.group("patch"):
                    btype = "patch"
                elif m.group("delete"):
                    btype = "delete"
                else:
                    btype = "filepath"

                # Last capture group is always the path
                path = m.group(m.lastindex).strip()
                current = {"type": btype, "path": path, "body": ""}
            else:
                if current is not None:
                    current_lines.append(line)

        # Flush last block
        if current is not None:
            current["body"] = "".join(current_lines).strip()
            blocks.append(current)

        return blocks

    def extract_and_save_code(self, builder_output: str):
        """Guarda cada bloque # filepath: dentro de .workspace."""
        for block in self._split_builder_blocks(builder_output):
            if block["type"] != "filepath":
                continue
            filepath = block["path"]
            code_content = block["body"]
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Saving file via Builder: {filepath}")
            res = write_file_tool(filepath, code_content)
            self.callback.on_system_message(f"File saved: {filepath}")
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")

    def extract_and_save_vault_notes(self, builder_output: str) -> int:
        """Guarda cada bloque # vault_file: en Obsidian."""
        count = 0
        for block in self._split_builder_blocks(builder_output):
            if block["type"] != "vault_file":
                continue
            filepath = block["path"]
            content = self._strip_trailing_builder_note(block["body"])
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Saving note to Obsidian: {filepath}")
            res = write_obsidian_tool(filepath, content)
            self._sync_vault_node(filepath)
            self.callback.on_system_message(f"Note saved and synced: {filepath}")
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")
            count += 1
        return count

    def extract_and_save_vault_assets(self, builder_output: str) -> int:
        """Guarda cada bloque # vault_asset: en Obsidian."""
        count = 0
        for block in self._split_builder_blocks(builder_output):
            if block["type"] != "vault_asset":
                continue
            filepath = block["path"]
            content = self._strip_trailing_builder_note(block["body"])
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Saving asset to Obsidian: {filepath}")
            res = write_vault_asset_tool(filepath, content)
            self._sync_vault_node(filepath)
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")
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
                print(f"{Fore.RED}[System]{Style.RESET_ALL} Rejecting unsafe path: {file_path}")
                continue

            if file_path.lower().endswith(".md") or "." not in os.path.basename(file_path):
                print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Saving note (JSON): {file_path}")
                res = write_obsidian_tool(file_path, content)
                self._sync_vault_node(file_path)
                print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")
            else:
                print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Saving asset (JSON): {file_path}")
                res = write_vault_asset_tool(file_path, content)
                self._sync_vault_node(file_path)
                print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")
            count += 1

        return count
            
    def extract_and_create_folders(self, builder_output: str) -> int:
        """Crea cada carpeta listada con # vault_folder:."""
        count = 0
        for block in self._split_builder_blocks(builder_output):
            if block["type"] != "vault_folder":
                continue
            folder_path = block["path"]
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Creating folder in Obsidian: {folder_path}")
            res = create_vault_folder(folder_path)
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")
            count += 1
        return count

    def extract_and_apply_patches(self, builder_output: str, task_id: str) -> int:
        """Aplica cada parche listado con # patch_vault_file:."""
        count = 0
        for block in self._split_builder_blocks(builder_output):
            if block["type"] != "patch":
                continue
            filepath = block["path"]
            patch_text = block["body"]
            # Limpiar posibles cierres de bloque ``` sobrantes
            patch_text = re.sub(r"\n```$", "", patch_text).strip()
            patch_text = self._strip_trailing_builder_note(patch_text)
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Applying patch to: {filepath}")
            res = patch_vault_file_tool(filepath, patch_text, task_id, "Builder")
            self._sync_vault_node(filepath)
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")
            count += 1
        return count

    def extract_and_delete_vault_files(self, builder_output: str, task_id: str) -> int:
        """Elimina cada archivo listado con # delete_vault_file:."""
        count = 0
        for block in self._split_builder_blocks(builder_output):
            if block["type"] != "delete":
                continue
            filepath = block["path"]
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Deleting vault file: {filepath}")
            res = delete_vault_file_tool(filepath, task_id, "Builder")
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Result: {res}")
            count += 1
        return count

    def extract_and_run_commands(self, text: str) -> str:
        """Busca bloques bash y los intenta correr y devuelve la salida."""
        pattern = r"```(?:bash|sh|cmd|powershell)\n(.*?)```"
        matches = re.finditer(pattern, text, re.DOTALL)
        outputs = []
        for match in matches:
            cmd = match.group(1).strip()
            print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Found a command to execute.")
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
            "delete_vault_file",
            "wikilink",
            "cloud/",
        ]
        return any(k in s for k in keywords)

    def _normalize_intent_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
        return normalized.lower()

    def _count_bullet_points(self, text: str) -> int:
        if not text:
            return 0
        return len(re.findall(r"(?m)^\s*(?:[-*]|\d+[.)])\s+\S+", text))

    def _extract_quantity_token(self, token: str) -> int:
        if not token:
            return 0
        token = token.strip().lower()
        if token.isdigit():
            return int(token)

        word_to_number = {
            "un": 1,
            "una": 1,
            "uno": 1,
            "dos": 2,
            "tres": 3,
            "cuatro": 4,
            "cinco": 5,
            "seis": 6,
            "siete": 7,
            "ocho": 8,
            "nueve": 9,
            "diez": 10,
        }
        return word_to_number.get(token, 0)

    def _extract_requested_quantity(self, text: str, noun_patterns: list[str]) -> int:
        normalized = self._normalize_intent_text(text)
        token_group = r"(\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
        noun_group = "|".join(noun_patterns)
        patterns = [
            rf"\b{token_group}\s+(?:nuev[oa]s?\s+)?(?:{noun_group})\b",
            rf"\b(?:crea|crear|cree|genera|generar|haz|hacer|arma|organiza)\b[^.\n]{{0,40}}\b{token_group}\s+(?:nuev[oa]s?\s+)?(?:{noun_group})\b",
        ]

        counts = []
        for pattern in patterns:
            for match in re.finditer(pattern, normalized):
                counts.append(self._extract_quantity_token(match.group(1)))
        return max(counts) if counts else 0

    def _infer_expected_vault_outputs(self, original_user_request: str, builder_instruction: str) -> dict[str, int | bool]:
        request_text = original_user_request or builder_instruction or ""
        normalized = self._normalize_intent_text(request_text)
        bullet_count = self._count_bullet_points(request_text)

        min_notes = self._extract_requested_quantity(
            request_text,
            [
                r"notas?",
                r"notes?",
                r"archivos? markdown",
                r"archivos? \.md",
                r"documentos? markdown",
            ],
        )
        min_folders = self._extract_requested_quantity(
            request_text,
            [
                r"carpetas?",
                r"folders?",
                r"directorios?",
            ],
        )

        if min_notes == 0:
            per_point_patterns = [
                r"\b(?:una\s+)?nota\s+por\s+cada\s+punto\b",
                r"\bnotas?\s+para\s+cada\s+punto\b",
                r"\bnota\s+para\s+cada\s+tema\b",
                r"\bnotas?\s+para\s+cada\s+tema\b",
                r"\bnota\s+por\s+cada\s+subtema\b",
                r"\bnotas?\s+por\s+cada\s+subtema\b",
                r"\bone\s+note\s+per\s+point\b",
                r"\bnotes?\s+for\s+each\s+point\b",
            ]
            if any(re.search(pattern, normalized) for pattern in per_point_patterns):
                min_notes = bullet_count if bullet_count >= 2 else 3

        if min_notes == 0:
            if re.search(r"\b(?:crea|crear|cree|genera|generar|haz|hacer|arma)\b[^.\n]{0,50}\b(?:notas|notes)\b", normalized):
                min_notes = 2
            elif re.search(r"\b(?:crea|crear|cree|genera|generar|haz|hacer|arma)\b[^.\n]{0,50}\b(?:nota|note|archivo markdown|archivo \.md)\b", normalized):
                min_notes = 1

        if min_folders == 0:
            if re.search(r"\b(?:crea|crear|cree|genera|generar|haz|hacer|arma)\b[^.\n]{0,50}\b(?:carpetas|folders|directorios)\b", normalized):
                min_folders = 1
            elif re.search(r"\b(?:crea|crear|cree|genera|generar|haz|hacer|arma)\b[^.\n]{0,50}\b(?:carpeta|folder|directorio)\b", normalized):
                min_folders = 1

        if min_notes > 0 and bullet_count >= 2 and re.search(r"\b(?:cada\s+punto|cada\s+tema|cada\s+subtema|for\s+each\s+point)\b", normalized):
            min_notes = max(min_notes, bullet_count)

        return {
            "min_notes": min_notes,
            "min_folders": min_folders,
            "force_markdown": ".md" in normalized or "markdown" in normalized,
        }

    def _summarize_builder_output(self, builder_output: str) -> dict[str, int]:
        note_paths = [match.group(1).strip() for match in re.finditer(r"(?:^|\n)#\s*[vV]ault[\s\-_]*[fF]ile:\s*(.+?)(?:\n|$)", builder_output)]
        asset_count = sum(1 for _ in re.finditer(r"(?:^|\n)#\s*[vV]ault[\s\-_]*[aA]sset:\s*(.+?)(?:\n|$)", builder_output))
        folder_count = sum(1 for _ in re.finditer(r"(?:^|\n)#\s*[vV]ault[\s\-_]*[fF]older:\s*(.+?)(?:\n|$)", builder_output))
        patch_count = sum(1 for _ in re.finditer(r"(?:^|\n)#\s*[pP]atch[\s\-_]*[vV]ault[\s\-_]*[fF]ile:\s*(.+?)(?:\n|$)", builder_output))
        delete_count = sum(1 for _ in re.finditer(r"(?:^|\n)#\s*[dD]elete[\s\-_]*[vV]ault[\s\-_]*[fF]ile:\s*(.+?)(?:\n|$)", builder_output))

        json_note_count = 0
        json_asset_count = 0
        for item in parse_builder_files_from_text(builder_output):
            file_path = item["file_path"].strip().replace("\\", "/").lstrip("/")
            if file_path.lower().endswith(".md") or "." not in os.path.basename(file_path):
                json_note_count += 1
            else:
                json_asset_count += 1

        explicit_note_count = len(note_paths)
        non_md_note_paths = sum(
            1
            for path in note_paths
            if "." in os.path.basename(path) and not path.lower().endswith(".md")
        )

        return {
            "notes": explicit_note_count + json_note_count,
            "folders": folder_count,
            "assets": asset_count + json_asset_count,
            "patches": patch_count,
            "deletes": delete_count,
            "non_md_note_paths": non_md_note_paths,
            "total_writes": explicit_note_count + json_note_count + folder_count + asset_count + json_asset_count + patch_count + delete_count,
        }

    def _get_builder_output_shortfalls(
        self,
        original_user_request: str,
        builder_instruction: str,
        builder_output: str,
    ) -> list[str]:
        expected = self._infer_expected_vault_outputs(original_user_request, builder_instruction)
        actual = self._summarize_builder_output(builder_output)
        reasons: list[str] = []

        if expected["min_notes"] > actual["notes"]:
            reasons.append(
                f"The request implies at least {expected['min_notes']} separate markdown notes, but the output only contains {actual['notes']}."
            )
        if expected["min_folders"] > 0 and actual["folders"] == 0:
            reasons.append(
                f"The request implies folder creation, but the output contains 0 folder directives."
            )
        if expected["force_markdown"] and actual["non_md_note_paths"] > 0:
            reasons.append("Every note path must end in .md when the user explicitly asks for markdown notes.")

        return reasons

    def _build_builder_reemit_instruction(self, original_instruction: str, previous_output: str, shortfalls: Optional[list[str]] = None) -> str:
        issue_summary = ""
        if shortfalls:
            issue_summary = "Problems to fix before re-emitting:\n- " + "\n- ".join(shortfalls) + "\n\n"

        return (
            "Your previous response did NOT satisfy the required vault output structure. Re-emit the SAME work using ONLY these directives:\n"
            "- # vault_folder: <path>\n"
            "- # vault_file: <path/note.md>\n"
            "- # vault_asset: <path/file.ext>\n\n"
            "- # patch_vault_file: <path/note.md>\n"
            "- # delete_vault_file: <path/note.md>\n\n"
            "Rules:\n"
            "- Do NOT output JSON.\n"
            "- If the request asks for multiple notes, create one separate # vault_file block per note. Do NOT merge multiple requested points into one file.\n"
            "- If the request asks for folders, emit explicit # vault_folder directives for them.\n"
            "- Every note created with # vault_file must end with the .md extension.\n"
            "- Do NOT wrap wikilinks like [[Note]] in backticks.\n"
            "- Do NOT include any ```bash/cmd/powershell``` command blocks.\n"
            "- Keep the content identical; just change the packaging/format so the Orchestrator can save it.\n\n"
            f"{issue_summary}"
            f"Original Builder instruction:\n{original_instruction}\n\n"
            f"Previous output to reformat:\n{previous_output}"
        )

    def process_task(self, task_id: str, prompt: str, mode: str = "Standard", workflow: str = "Plan"):
        # Load Persona/Mode instruction
        default_mode = "Standard" if "Standard" in PERSONAS else (next(iter(PERSONAS.keys())) if PERSONAS else None)
        effective_mode = mode if mode in PERSONAS else default_mode
        if not effective_mode:
            raise ValueError("No personas configured.")
        persona = PERSONAS[effective_mode]

        # Workflow Policy
        if workflow == "Execute":
            wf_instruction = (
                "\n\n=== CURRENT WORKFLOW: EXECUTE ===\n"
                "Your priority is to IMPLEMENT the agreed plan from the chat history.\n"
                "1. Use 'Builder' to create/modify files.\n"
                "2. Use 'Critic' for quality review.\n"
                "3. Use 'Planner' or 'Researcher' only if critical missing details arise during execution.\n"
                "Finish quickly with a professional summary once the work is applied."
            )
        else:  # Plan Mode
            wf_instruction = (
                "\n\n=== CURRENT WORKFLOW: PLAN ===\n"
                "Your priority is to RESEARCH, DESIGN, and PROPOSE.\n"
                "1. DO NOT call the 'Builder' for permanent vault writes or file creation.\n"
                "2. Work with 'Planner' and 'Researcher' to create a high-quality proposal.\n"
                "3. ALWAYS end by calling 'User' to ask for feedback, clarification, or approval of the proposed plan.\n"
                "Do not finalize until the user is satisfied with the architecture."
            )

        log = logging.LoggerAdapter(logging.getLogger(__name__), {"task_id": task_id, "agent": "Orchestrator"})
        log.info("Task loop started")

        current_prompt = prompt
        original_user_request = self._extract_original_user_request(prompt)
        manager_language_policy = build_manager_language_policy(original_user_request)

        # Context Extraction for Memory System
        plan_of_record = self._extract_plan_of_record(task_id)
        consolidated_feedback = self._extract_user_feedback(task_id)
        
        # Build memory-aware instruction
        memory_instruction = f"\n\n=== RECENT CONTEXT SUMMARY ===\n{plan_of_record}\n{consolidated_feedback}"
        
        self.manager.update_system_prompt(
            persona["instruction"] + wf_instruction + memory_instruction + "\n\n" + manager_language_policy
        )

        print(f"\n{Fore.GREEN}[User]{Style.RESET_ALL} (Mode: {effective_mode}): {prompt}\n")
        
        while True:
            # 1. Manager decides the next step
            self.callback.on_agent_start("Manager", f"Deciding next step for: {current_prompt[:50]}...")
            print(f"{Fore.MAGENTA}[Manager]{Style.RESET_ALL} processing next step...")
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
                next_agent_name, instruction = self._parse_manager_decision(mgr_response)
            except Exception as e:
                # One retry with stricter instruction to avoid aborting due to a minor formatting slip.
                log.warning("Manager returned invalid decision payload. Retrying once. Error=%s", str(e))
                retry_prompt = (
                    "Return ONLY a single JSON object (not an array) with exactly these keys:\n"
                    '{ "next_agent": "Planner|Builder|Critic|User", "instruction": "..." }\n'
                    "No markdown, no extra keys, no surrounding text."
                )
                try:
                    mgr_response_retry = self.manager.execute(task_id, retry_prompt)
                    self.callback.on_agent_end("Manager", mgr_response_retry)
                    next_agent_name, instruction = self._parse_manager_decision(mgr_response_retry)
                except Exception:
                    print(f"[Error] Manager did not return valid JSON. Aborting. {mgr_response}")
                    log.error("Manager returned invalid JSON: %s", mgr_response)
                    break
            
            print(f"{Fore.MAGENTA}[Manager]{Style.RESET_ALL} calls {Fore.YELLOW}{next_agent_name}{Style.RESET_ALL}: {instruction}\n")
            
            if next_agent_name.lower() == "user":
                self.callback.on_agent_start("Summarizer", "Finalizando reporte...")
                # We update the summarizer persona using the current mode too
                summarizer_instruction = with_language_context(
                    PERSONAS.get("Summarizer", {}).get("instruction", SUMMARIZER_PROMPT),
                    prompt
                )
                self.summarizer.update_system_prompt(summarizer_instruction)
                
                # Execute summarizer over the manager's instruction (which holds the report)
                final_report = self.summarizer.execute(task_id, instruction)
                self.callback.on_agent_end("Summarizer", final_report)
                print(f"\n{Fore.GREEN}[Task finished]{Style.RESET_ALL} {final_report}")
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

                planner_prompt = self._with_language_context(
                    f"{instruction}\n\n=== CURRENT VAULT STRUCTURE ===\n{vault_tree}{relational_context}",
                    original_user_request,
                )
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
                researcher_instruction = self._with_language_context(instruction, original_user_request)
                self.callback.on_agent_start("Researcher", instruction)
                try:
                    result = self.researcher.execute(task_id, researcher_instruction)
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
                builder_instruction = self._with_language_context(instruction, original_user_request)
                self.callback.on_agent_start("Builder", instruction)
                try:
                    result = self.builder.execute(task_id, builder_instruction)
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
                vault_writes += self.extract_and_delete_vault_files(result, task_id)
                # Fallback: if Builder returns JSON-ish files, save them too.
                vault_writes += self.extract_and_save_vault_json_files(result)

                shortfalls = self._get_builder_output_shortfalls(original_user_request, instruction, result)
                needs_reemit = False

                # Avoid "false success": if we expected vault output but saved nothing, or if the Builder under-produced
                # relative to an explicitly multi-file / folder request, force a single re-emit.
                if vault_writes == 0 and self._expects_vault_writes(f"{instruction}\n{original_user_request}"):
                    needs_reemit = True
                    if not shortfalls:
                        shortfalls = [
                            "The response did not produce any vault write directives that the Orchestrator could save."
                        ]

                if shortfalls:
                    needs_reemit = True

                if needs_reemit:
                    log.warning("Builder produced no vault writes. Forcing a re-emit in save-directive format.")
                    print(
                        f"{Fore.YELLOW}[System]{Style.RESET_ALL} Builder needs a structured re-emit. "
                        "Requesting output split by files/folders...\n"
                    )
                    reemit_instruction = self._with_language_context(
                        self._build_builder_reemit_instruction(instruction, result, shortfalls),
                        original_user_request,
                    )
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
                        vault_writes += self.extract_and_delete_vault_files(reformatted, task_id)
                        vault_writes += self.extract_and_save_vault_json_files(reformatted)
                        if vault_writes > 0:
                            result = reformatted
                cmd_results = self.extract_and_run_commands(result)
                
                builder_feedback = result
                if cmd_results:
                    builder_feedback += f"\n\nExecuted Commands Results:\n{cmd_results}"
                    
                current_prompt = f"Builder ended its work. Feedback: {builder_feedback}. Manager, should Critic review it?"
                
            elif next_agent_name.lower() == "critic":
                critic_instruction = self._with_language_context(instruction, original_user_request)
                self.callback.on_agent_start("Critic", instruction)
                try:
                    result = self.critic.execute(task_id, critic_instruction)
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
                print(f"Unknown agent: {next_agent_name}")
                break
