import re


REQUEST_MARKERS = (
    "Requested task:",
    "Requested Task:",
    "Tarea solicitada:",
)

SPANISH_HINTS = (
    "que",
    "para",
    "con",
    "sin",
    "pero",
    "porque",
    "como",
    "esto",
    "esta",
    "estas",
    "estos",
    "una",
    "uno",
    "y",
    "o",
    "de",
    "del",
    "el",
    "la",
    "los",
    "las",
    "por",
    "haz",
    "agrega",
    "elimina",
    "mejora",
    "cambia",
)

ENGLISH_HINTS = (
    "the",
    "and",
    "or",
    "with",
    "without",
    "please",
    "make",
    "add",
    "remove",
    "improve",
    "change",
    "build",
)


def extract_original_user_request(prompt: str) -> str:
    if not prompt:
        return ""

    for marker in REQUEST_MARKERS:
        if marker in prompt:
            return prompt.split(marker, 1)[1].strip()
    return prompt.strip()


def detect_user_language(text: str) -> str:
    if not text:
        return "en"

    lowered = text.lower()
    if re.search(r"[\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00bf\u00a1]", lowered):
        return "es"

    spanish_hits = sum(1 for word in SPANISH_HINTS if re.search(rf"\b{re.escape(word)}\b", lowered))
    english_hits = sum(1 for word in ENGLISH_HINTS if re.search(rf"\b{re.escape(word)}\b", lowered))
    return "es" if spanish_hits >= english_hits + 1 else "en"


def get_language_name(language_code: str) -> str:
    return "Spanish" if language_code == "es" else "English"


def build_manager_language_policy(original_user_request: str) -> str:
    language_code = detect_user_language(original_user_request)
    language_name = get_language_name(language_code)
    return (
        "Internal coordination language: English.\n"
        f"User-facing language: {language_name}. "
        f"If next_agent is \"User\", write the instruction in {language_name}.\n"
    )


def with_language_context(instruction: str, original_user_request: str) -> str:
    if not original_user_request:
        return instruction

    language_name = get_language_name(detect_user_language(original_user_request))
    return (
        f"{instruction}\n\n"
        "=== OUTPUT LANGUAGE ===\n"
        f"- Write ALL user-facing content in {language_name}.\n"
        "- Only switch languages if the user explicitly asks for another one.\n\n"
        "=== LANGUAGE REFERENCE ===\n"
        "Match the language of the ORIGINAL USER REQUEST for all user-facing content and all generated file contents.\n"
        "Only switch languages if the user explicitly asks for another one.\n"
        f"ORIGINAL USER REQUEST:\n{original_user_request}\n"
    )
