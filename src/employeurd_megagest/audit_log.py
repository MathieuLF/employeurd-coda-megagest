from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_log_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "EmployeurD-MegaGest" / "logs"
    return Path.home() / ".employeurd-megagest" / "logs"


def write_audit_event(event: str, *, status: str, details: dict[str, Any] | None = None, log_dir: Path | None = None) -> Path:
    directory = log_dir or default_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
    payload = {
        "event": event,
        "status": status,
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "details": _sanitize(details or {}),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
    return path


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items() if "path" not in str(key).lower()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return value.name
    return value
