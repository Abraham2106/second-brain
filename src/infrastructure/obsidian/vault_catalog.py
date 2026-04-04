import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.infrastructure.config.config import normalize_obsidian_vault_path


INVALID_VAULT_NAME = re.compile(r'[<>:"/\\|?*]')


@dataclass(frozen=True)
class VaultOption:
    name: str
    path: str
    source: str


def get_vaults_root() -> Path:
    return (Path(__file__).resolve().parent.parent.parent.parent / "obsidian-vaults").resolve()


def _add_vault_option(options: List[VaultOption], path: Path, source: str) -> None:
    if not path.exists() or not path.is_dir():
        return

    normalized = path.resolve().as_posix()
    if any(item.path == normalized for item in options):
        return

    options.append(
        VaultOption(
            name=path.name or normalized,
            path=normalized,
            source=source,
        )
    )


def list_vaults(active_path: Optional[str] = None) -> List[VaultOption]:
    root = get_vaults_root()
    root.mkdir(parents=True, exist_ok=True)

    options: List[VaultOption] = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            _add_vault_option(options, child, "workspace")

    normalized_active = normalize_obsidian_vault_path(active_path)
    if normalized_active:
        _add_vault_option(options, Path(normalized_active), "external")

    return sorted(options, key=lambda item: (item.source != "workspace", item.name.lower()))


def validate_vault_name(name: str) -> str:
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Enter a name for the vault.")
    if clean in {".", ".."}:
        raise ValueError("That vault name is not valid.")
    if INVALID_VAULT_NAME.search(clean):
        raise ValueError('The name cannot contain: < > : " / \\ | ? *')
    return clean


def create_vault(name: str) -> VaultOption:
    vault_name = validate_vault_name(name)
    root = get_vaults_root()
    root.mkdir(parents=True, exist_ok=True)

    vault_dir = root / vault_name
    if vault_dir.exists():
        raise FileExistsError(f"The vault '{vault_name}' already exists.")

    vault_dir.mkdir(parents=True, exist_ok=False)
    return VaultOption(name=vault_name, path=vault_dir.resolve().as_posix(), source="workspace")
