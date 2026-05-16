"""File-locked per-subject run session state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TypedDict, cast

from filelock import FileLock


class _State(TypedDict):
    subject_id: str
    battery_id: str
    order: list[str]
    completed: list[str]


class RunSession:
    """Tracks one subject's progress through a battery.

    State is persisted to `state_dir/sub-<subject_id>.json` and protected by
    a file lock so concurrent web requests can't race.
    """

    def __init__(self, state_dir: Path, subject_id: str) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.subject_id = subject_id
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.state_dir / f"sub-{subject_id}.json"
        self._lock = FileLock(str(self._path) + ".lock")

    def _read(self) -> _State | None:
        if not self._path.exists():
            return None
        return cast(_State, json.loads(self._path.read_text()))

    def _write(self, state: _State) -> None:
        fd, tmpname = tempfile.mkstemp(prefix=f"sub-{self.subject_id}-", dir=str(self.state_dir))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2, sort_keys=True)
            os.replace(tmpname, self._path)
        except Exception:
            if os.path.exists(tmpname):
                os.unlink(tmpname)
            raise

    def initialize(self, *, battery_id: str, order: list[str]) -> None:
        """Create state if missing, or preserve if same battery_id; reset otherwise."""
        with self._lock:
            existing = self._read()
            if existing is not None and existing.get("battery_id") == battery_id:
                return  # preserve progress
            state: _State = {
                "subject_id": self.subject_id,
                "battery_id": battery_id,
                "order": list(order),
                "completed": [],
            }
            self._write(state)

    def current(self) -> str | None:
        with self._lock:
            state = self._read()
            if state is None:
                msg = f"session not initialized for sub-{self.subject_id}"
                raise RuntimeError(msg)
            remaining = [e for e in state["order"] if e not in state["completed"]]
            return remaining[0] if remaining else None

    def advance(self) -> None:
        with self._lock:
            state = self._read()
            if state is None:
                msg = f"session not initialized for sub-{self.subject_id}"
                raise RuntimeError(msg)
            remaining = [e for e in state["order"] if e not in state["completed"]]
            if not remaining:
                return
            state["completed"].append(remaining[0])
            self._write(state)

    def completed(self) -> list[str]:
        with self._lock:
            state = self._read()
            if state is None:
                return []
            return list(state["completed"])

    def reset(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()
