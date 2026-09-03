"""The reference-set screen: read the questions, read the last report, nominate.

The set is files in git (ADR-011), so the panel reads them rather than a table,
and it never writes into the set itself. An approved pair goes to
`evals/candidates/` as a draft with everything the question needs except the
judgement of whether it belongs. That judgement is a commit by a person.

A set that grew by itself from what the agent already answered correctly would
raise its own score every week and measure nothing.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def repository() -> Path:
    return Path(os.environ.get("REPO_ROOT", "/repo"))


def load_questions() -> list[dict[str, Any]]:
    root = repository() / "evals" / "dataset"
    questions: list[dict[str, Any]] = []
    for subset in ("open", "sealed"):
        for path in sorted((root / subset).glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            questions.append(
                {
                    "id": data["id"],
                    "subset": subset,
                    "question": data["question"],
                    "difficulty": data["difficulty"],
                    "kind": data["kind"],
                    # A sealed question is listed by id and class only. Reading
                    # them while building is exactly what the seal prevents.
                    "hidden": subset == "sealed",
                }
            )
    return questions


def last_report() -> dict[str, Any] | None:
    reports = sorted((repository() / "evals" / "reports").glob("*.json"))
    if not reports:
        return None
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    data["file"] = reports[-1].name
    return data


def nominate(proposal, *, by: str) -> Path:
    """Write an approved pair out as a draft question."""
    directory = repository() / "evals" / "candidates"
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", proposal.question.lower())[:40].strip("-") or "question"
    path = directory / f"{proposal.id}-{slug}.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": f"candidate-{proposal.id}",
                "question": proposal.question,
                "asked_by": proposal.user_id,
                "difficulty": "medium",
                "kind": "answerable",
                "gold_sql": proposal.sql,
                "expect": {"key_columns": [], "measure_columns": []},
                "notes": (
                    f"Кандидат из подтверждённой пары. Предложил {proposal.user_id}, "
                    f"подтвердил {proposal.decided_by or 'политика'}, "
                    f"выдвинул {by} {datetime.now(UTC).date().isoformat()}. "
                    "Перед включением в набор: назвать класс сложности, ключевые "
                    "колонки и меры, заморозить эталонный ответ."
                ),
            },
            allow_unicode=True, sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path
