import os
import time
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


def _split_csv(value: str) -> List[str]:
    # Accept comma or newline separated lists. Strip quotes/spaces.
    raw = re.split(r"[,\n]+", value)
    out: List[str] = []
    for item in raw:
        s = item.strip().strip('"').strip("'").strip()
        if s:
            out.append(s)
    return out


def load_gemini_api_keys_from_env() -> List[str]:
    """
    Supports:
      - GEMINI_API_KEYS="k1,k2,k3"
      - GEMINI_API_KEY="single_key" (fallback)
    """
    keys_csv = os.getenv("GEMINI_API_KEYS", "").strip()
    if keys_csv:
        keys = _split_csv(keys_csv)
        if keys:
            return keys
    single = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    return [single] if single else []


def load_gemini_models_from_env(default_models: List[str]) -> List[str]:
    """
    Optional override:
      - GEMINI_MODELS="gemini-2.5-flash,gemini-2.0-flash-lite"
    """
    models_csv = os.getenv("GEMINI_MODELS", "").strip()
    if not models_csv:
        return list(default_models)
    models = _split_csv(models_csv)
    return models or list(default_models)


def parse_retry_delay_seconds(err_str: str) -> Optional[int]:
    """
    Best-effort parser for RetryInfo retryDelay (often "42s") inside exception str().
    """
    # Examples seen:
    #   ... 'retryDelay': '42s.' ...
    #   ... "retryDelay": "42s" ...
    m = re.search(r"retryDelay['\"]\s*:\s*['\"](\d+)s", err_str)
    if m:
        return int(m.group(1))
    return None


@dataclass
class _KeyState:
    # Per model: unix timestamp (seconds) when it becomes available again.
    model_available_at: Dict[str, float] = field(default_factory=dict)

    def is_model_available(self, model: str, now: float) -> bool:
        return self.model_available_at.get(model, 0.0) <= now

    def next_model_ready_time(self, models: List[str]) -> float:
        # Return the earliest time any model is available again.
        if not models:
            return time.time()
        return min(self.model_available_at.get(m, 0.0) for m in models)


class GeminiLoadBalancer:
    """
    In-memory balancer:
      - Rotates across (api_key, model) on 429.
      - Tracks cooldown per (api_key, model) using retryDelay when present.
    """

    def __init__(self, api_keys: List[str], models: List[str]):
        clean_keys = [k for k in api_keys if k]
        if not clean_keys:
            raise ValueError("No Gemini API keys found. Set GEMINI_API_KEY or GEMINI_API_KEYS.")
        if not models:
            raise ValueError("No Gemini models configured.")

        self.api_keys = clean_keys
        self.models = list(models)
        self._state: Dict[str, _KeyState] = {k: _KeyState() for k in self.api_keys}
        self._rr_key = 0

    def choose(self) -> Tuple[str, str]:
        """
        Picks the next available (key, model) using:
          1) round-robin keys
          2) first available model in configured order
        Raises RuntimeError if none available *right now*.
        """
        now = time.time()
        nkeys = len(self.api_keys)

        for i in range(nkeys):
            key_idx = (self._rr_key + i) % nkeys
            key = self.api_keys[key_idx]
            ks = self._state[key]
            for model in self.models:
                if ks.is_model_available(model, now):
                    self._rr_key = (key_idx + 1) % nkeys
                    return key, model

        raise RuntimeError("No (key, model) available right now.")

    def note_rate_limited(self, api_key: str, model: str, retry_after_s: Optional[int]) -> None:
        now = time.time()
        cooldown = float(retry_after_s if retry_after_s is not None else 30)
        ready_at = now + max(1.0, cooldown)
        ks = self._state.setdefault(api_key, _KeyState())
        ks.model_available_at[model] = max(ks.model_available_at.get(model, 0.0), ready_at)

    def soonest_ready_in(self) -> float:
        now = time.time()
        soonest = None
        for key in self.api_keys:
            ks = self._state.get(key)
            if not ks:
                continue
            t = ks.next_model_ready_time(self.models)
            soonest = t if soonest is None else min(soonest, t)
        if soonest is None:
            return 0.0
        return max(0.0, soonest - now)

