"""Counterbalance strategies — 4 implementations of CounterbalanceStrategy."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class CounterbalanceStrategy(Protocol):
    name: str

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]: ...


class FixedStrategy:
    name = "fixed"

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        return list(experiments)


class LatinSquareStrategy:
    """Balanced KxK Latin square; subject row = int(subject_id) mod K."""

    name = "latin_square"

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        try:
            n = int(subject_id)
        except ValueError as exc:
            msg = f"latin_square requires integer-parseable subject_id; got {subject_id!r}"
            raise ValueError(msg) from exc
        k = len(experiments)
        row = n % k
        # Williams-style Latin square: position j of row i = (i + j) mod K
        return [experiments[(row + j) % k] for j in range(k)]


class SeededRandomStrategy:
    """Per-subject deterministic shuffle. Seed derived from subject_id."""

    name = "seeded_random"

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        rng = random.Random(subject_id)
        out = list(experiments)
        rng.shuffle(out)
        return out


class UserSuppliedStrategy:
    """Reads order_csv; rows are subject_id, pos_1, pos_2, ..."""

    name = "user_supplied"

    def __init__(self, order_csv: Path) -> None:
        self.order_csv = Path(order_csv)
        self._cache: dict[str, list[str]] | None = None

    def _load(self) -> dict[str, list[str]]:
        if self._cache is not None:
            return self._cache
        out: dict[str, list[str]] = {}
        with self.order_csv.open() as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None or len(header) < 2:
                msg = f"order_csv {self.order_csv} missing header / columns"
                raise ValueError(msg)
            for row in reader:
                if not row:
                    continue
                subject = row[0]
                out[subject] = [c for c in row[1:] if c]
        self._cache = out
        return out

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        loaded = self._load()
        if subject_id not in loaded:
            msg = f"subject_id {subject_id!r} not in {self.order_csv}"
            raise KeyError(msg)
        return loaded[subject_id]
