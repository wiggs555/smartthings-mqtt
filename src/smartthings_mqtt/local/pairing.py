"""Token persistence for local TV pairing."""

from __future__ import annotations

import json
from pathlib import Path


def token_path(token_dir: Path, device_id: str) -> Path:
    """Path to token file for a SmartThings device ID."""
    safe_id = device_id.replace("/", "_")
    return token_dir / f"{safe_id}.json"


def load_token(token_dir: Path, device_id: str) -> str | None:
    """Load saved WebSocket token if present."""
    path = token_path(token_dir, device_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("token")
    except (json.JSONDecodeError, OSError):
        return None


def save_token(token_dir: Path, device_id: str, token: str) -> None:
    """Persist WebSocket token after TV pairing."""
    token_dir.mkdir(parents=True, exist_ok=True)
    path = token_path(token_dir, device_id)
    path.write_text(json.dumps({"token": token}), encoding="utf-8")
