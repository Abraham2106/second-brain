import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


def _strip_quotes(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1]
    return v.strip()


def _split_csv(value: str) -> List[str]:
    raw = re.split(r"[,\n]+", value)
    out: List[str] = []
    for item in raw:
        s = _strip_quotes(item)
        if s:
            out.append(s)
    return out


def _parse_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Gemini Proxy
    gemini_proxy_url: str
    gemini_models: List[str]
    gemini_max_rounds: int

    # Obsidian
    obsidian_vault_path: Optional[str]

    # Redis (optional)
    redis_host: str
    redis_port: int
    redis_db: int

    # Local paths
    workspace_dir: str
    logs_dir: str
    log_level: str


_SETTINGS: Optional[Settings] = None
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
_ENV_PATH = _ROOT_DIR / ".env"


def get_settings() -> Settings:
    """Loads .env once and returns parsed settings (cached)."""
    global _SETTINGS
    if _SETTINGS is not None:
        return _SETTINGS

    # Load .env into process env once.
    load_dotenv(str(_ENV_PATH))

    # Instead of local keys, we define the proxy endpoint
    proxy_url = os.getenv("GEMINI_PROXY_URL", "http://127.0.0.1:8000/v1/chat/completions").strip()

    models_csv = os.getenv("GEMINI_MODELS", "").strip()
    if models_csv:
        models = _split_csv(models_csv)
    else:
        # Default model order (mirrors src/base_agent.py constant).
        models = [
            "gemini-2.5-flash",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.0-flash-lite",
            "gemini-3.1-flash-live-preview",
            "gemini-flash-latest",
        ]

    vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    vault_path = _strip_quotes(vault_path) if vault_path else ""

    _SETTINGS = Settings(
        gemini_proxy_url=proxy_url,
        gemini_models=[m for m in models if m],
        gemini_max_rounds=_parse_int("GEMINI_MAX_ROUNDS", 3),
        obsidian_vault_path=vault_path or None,
        redis_host=os.getenv("REDIS_HOST", "localhost").strip() or "localhost",
        redis_port=_parse_int("REDIS_PORT", 6379),
        redis_db=_parse_int("REDIS_DB", 0),
        workspace_dir=os.getenv("WORKSPACE_DIR", ".workspace").strip() or ".workspace",
        logs_dir=os.getenv("LOGS_DIR", "logs").strip() or "logs",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
    )
    return _SETTINGS


def reset_settings_cache() -> None:
    global _SETTINGS
    _SETTINGS = None


def normalize_obsidian_vault_path(vault_path: Optional[str]) -> Optional[str]:
    if not vault_path:
        return None

    clean = _strip_quotes(vault_path)
    if not clean:
        return None

    return Path(clean).expanduser().resolve(strict=False).as_posix()


def persist_env_value(name: str, value: str) -> None:
    lines: List[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    new_line = f'{name}="{value}"'
    replaced = False
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=")

    for idx, line in enumerate(lines):
        if pattern.match(line):
            lines[idx] = new_line
            replaced = True
            break

    if not replaced:
        lines.append(new_line)

    _ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def set_obsidian_vault_path(vault_path: Optional[str], persist: bool = False) -> Optional[str]:
    normalized = normalize_obsidian_vault_path(vault_path)

    if normalized:
        os.environ["OBSIDIAN_VAULT_PATH"] = normalized
        if persist:
            persist_env_value("OBSIDIAN_VAULT_PATH", normalized)
    else:
        os.environ.pop("OBSIDIAN_VAULT_PATH", None)

    reset_settings_cache()
    return normalized
