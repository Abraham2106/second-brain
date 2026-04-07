import logging
import time
import requests
from typing import Optional, Tuple, Protocol

from src.infrastructure.config.config import get_settings
from src.infrastructure.persistence.db import get_history, save_message
from src.core.errors import ConfigError, GeminiBackendsExhausted, GeminiRequestFailed


def _build_prompt_with_history(task_id: str, prompt: str) -> Tuple[str, bool]:
    """
    Returns (final_prompt, has_history).
    Structures the history to highlight user instructions and agent roles.
    """
    raw_history = get_history(task_id)
    if not raw_history:
        return prompt, False

    context_parts = ["=== PREVIOUS CONVERSATION CONTEXT ==="]
    
    for msg in raw_history:
        role = msg["agent_name"]
        content = msg["parts"][0]
        
        if role.lower() == "user":
            tag = "[USER FEEDBACK / CRITICAL INSTRUCTION]"
        elif role.lower() == "manager":
            tag = "[COORDINATOR DECISION]"
        elif role.lower().endswith("_instruction"):
            agent_name = role.split("_")[0].capitalize()
            tag = f"[INSTRUCTION TO {agent_name}]"
        else:
            tag = f"[{role} OUTPUT]"
            
        context_parts.append(f"{tag}:\n{content}")

    context_parts.append("=== END OF PREVIOUS CONTEXT ===")
    context_block = "\n\n".join(context_parts)

    final_prompt = (
        f"{context_block}\n\n"
        "NEW INSTRUCTION FOR YOU:\n"
        f"[from Manager/User]: {prompt}"
    )
    return final_prompt, True


class Agent(Protocol):
    def execute(self, task_id: str, prompt: str) -> str:
        ...


class AI_Agent:
    def __init__(self, name: str, system_prompt: str, model_name: Optional[str] = None, require_json: bool = False):
        self.name = name
        self.system_prompt = system_prompt
        self.preferred_model = model_name
        self.require_json = require_json
        
        self.system_instruction = f"Agent Role: {self.name}\n{self.system_prompt}"

    def update_system_prompt(self, additional_instruction: str):
        """Inject additional system instructions without recreating the agent."""
        full_prompt = f"Agent Role: {self.name}\n{self.system_prompt}\n\n[USER_SELECTED_MODE_INSTRUCTION]:\n{additional_instruction}"
        self.system_instruction = full_prompt

    def execute(self, task_id: str, prompt: str) -> str:
        settings = get_settings()

        log = logging.LoggerAdapter(logging.getLogger(__name__), {"task_id": task_id, "agent": self.name})

        final_prompt, has_history = _build_prompt_with_history(task_id, prompt)

        preferred_model = self.preferred_model or (settings.gemini_models[0] if settings.gemini_models else "gemini-2.5-flash")

        payload = {
            "model": preferred_model,
            "messages": [
                {"role": "system", "content": self.system_instruction},
                {"role": "user", "content": final_prompt}
            ]
        }
        
        if self.require_json:
            payload["response_format"] = {"type": "json_object"}

        log.info(f"Sending request to proxy at {settings.gemini_proxy_url} for model {preferred_model}")
        
        try:
            response = requests.post(settings.gemini_proxy_url, json=payload, timeout=300)
            
            if response.status_code != 200:
                err_msg = response.text
                log.error(f"Proxy returned error {response.status_code}: {err_msg}")
                raise GeminiRequestFailed(f"Proxy Error {response.status_code}: {err_msg}")
                
            data = response.json()
            output = data["choices"][0]["message"]["content"]
            
        except requests.exceptions.RequestException as e:
            log.exception(f"HTTP Request failed on {settings.gemini_proxy_url}: {str(e)}")
            raise GeminiRequestFailed(f"Proxy connection error: {str(e)}") from e

        # 🧠 Structured Memory: Save the input and output for every turn
        if prompt:
            # Distinguish between Manager calls from User and Manager calls to other agents
            if self.name.lower() == "manager":
                role_to_save = "user" # The Manager's input is always the User/Task prompt
            else:
                # The input to any other agent is an instruction from the Manager
                role_to_save = f"{self.name}_instruction"
            
            save_message(task_id, role_to_save, prompt)

        save_message(task_id, self.name, output)
        return output
