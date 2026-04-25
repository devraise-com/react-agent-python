"""Simple file-based JSON persistence for mock services."""

import json
import threading
from pathlib import Path
from typing import Any, Callable


class JsonStore:
    """Read/write a JSON file with a lock for safety."""

    def __init__(self, path: Path, defaults: dict[str, Any]) -> None:
        self._path = path
        self._lock = threading.Lock()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_locked(defaults)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self) -> dict[str, Any]:
        with self._lock:
            return self._read_locked()

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._write_locked(data)

    def update(self, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        """Read → transform → write atomically; returns the new state."""
        with self._lock:
            data = self._read_locked()
            data = fn(data)
            self._write_locked(data)
        return data

    # ------------------------------------------------------------------
    # Internal helpers (must be called with lock held)
    # ------------------------------------------------------------------

    def _read_locked(self) -> dict[str, Any]:
        with open(self._path, encoding="utf-8") as f:
            result: dict[str, Any] = json.load(f)
            return result

    def _write_locked(self, data: dict[str, Any]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
