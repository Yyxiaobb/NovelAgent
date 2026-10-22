"""Privacy-conscious timing logs for model-backed generation requests."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


_logger = logging.getLogger("app.generation")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _logger.addHandler(handler)
_logger.propagate = False
_write_lock = Lock()


def _telemetry_file() -> Path:
    configured = os.getenv("GENERATION_TELEMETRY_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "novel-agent-generation.jsonl"


def _safe_metric(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return type(value).__name__


def log_generation_metric(event: str, task: str, duration_ms: float, **metrics: object) -> None:
    """Emit numeric generation diagnostics without prompts, output text, or user identifiers."""
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "task": task,
        "duration_ms": round(duration_ms, 2),
        **{key: _safe_metric(value) for key, value in metrics.items()},
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _logger.info("generation_telemetry %s", serialized)
    try:
        target = _telemetry_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            with target.open("a", encoding="utf-8") as stream:
                stream.write(serialized)
                stream.write("\n")
    except OSError as error:
        # Observability must never make a generation request fail.
        _logger.warning("generation telemetry file unavailable: %s", error)
