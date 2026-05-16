"""SQLite catalog adapter — always-on local index of runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from expdeploy.storage.base import RunRecord, SaveResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  exp_id TEXT NOT NULL,
  exp_version TEXT,
  subject_id TEXT NOT NULL,
  session_num TEXT,
  run_num TEXT,
  battery_id TEXT,
  group_index INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  trials_json TEXT,
  interaction_data_json TEXT,
  jspsych_version TEXT,
  deploy_version TEXT,
  client_user_agent TEXT
);

CREATE TABLE IF NOT EXISTS batteries (
  battery_id TEXT PRIMARY KEY,
  name TEXT,
  manifest_hash TEXT,
  counterbalance TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS remote_sync (
  run_id TEXT REFERENCES runs(run_id),
  adapter TEXT NOT NULL,
  status TEXT NOT NULL,
  attempted_at TEXT,
  remote_uri TEXT,
  error TEXT,
  PRIMARY KEY (run_id, adapter)
);

CREATE INDEX IF NOT EXISTS idx_runs_subject ON runs(subject_id, session_num, run_num);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_remote_sync_status ON remote_sync(status, adapter);
"""


class SQLiteCatalog:
    name = "sqlite"

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def save(self, record: RunRecord) -> SaveResult:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO runs (
                        run_id, exp_id, exp_version, subject_id, session_num, run_num,
                        battery_id, group_index, started_at, ended_at, status,
                        trials_json, interaction_data_json,
                        jspsych_version, deploy_version, client_user_agent
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        status = excluded.status,
                        ended_at = excluded.ended_at,
                        trials_json = excluded.trials_json,
                        interaction_data_json = excluded.interaction_data_json
                    """,
                    (
                        record.run_id,
                        record.exp_id,
                        record.exp_version,
                        record.subject_id,
                        record.session_num,
                        record.run_num,
                        record.battery_id,
                        record.group_index,
                        record.started_at.isoformat(),
                        record.ended_at.isoformat(),
                        record.status,
                        json.dumps(record.trials),
                        json.dumps(record.interaction_data),
                        record.jspsych_version,
                        record.deploy_version,
                        record.client_user_agent,
                    ),
                )
        except Exception as exc:
            return SaveResult(ok=False, path=str(self.db_path), error=str(exc))
        return SaveResult(ok=True, path=str(self.db_path))

    def recent_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def runs_for_subject(self, subject_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE subject_id = ? ORDER BY started_at DESC",
                (subject_id,),
            ).fetchall()
        return [dict(r) for r in rows]
