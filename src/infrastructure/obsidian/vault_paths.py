import os
import re
import unicodedata

from dotenv import load_dotenv


def get_vault_dir() -> str:
    # Ensure we load the .env from the project root
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    _env_path = os.path.join(_root, ".env")
    load_dotenv(_env_path)
    
    vault_dir = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_dir:
        raise ValueError("OBSIDIAN_VAULT_PATH not set")
    return vault_dir.strip('"').strip("'").strip()


def normalize_folder_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[-_\s]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)

    words = []
    for word in normalized.split():
        singular = word
        if len(word) > 4:
            if word.endswith("es"):
                singular = word[:-2]
            elif word.endswith("s"):
                singular = word[:-1]
        words.append(singular)

    return " ".join(words)


def list_child_dirs(parent_dir: str) -> list[str]:
    try:
        return [
            name for name in os.listdir(parent_dir)
            if os.path.isdir(os.path.join(parent_dir, name)) and not name.startswith(".")
        ]
    except Exception:
        return []


def match_existing_child(parent_dir: str, desired_segment: str) -> str | None:
    children = list_child_dirs(parent_dir)
    desired_lower = desired_segment.lower()

    for child in children:
        if child.lower() == desired_lower:
            return child

    desired_normalized = normalize_folder_token(desired_segment)
    matches = [child for child in children if normalize_folder_token(child) == desired_normalized]
    if len(matches) == 1:
        return matches[0]
    return None


def find_unique_descendant_by_basename(vault_dir: str, desired_segment: str) -> str | None:
    desired_normalized = normalize_folder_token(desired_segment)
    matches = []

    for root, dirs, _ in os.walk(vault_dir):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        for directory in dirs:
            if normalize_folder_token(directory) == desired_normalized:
                rel_path = os.path.relpath(os.path.join(root, directory), vault_dir).replace("\\", "/")
                matches.append(rel_path)

    if len(matches) == 1:
        return matches[0]
    return None


def resolve_folder_path(vault_dir: str, folder_path: str) -> tuple[str, str]:
    clean_path = folder_path.replace("\\", "/").strip("/")
    if not clean_path:
        return "", vault_dir

    segments = [segment for segment in clean_path.split("/") if segment and segment != "."]
    resolved_segments: list[str] = []
    current_dir = vault_dir
    index = 0

    while index < len(segments):
        desired_segment = segments[index]
        matched_child = match_existing_child(current_dir, desired_segment)
        if matched_child:
            resolved_segments.append(matched_child)
            current_dir = os.path.join(current_dir, matched_child)
            index += 1
            continue

        if index == 0:
            deep_match = find_unique_descendant_by_basename(vault_dir, desired_segment)
            if deep_match:
                deep_segments = deep_match.split("/")
                resolved_segments = deep_segments.copy()
                current_dir = os.path.join(vault_dir, *deep_segments)
                index += 1
                continue

        resolved_segments.extend(segments[index:])
        break

    resolved_rel_path = "/".join(resolved_segments)
    resolved_full_path = os.path.join(vault_dir, *resolved_segments) if resolved_segments else vault_dir
    return resolved_rel_path, resolved_full_path


def resolve_file_path(vault_dir: str, filename: str, default_extension: str | None = None) -> tuple[str, str]:
    normalized_filename = filename.replace("\\", "/").lstrip("/")
    parent_rel = os.path.dirname(normalized_filename)
    base_name = os.path.basename(normalized_filename)

    resolved_parent_rel, resolved_parent_full = resolve_folder_path(vault_dir, parent_rel)
    resolved_full_path = os.path.join(resolved_parent_full, base_name)
    if default_extension and not resolved_full_path.lower().endswith(default_extension):
        resolved_full_path += default_extension

    resolved_rel_path = os.path.relpath(resolved_full_path, vault_dir).replace("\\", "/")
    return resolved_rel_path, resolved_full_path
