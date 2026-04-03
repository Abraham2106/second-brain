import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv
from .db import get_history, save_message
from .gemini_balancer import (
    GeminiLoadBalancer,
    load_gemini_api_keys_from_env,
    load_gemini_models_from_env,
    parse_retry_delay_seconds,
)

load_dotenv()

# Lista de modelos para rotación (Failover)
# Ordenados de mayor capacidad a menor para priorizar calidad
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.0-flash-lite",
    "gemini-3.1-flash-live-preview",
    "gemini-flash-latest"
]


# Balancer global (llaves + modelos). Se inicializa una vez.
_BALANCER = None


def _get_balancer() -> GeminiLoadBalancer:
    global _BALANCER
    if _BALANCER is not None:
        return _BALANCER
    keys = load_gemini_api_keys_from_env()
    models = load_gemini_models_from_env(GEMINI_MODELS)
    _BALANCER = GeminiLoadBalancer(api_keys=keys, models=models)
    return _BALANCER


class AI_Agent:
    def __init__(self, name: str, system_prompt: str, model_name: str = None, require_json=False):
        self.name = name
        self.system_prompt = system_prompt
        # Si no se especifica, usará el primero de la lista global
        self.model_name = model_name or GEMINI_MODELS[0]
        self.require_json = require_json
        
        # El cliente se crea por request para poder rotar llaves (API keys).
        
        # Configuración de generación
        self.config = types.GenerateContentConfig()
        self.config.system_instruction = f"Agent Role: {self.name}\n{self.system_prompt}"
        
        if self.require_json:
            self.config.response_mime_type = "application/json"

    def execute(self, task_id: str, prompt: str) -> str:
        # Cargar historial
        raw_history = get_history(task_id)
        
        context_block = "=== PREVIOUS CHAT HISTORY ===\n"
        has_history = False
        for msg in raw_history:
            has_history = True
            role = msg["agent_name"]
            content = msg["parts"][0]
            context_block += f"[{role}]: {content}\n\n"
        context_block += "=============================\n"
        
        final_prompt = prompt
        if has_history:
             final_prompt = f"{context_block}\nNew message for you:\n[user/manager]: {prompt}"
        
        balancer = _get_balancer()
        models = balancer.models

        # Empezar por el modelo preferido (si está en la lista); si no, arrancar en 0.
        start_model_idx = 0
        if self.model_name in models:
            start_model_idx = models.index(self.model_name)

        # Rondas controladas para evitar bucles infinitos si todas las llaves/modelos están agotados.
        rounds = 3
        for _ in range(rounds):
            now = time.time()
            nkeys = len(balancer.api_keys)
            nmodels = len(models)
            any_attempted = False

            # Política: por cada llave, probar todos los modelos; solo cambiar de llave cuando esa llave ya no tenga modelos disponibles.
            for k in range(nkeys):
                key_idx = (balancer._rr_key + k) % nkeys
                api_key = balancer.api_keys[key_idx]

                for m in range(nmodels):
                    model = models[(start_model_idx + m) % nmodels]
                    ks = balancer._state.get(api_key)
                    if ks is not None and not ks.is_model_available(model, now):
                        continue

                    any_attempted = True
                    try:
                        client = genai.Client(api_key=api_key)
                        response = client.models.generate_content(
                            model=model,
                            contents=final_prompt,
                            config=self.config
                        )
                        output = response.text

                        if not has_history:
                            save_message(task_id, "user", prompt)

                        save_message(task_id, self.name, output)
                        # Avanzar round-robin de llave para la próxima ejecución global.
                        balancer._rr_key = (key_idx + 1) % nkeys
                        return output

                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str:
                            retry_s = parse_retry_delay_seconds(err_str)
                            balancer.note_rate_limited(api_key, model, retry_s)
                            print(
                                f"[{self.name}] 429 en modelo={model} (key#{key_idx+1}/{nkeys}). "
                                f"Rotando modelo; si se agotan, rotamos llave..."
                            )
                            time.sleep(1)
                            continue

                        err_msg = f"Error en {model}: {err_str}"
                        print(err_msg)
                        return "{ \"next_agent\": \"User\", \"instruction\": \"Error occurred API limit or connectivity.\"}"

            if not any_attempted:
                sleep_s = balancer.soonest_ready_in()
                sleep_s = min(60.0, max(1.0, sleep_s))
                print(f"[{self.name}] Todas las llaves/modelos están en cooldown. Esperando {int(sleep_s)}s...")
                time.sleep(sleep_s)

        return "{ \"next_agent\": \"User\", \"instruction\": \"All keys/models exhausted or rate limited.\"}"
