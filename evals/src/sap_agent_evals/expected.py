"""Frozen results of the gold SQL.

The gold answer is what the gold SQL returned against the reporting replica at a
named moment, stored as data rather than recomputed on every run. Two reasons.
A comparison run must not depend on the database being up. And a change in the
numbers has to be visible as a diff: if the replica is refreshed and revenue for
2021 moves, that shows up here as a changed file and gets looked at, instead of
quietly becoming the new truth.

The sha of the gold SQL is stored next to the numbers. Edit the query and the
frozen answer stops matching it, which is exactly when it should be re-frozen.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .compare import Table


def sql_fingerprint(sql: str) -> str:
    """Whitespace-insensitive, so reformatting the query is not a change."""
    normalized = " ".join(sql.split()).upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class FrozenResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    sql_fingerprint: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    frozen_at: str
    data_as_of: str | None = None
    duration_ms: int | None = None

    @classmethod
    def build(
        cls,
        *,
        question_id: str,
        sql: str,
        columns: list[str],
        rows: list[list[Any]],
        data_as_of: str | None = None,
        duration_ms: int | None = None,
    ) -> FrozenResult:
        return cls(
            question_id=question_id,
            sql_fingerprint=sql_fingerprint(sql),
            columns=[c.upper() for c in columns],
            rows=[list(row) for row in rows],
            row_count=len(rows),
            frozen_at=datetime.now(UTC).isoformat(timespec="seconds"),
            data_as_of=data_as_of,
            duration_ms=duration_ms,
        )

    def as_table(self) -> Table:
        return Table.of(self.columns, self.rows)

    def matches(self, sql: str) -> bool:
        return self.sql_fingerprint == sql_fingerprint(sql)


def default_root() -> Path:
    return Path(__file__).resolve().parents[2] / "expected"


def path_for(question_id: str, root: Path | None = None) -> Path:
    return (root or default_root()) / f"{question_id}.json"


def save(result: FrozenResult, root: Path | None = None) -> Path:
    path = path_for(result.question_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def load(question_id: str, root: Path | None = None) -> FrozenResult:
    path = path_for(question_id, root)
    return FrozenResult.model_validate_json(path.read_text(encoding="utf-8"))


def exists(question_id: str, root: Path | None = None) -> bool:
    return path_for(question_id, root).is_file()
