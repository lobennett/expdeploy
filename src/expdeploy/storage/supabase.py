"""Supabase storage adapter — Postgres table + storage bucket. Optional install."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from expdeploy.storage.base import RunRecord, SaveResult

if TYPE_CHECKING:
    from supabase import Client

_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")


def _make_storage_path(record: RunRecord) -> str:
    parts = [f"sub-{record.subject_id}"]
    if record.session_num is not None:
        parts.append(f"ses-{record.session_num}")
    fname = parts[:]
    fname.append(f"task-{record.exp_id}")
    if record.run_num is not None:
        fname.append(f"run-{record.run_num}")
    filename = "_".join(fname) + "_beh.json"
    return "/".join(parts) + "/" + filename


@dataclass(frozen=True, slots=True)
class SupabaseConfig:
    url: str
    service_role_key: str
    schema: str = "expdeploy"
    bucket: str = "expdeploy-raw"

    @classmethod
    def from_env(cls) -> SupabaseConfig:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            msg = "Supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars."
            raise RuntimeError(msg)
        schema = os.environ.get("SUPABASE_SCHEMA", "expdeploy")
        bucket = os.environ.get("SUPABASE_BUCKET", "expdeploy-raw")
        return cls(url=url, service_role_key=key, schema=schema, bucket=bucket)


class SupabaseAdapter:
    """Mirrors runs to a Supabase Postgres table + storage bucket."""

    name = "supabase"

    def __init__(self, config: SupabaseConfig) -> None:
        self.config = config
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            from supabase import create_client

            self._client = create_client(self.config.url, self.config.service_role_key)
        return self._client

    def apply_migrations(self) -> None:
        """Apply idempotent DDL via the Postgres-meta REST endpoint (psql-like)."""
        schema_path = Path(__file__).resolve().parent / "supabase_schema.sql"
        sql = schema_path.read_text()
        client = self._get_client()
        # Supabase client's `postgrest` doesn't expose raw SQL; use the RPC `exec_sql` if
        # the project has it, otherwise instruct the user to apply via SQL editor.
        try:
            client.postgrest.rpc("exec_sql", {"sql": sql}).execute()
        except Exception as exc:
            # Fallback: print SQL for manual application
            msg = (
                f"Could not apply DDL automatically ({exc}). "
                f"Run the SQL at {schema_path} via the Supabase SQL editor."
            )
            raise RuntimeError(msg) from exc

    def save(self, record: RunRecord) -> SaveResult:
        try:
            client = self._get_client()
            row = record.model_dump(mode="json")
            # Drop fields that don't have Postgres columns; trials/interaction become JSONB
            row["trials_json"] = row.pop("trials")
            row["interaction_data_json"] = row.pop("interaction_data")
            row.pop("raw_payload", None)  # raw bucket upload carries the payload
            client.schema(self.config.schema).table("runs").upsert(row).execute()

            storage_path = _make_storage_path(record)
            body = json.dumps(record.model_dump(mode="json"), sort_keys=True).encode("utf-8")
            client.storage.from_(self.config.bucket).upload(
                path=storage_path,
                file=body,
                file_options={"content-type": "application/json", "upsert": "true"},
            )
            remote_uri = f"{self.config.url}/storage/v1/object/{self.config.bucket}/{storage_path}"
        except Exception as exc:
            return SaveResult(ok=False, path="", error=str(exc))
        return SaveResult(ok=True, path=remote_uri)
