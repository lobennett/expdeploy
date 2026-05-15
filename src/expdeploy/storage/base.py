"""Storage adapter protocol and common types."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")

RunStatus = Literal["started", "finished", "aborted", "declined"]


def _new_run_id() -> str:
    return str(ULID())


class RunRecord(BaseModel):
    """One completed experiment run; what an adapter saves."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=_new_run_id, max_length=64)
    exp_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)
    exp_version: str | None = None
    subject_id: str = Field(pattern=r"^[a-zA-Z0-9-]+$", max_length=64)
    session_num: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9-]+$", max_length=32)
    run_num: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9-]+$", max_length=32)
    battery_id: str | None = Field(default=None, max_length=64)
    group_index: int | None = Field(default=None, ge=0)
    started_at: datetime
    ended_at: datetime
    status: RunStatus
    trials: list[dict[str, Any]] = Field(default_factory=list)
    interaction_data: list[dict[str, Any]] = Field(default_factory=list)
    jspsych_version: str | None = None
    deploy_version: str | None = None
    client_user_agent: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SaveResult:
    ok: bool
    path: str
    error: str | None = None


@runtime_checkable
class StorageAdapter(Protocol):
    name: str

    def save(self, record: RunRecord) -> SaveResult: ...
