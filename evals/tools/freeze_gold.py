"""Run every gold query against the reporting replica and freeze what it returns.

This is the step that turns a written reference set into a measured one. Until
it runs, the gold SQL is an opinion: it parses, it passes the guard rails, and
it may still return nothing at all because a filter is spelled the way the
business says it rather than the way the column stores it.

Run (from the repository root, with the replica up):

    docker run --rm --network host --user "$(id -u):$(id -g)" \
        -v "$PWD:/w" -w /w \
        -e PYTHONPATH=/w/mcp_server/src:/w/evals/src \
        -e ORACLE_APP_USER -e ORACLE_APP_USER_PASSWORD \
        -e ORACLE_DSN=127.0.0.1:1521/REPPDB1 \
        sap-agent-mcp:dev python evals/tools/freeze_gold.py

Options:
    --only <id>       freeze one question
    --check           run nothing, only report which frozen answers are stale
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "mcp_server" / "src"), str(ROOT / "evals" / "src")]

from sap_agent_evals import expected as frozen  # noqa: E402
from sap_agent_evals.dataset import Kind, load_dataset  # noqa: E402
from sap_agent_mcp.db import Database  # noqa: E402
from sap_agent_mcp.guards import Guards  # noqa: E402
from sap_agent_mcp.semantic.loader import load  # noqa: E402

SEMANTIC = ROOT / "mcp_server" / "semantic" / "sap"
# The ceiling the server itself uses. A gold answer longer than this could never
# be reproduced through the agent, so freezing one would be a trap of our own.
MAX_ROWS = 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    dataset = load_dataset()
    questions = [q for q in dataset.questions if q.kind is Kind.ANSWERABLE]
    if args.only:
        questions = [q for q in questions if q.id == args.only]
        if not questions:
            print(f"нет такого вопроса: {args.only}")
            return 2

    if args.check:
        return _check(questions)

    guards = Guards(load([SEMANTIC]), max_rows=MAX_ROWS)
    database = Database(
        user=os.environ.get("ORACLE_APP_USER", "agent_ro"),
        password=os.environ["ORACLE_APP_USER_PASSWORD"],
        dsn=os.environ.get("ORACLE_DSN", "127.0.0.1:1521/REPPDB1"),
    )
    as_of = database.replica_as_of()
    print(f"реплика на {as_of}\n")

    failures: list[str] = []
    try:
        for question in questions:
            verdict = guards.check(question.gold_sql)
            if not verdict.ok:
                failures.append(
                    f"{question.id}: ограничители отклонили эталонный запрос: "
                    + "; ".join(f"{c.id} {c.detail}" for c in verdict.failures)
                )
                continue

            rows = database.run(
                verdict.sql, max_rows=MAX_ROWS, timeout_seconds=120
            )
            if rows.row_count == 0:
                # An empty gold answer is almost always a filter written in the
                # wrong spelling, and it would freeze as "the right answer is
                # nothing", which is the one wrong answer nobody notices.
                failures.append(
                    f"{question.id}: эталонный запрос вернул ноль строк. "
                    "Это почти всегда фильтр не в том формате, а не отсутствие данных."
                )
                continue
            if rows.truncated:
                failures.append(
                    f"{question.id}: результат обрезан по лимиту {MAX_ROWS} строк. "
                    "Эталон обязан помещаться в лимит, иначе агент его не повторит."
                )
                continue

            result = frozen.FrozenResult.build(
                question_id=question.id,
                sql=question.gold_sql,
                columns=rows.columns,
                rows=[[_plain(value) for value in row] for row in rows.rows],
                data_as_of=as_of,
                duration_ms=rows.duration_ms,
            )
            path = frozen.save(result)
            head = ", ".join(
                f"{c}={result.rows[0][i]}" for i, c in enumerate(result.columns[:3])
            )
            print(
                f"{question.id:<12} строк {result.row_count:>4}  "
                f"{rows.duration_ms:>5} мс  {head}"
            )
            print(f"             -> {path.relative_to(ROOT)}")
    finally:
        database.close()

    if failures:
        print("\nне заморожено:")
        for line in failures:
            print("  " + line)
        return 1

    print(f"\nзаморожено вопросов: {len(questions)}")
    return 0


def _check(questions) -> int:
    """Which frozen answers no longer match the query that produced them."""
    stale: list[str] = []
    missing: list[str] = []
    for question in questions:
        if not frozen.exists(question.id):
            missing.append(question.id)
            continue
        if not frozen.load(question.id).matches(question.gold_sql):
            stale.append(question.id)

    if missing:
        print("нет эталонного результата: " + ", ".join(missing))
    if stale:
        print("эталонный запрос изменился после заморозки: " + ", ".join(stale))
    if not missing and not stale:
        print(f"все {len(questions)} эталонных результатов свежие")
        return 0
    return 1


def _plain(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return float(value) if hasattr(value, "__float__") else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
