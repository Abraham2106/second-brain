import logging
import time
from typing import Optional, Tuple

from google import genai
from google.genai import types

from .config import get_settings
from .db import get_history, save_message
from .errors import ConfigError, GeminiBackendsExhausted, GeminiRequestFailed
from .gemini_balancer import GeminiLoadBalancer, parse_retry_delay_seconds


_BALANCER: Optional[GeminiLoadBalancer] = None


def _get_balancer() -> GeminiLoadBalancer:
    global _BALANCER
    if _BALANCER is not None:
        return _BALANCER

    settings = get_settings()
    if not settings.gemini_api_keys:
        raise ConfigError("No Gemini API keys found. Set GEMINI_API_KEY or GEMINI_API_KEYS in .env.")
    if not settings.gemini_models:
        raise ConfigError("No Gemini models configured. Set GEMINI_MODELS or rely on defaults.")

    _BALANCER = GeminiLoadBalancer(api_keys=settings.gemini_api_keys, models=settings.gemini_models)
    return _BALANCER


def _build_prompt_with_history(task_id: str, prompt: str) -> Tuple[str, bool]:
    """
    Returns (final_prompt, has_history).
    Only the first user prompt per task_id is persisted as role 'user' in SQLite.
    """
    raw_history = get_history(task_id)
    if not raw_history:
        return prompt, False

    context_block = "=== PREVIOUS CHAT HISTORY ===\n"
    for msg in raw_history:
        role = msg["agent_name"]
        content = msg["parts"][0]
        context_block += f"[{role}]: {content}\n\n"
    context_block += "=============================\n"

    final_prompt = f"{context_block}\nNew message for you:\n[user/manager]: {prompt}"
    return final_prompt, True


class AI_Agent:
    def __init__(self, name: str, system_prompt: str, model_name: Optional[str] = None, require_json: bool = False):
        self.name = name
        self.system_prompt = system_prompt
        self.preferred_model = model_name
        self.require_json = require_json

        self.config = types.GenerateContentConfig()
        self.config.system_instruction = f"Agent Role: {self.name}\n{self.system_prompt}"
        if self.require_json:
            self.config.response_mime_type = "application/json"

    def execute(self, task_id: str, prompt: str) -> str:
        settings = get_settings()
        balancer = _get_balancer()

        log = logging.LoggerAdapter(logging.getLogger(__name__), {"task_id": task_id, "agent": self.name})

        final_prompt, has_history = _build_prompt_with_history(task_id, prompt)

        preferred_model = self.preferred_model or (settings.gemini_models[0] if settings.gemini_models else None)
        if not preferred_model:
            raise ConfigError("No Gemini models configured.")

        rounds = max(1, settings.gemini_max_rounds)

        for _ in range(rounds):
            now = time.time()
            attempted = False

            for key_index, api_key in balancer.iter_keys():
                for model in balancer.iter_models(preferred_model):
                    if not balancer.is_available(api_key, model, now):
                        continue

                    attempted = True
                    try:
                        client = genai.Client(api_key=api_key)
                        response = client.models.generate_content(
                            model=model,
                            contents=final_prompt,
                            config=self.config,
                        )
                        output = response.text or ""
                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str:
                            retry_s = parse_retry_delay_seconds(err_str)
                            balancer.note_rate_limited(api_key, model, retry_s)
                            log.warning(
                                "429 rate limit on model=%s. Cooling down%s and rotating.",
                                model,
                                f" ({retry_s}s)" if retry_s else "",
                            )
                            time.sleep(1)
                            continue

                        log.exception("Gemini request failed on model=%s: %s", model, err_str)
                        raise GeminiRequestFailed(f"Error calling Gemini model '{model}': {err_str}") from e

                    if not has_history:
                        save_message(task_id, "user", prompt)

                    save_message(task_id, self.name, output)
                    balancer.note_success(key_index)
                    return output

            if not attempted:
                sleep_s = balancer.soonest_ready_in()
                sleep_s = min(60.0, max(1.0, sleep_s))
                log.warning("All keys/models in cooldown. Sleeping %ss...", int(sleep_s))
                time.sleep(sleep_s)

        raise GeminiBackendsExhausted("All keys/models exhausted or rate-limited.")

