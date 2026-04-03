class AppError(Exception):
    """Base class for app-level errors (expected, user-facing)."""


class ConfigError(AppError):
    """Raised when required configuration is missing or invalid."""


class GeminiError(AppError):
    """Raised for errors calling Gemini APIs."""


class GeminiBackendsExhausted(GeminiError):
    """Raised when all configured keys/models are rate-limited or unavailable."""


class GeminiRequestFailed(GeminiError):
    """Raised when a Gemini request fails in a non-retryable way."""

