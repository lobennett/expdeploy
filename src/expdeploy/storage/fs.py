"""Filesystem storage adapter — raw JSON always; BIDS layout when manifest declares it."""

from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from filelock import FileLock

from expdeploy.manifest import BidsConfig, ExperimentManifest
from expdeploy.storage.base import RunRecord, SaveResult

_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")
BIDS_VERSION = "1.9.0"


class FSAdapter:
    """Saves raw run JSON to disk; optionally writes a BIDS-flavored mirror."""

    name = "fs"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).resolve()

    # ---- raw JSON write (unchanged from Plan 1) -------------------------------

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
        suffix: str = "_beh",
        ext: str = ".json",
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
        return "_".join(parts) + suffix + ext

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
                **record.model_dump(mode="json"),
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            tmp.replace(path)
        except Exception as exc:
            return SaveResult(ok=False, path="", error=str(exc))
        return SaveResult(ok=True, path=str(path))

    # ---- BIDS layout writes ---------------------------------------------------

    def save_bids(self, record: RunRecord, manifest: ExperimentManifest) -> SaveResult:
        if manifest.bids is None:
            return SaveResult(ok=False, path="", error="manifest has no [bids] block")
        try:
            bids_root = self.data_dir / "bids"
            bids_root.mkdir(parents=True, exist_ok=True)
            self._ensure_dataset_description(bids_root, manifest)
            self._append_participant(bids_root, record.subject_id)
            events_path = self._write_events_tsv(bids_root, record, manifest.bids)
            self._write_events_sidecar(bids_root, record, manifest.bids)
        except Exception as exc:
            return SaveResult(ok=False, path="", error=str(exc))
        return SaveResult(ok=True, path=str(events_path))

    def _ensure_dataset_description(self, bids_root: Path, manifest: ExperimentManifest) -> None:
        path = bids_root / "dataset_description.json"
        if path.exists():
            return
        dd = {
            "Name": manifest.experiment.name,
            "BIDSVersion": BIDS_VERSION,
            "DatasetType": "raw",
            "Authors": list(manifest.experiment.metadata.contributors),
        }
        path.write_text(json.dumps(dd, indent=2, sort_keys=True) + "\n")

    def _append_participant(self, bids_root: Path, subject_id: str) -> None:
        path = bids_root / "participants.tsv"
        lock = FileLock(str(path) + ".lock")
        participant = f"sub-{subject_id}"
        with lock:
            existing: list[str] = []
            if path.exists():
                existing = path.read_text().splitlines()
            header_present = bool(existing) and existing[0].startswith("participant_id")
            rows_existing = set(existing[1:]) if header_present else set(existing)
            if participant in rows_existing:
                return
            with path.open("a") as f:
                if not header_present:
                    f.write("participant_id\n")
                f.write(participant + "\n")

    def _events_dir_for(self, bids_root: Path, record: RunRecord, bids: BidsConfig) -> Path:
        subject_dir = bids_root / f"sub-{record.subject_id}"
        if record.session_num is not None:
            subject_dir = subject_dir / f"ses-{record.session_num}"
        modality = "func" if bids.type == "fmri" else "beh"
        events_dir = subject_dir / modality
        events_dir.mkdir(parents=True, exist_ok=True)
        return events_dir

    def _write_events_tsv(self, bids_root: Path, record: RunRecord, bids: BidsConfig) -> Path:
        events_dir = self._events_dir_for(bids_root, record, bids)
        suffix = "_events" if bids.type == "fmri" else "_beh"
        ext = ".tsv"
        filename = self._make_filename(
            exp_id=record.exp_id,
            subject_id=record.subject_id,
            session_num=record.session_num,
            run_num=record.run_num,
            suffix=suffix,
            ext=ext,
        )
        path = events_dir / filename

        # BIDS-mandated columns first; remaining trial columns appended
        bids_cols = ["onset", "duration", "trial_type"]
        all_cols: list[str] = list(bids_cols)
        for trial in record.trials:
            for k in trial:
                if k not in all_cols:
                    all_cols.append(k)

        buf = StringIO()
        writer = csv.DictWriter(buf, fieldnames=all_cols, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for trial in record.trials:
            row = {col: trial.get(col, "n/a") for col in all_cols}
            writer.writerow(row)
        path.write_text(buf.getvalue())
        return path

    def _write_events_sidecar(self, bids_root: Path, record: RunRecord, bids: BidsConfig) -> None:
        if not bids.columns:
            return
        events_dir = self._events_dir_for(bids_root, record, bids)
        suffix = "_events" if bids.type == "fmri" else "_beh"
        filename = self._make_filename(
            exp_id=record.exp_id,
            subject_id=record.subject_id,
            session_num=record.session_num,
            run_num=None,  # sidecar is per-task, not per-run
            suffix=suffix,
            ext=".json",
        )
        path = events_dir / filename
        if path.exists():
            return  # sidecar is task-level; first writer wins
        sidecar: dict[str, Any] = {}
        for col_name, col in bids.columns.items():
            sidecar[col_name] = {
                "description": col.description,
            }
            if col.levels:
                sidecar[col_name]["Levels"] = dict(col.levels)
        path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n")
