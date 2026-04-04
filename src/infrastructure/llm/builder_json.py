import json
import re
from typing import Any, Dict, List


def _sanitize_multiline_json_strings(payload: str) -> str:
    """
    Gemini sometimes produces "JSON-looking" output with literal newlines inside quoted strings.
    That is invalid JSON (control characters). This function escapes control chars while inside strings
    so json.loads() can parse it.
    """
    out: List[str] = []
    in_string = False
    escaped = False

    for ch in payload:
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            continue

        # In string:
        if escaped:
            out.append(ch)
            escaped = False
            continue

        if ch == "\\":
            out.append(ch)
            escaped = True
            continue

        if ch == '"':
            out.append(ch)
            in_string = False
            continue

        o = ord(ch)
        if ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20:
            out.append(f"\\u{o:04x}")
        else:
            out.append(ch)

    return "".join(out)


def parse_builder_files_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract and parse a ```json ...``` block that contains a list of {file_path, content}.
    Returns a list of dicts. If no block is found or parsing fails, returns [].
    """
    start = text.find("```json")
    if start == -1:
        return []
    # The Builder's JSON often embeds Markdown code fences (```mermaid, ```),
    # so we cannot stop at the first triple-backtick after ```json.
    # Instead, take everything until the LAST ``` in the message.
    end = text.rfind("```")
    if end == -1 or end <= start:
        return []

    payload = text[start + len("```json") : end].strip()
    if not payload:
        return []

    # 1) Try strict JSON (and a newline-sanitized version).
    obj = None
    try:
        obj = json.loads(payload)
    except Exception:
        try:
            fixed = _sanitize_multiline_json_strings(payload)
            obj = json.loads(fixed)
        except Exception:
            obj = None

    if obj is not None:
        if isinstance(obj, dict) and isinstance(obj.get("files"), list):
            files_any = obj["files"]
        elif isinstance(obj, list):
            files_any = obj
        else:
            files_any = None

        if isinstance(files_any, list):
            normalized: List[Dict[str, Any]] = []
            for item in files_any:
                if not isinstance(item, dict):
                    continue
                path = item.get("file_path") or item.get("path") or item.get("filepath")
                content = item.get("content")
                if isinstance(path, str) and isinstance(content, str):
                    normalized.append({"file_path": path, "content": content})
            if normalized:
                return normalized

    # 2) Loose parser fallback:
    # Gemini sometimes outputs JSON-looking data with unescaped quotes/backticks inside content.
    # We'll extract objects by structure markers instead of json.loads().
    starts = [m.start() for m in re.finditer(r"\{\s*\n\s*\"file_path\"\s*:\s*\"", payload)]
    if not starts:
        # Alternate: sometimes the first object is not preceded by a newline.
        starts = [m.start() for m in re.finditer(r"\{\s*\"file_path\"\s*:\s*\"", payload)]
    if not starts:
        return []

    # Ensure we don't include trailing closing bracket noise as an "object".
    ends = starts[1:] + [len(payload)]
    extracted: List[Dict[str, Any]] = []

    for s, e in zip(starts, ends):
        obj_str = payload[s:e].strip()

        m_path = re.search(r"\"file_path\"\s*:\s*\"([^\"]+)\"", obj_str)
        if not m_path:
            continue
        file_path = m_path.group(1)

        key = "\"content\": \""
        i = obj_str.find(key)
        if i == -1:
            continue
        content_start = i + len(key)

        # Content ends at the quote right before the object closes: "\n  }" or "\n  },"
        m_end = re.search(r"\"\s*\n\s*\}\s*,?\s*$", obj_str, re.S)
        if not m_end:
            continue
        content_end = m_end.start()
        content = obj_str[content_start:content_end]

        extracted.append({"file_path": file_path, "content": content})

    return extracted
