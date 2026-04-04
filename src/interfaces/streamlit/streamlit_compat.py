import sys


def apply_streamlit_shutdown_patch() -> None:
    """
    Evita un traceback ruidoso al cerrar Streamlit con Ctrl+C en Windows
    cuando el event loop ya fue cerrado durante el apagado.
    """
    if sys.platform != "win32":
        return

    try:
        from streamlit.runtime.runtime import Runtime
    except Exception:
        return

    original_stop = getattr(Runtime, "stop", None)
    if original_stop is None or getattr(original_stop, "_ai_team_safe_stop", False):
        return

    def safe_stop(self) -> None:
        try:
            original_stop(self)
        except RuntimeError as exc:
            if "Event loop is closed" not in str(exc):
                raise

    safe_stop._ai_team_safe_stop = True
    Runtime.stop = safe_stop
