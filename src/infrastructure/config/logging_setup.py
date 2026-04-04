import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.infrastructure.config.config import Settings


class _DefaultContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if not hasattr(record, "task_id"):
            record.task_id = "-"
        if not hasattr(record, "agent"):
            record.agent = "-"
        return True


def setup_logging(settings: Settings, task_id: str) -> Path:
    """
    Configure root logging for the current session.
    Returns the log file path.
    """
    log_dir = Path(settings.logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"task_{task_id}.log"

    level = getattr(logging, settings.log_level, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers when running multiple times in the same interpreter.
    root.handlers = []

    fmt = "%(asctime)s %(levelname)s [%(name)s] [task=%(task_id)s] [agent=%(agent)s] %(message)s"
    formatter = logging.Formatter(fmt)
    context_filter = _DefaultContextFilter()

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(formatter)
    sh.addFilter(context_filter)
    root.addHandler(sh)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(formatter)
    fh.addFilter(context_filter)
    root.addHandler(fh)

    return log_file


def get_task_logger(name: str, task_id: str, agent: str = "-") -> logging.LoggerAdapter:
    extra: Dict[str, Any] = {"task_id": task_id, "agent": agent}
    return logging.LoggerAdapter(logging.getLogger(name), extra)

