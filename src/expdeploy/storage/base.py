"""Storage adapter protocol and common types."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")


def _validate_label(value: str, *, field: str) -> str:
    if not _LABEL_RE.match(value):
        msg = f"{field} {value!r} must match {_LABEL_RE.pattern}"
        raise ValueError(msg)
    return value


class RunRecord(BaseModel):
    """One completed experiment run; what an adapter saves."""

    model_config = ConfigDict(extra="forbid")

    exp_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)
    subject_id: str = Field(pattern=r"^[a-zA-Z0-9-]+$", max_length=64)
    session_num: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9-]+$", max_length=32)
    run_num: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9-]+$", max_length=32)
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
