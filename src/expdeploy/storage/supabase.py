"""Supabase storage adapter — Postgres table + storage bucket. Optional install."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from expdeploy.storage.base import RunRecord, SaveResult

if TYPE_CHECKING:
    from supabase import Client


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

    def save(self, record: RunRecord) -> SaveResult:
        # Stubbed; full impl in Task 6.
        return SaveResult(ok=False, path="", error="not yet implemented")
