"""Filesystem storage adapter (raw JSON only in Plan 1)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from expdeploy.storage.base import RunRecord, SaveResult

_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")


class FSAdapter:
    """Saves raw run JSON to a BIDS-shaped filename under data_dir/raw/."""

    name = "fs"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).resolve()

    @staticmethod
    def _validate(field: str, value: str | None) -> None:
        if value is not None and not _LABEL_RE.match(value):
            msg = f"{field} {value!r} must match {_LABEL_RE.pattern}"
            raise ValueError(msg)

    @classmethod
    def _make_filename(
        cls,
        *,
        exp_id: str,
        subject_id: str,
        session_num: str | None,
        run_num: str | None,
    ) -> str:
        cls._validate("exp_id", exp_id)
        cls._validate("subject_id", subject_id)
        cls._validate("session_num", session_num)
        cls._validate("run_num", run_num)
        parts = [f"sub-{subject_id}"]
        if session_num is not None:
            parts.append(f"ses-{session_num}")
        parts.append(f"task-{exp_id}")
        if run_num is not None:
            parts.append(f"run-{run_num}")
        return "_".join(parts) + "_beh.json"

    def save(self, record: RunRecord) -> SaveResult:
        try:
            filename = self._make_filename(
                exp_id=record.exp_id,
                subject_id=record.subject_id,
                session_num=record.session_num,
                run_num=record.run_num,
            )
            subject_dir = self.data_dir / "raw" / f"sub-{record.subject_id}"
            if record.session_num is not None:
                subject_dir = subject_dir / f"ses-{record.session_num}"
            subject_dir.mkdir(parents=True, exist_ok=True)
            path = subject_dir / filename
            payload = {
                "saved_at_utc": datetime.now(UTC).isoformat(),
                **record.raw_payload,
            }
            # Atomic write
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            tmp.replace(path)
        except Exception as exc:
            return SaveResult(ok=False, path="", error=str(exc))
        return SaveResult(ok=True, path=str(path))
