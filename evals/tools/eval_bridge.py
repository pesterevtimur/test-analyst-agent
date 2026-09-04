"""Мост между прогоном на хосте и состоянием внутри контейнера.

Прогон запускает агента через CLI OpenClaw, который живёт на хосте, а очередь
предложений, журнал и результаты лежат в томе docker. Питона с зависимостями на
хосте нет и не будет: сервер намеренно живёт в контейнере.

Поэтому мост. Хостовый скрипт зовёт его командой docker run, мост отвечает
JSON-ом и ничего не решает сам.

Команды:
    pending  --user <id>                кто ждёт подтверждения
    approve  --id <id> --by <кто>       подтвердить, как это сделал бы аналитик
    since    --at <isotime>             журнал, предложения и результаты после момента
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/app/src")

from sap_agent_mcp.store import (  # noqa: E402
    JournalEntry,
    Proposal,
    ProposalStatus,
    Result,
    Store,
)
from sqlalchemy import select  # noqa: E402


def store() -> Store:
    return Store(Path(os.environ.get("STATE_PATH", "/state/sap-agent.db")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["pending", "approve", "since"])
    parser.add_argument("--user", default=None)
    parser.add_argument("--id", default=None)
    parser.add_argument("--by", default="eval-runner")
    parser.add_argument("--at", default=None)
    args = parser.parse_args()

    state = store()

    if args.command == "pending":
        rows = [
            {"id": p.id, "user_id": p.user_id, "question": p.question,
             "policy_reason": p.policy_reason}
            for p in state.pending()
            if args.user is None or p.user_id == args.user
        ]
        print(json.dumps(rows, ensure_ascii=False))
        return 0

    if args.command == "approve":
        # Подтверждение аналитика, сымитированное прогоном. Имя подтверждающего
        # честное: в журнале останется eval-runner, а не живой человек.
        proposal = state.decide(
            args.id, status=ProposalStatus.APPROVED, by=args.by,
            note="автоподтверждение эталонного прогона",
        )
        state.record(
            user_id=args.by, tool="panel", outcome="approved",
            proposal_id=proposal.id, note="эталонный прогон",
        )
        print(json.dumps({"id": proposal.id, "status": proposal.status}))
        return 0

    since = datetime.fromisoformat(args.at)
    with state.session() as session:
        journal = [
            {
                "at": e.at.isoformat(),
                "user_id": e.user_id,
                "tool": e.tool,
                "outcome": e.outcome,
                "proposal_id": e.proposal_id,
                "duration_ms": e.duration_ms,
                "detail": e.detail,
            }
            for e in session.scalars(
                select(JournalEntry).where(JournalEntry.at >= since)
                .order_by(JournalEntry.at)
            )
        ]
        proposals = [
            {
                "id": p.id, "question": p.question, "sql": p.sql, "status": p.status,
                "checks": p.checks, "tables": p.tables,
                "estimated_rows": p.estimated_rows,
                "data_as_of": p.data_as_of,
                "policy_reason": p.policy_reason,
                "created_at": p.created_at.isoformat(),
            }
            for p in session.scalars(
                select(Proposal).where(Proposal.created_at >= since)
                .order_by(Proposal.created_at)
            )
        ]
        ids = {p["id"] for p in proposals}
        results = [
            {
                "id": r.id, "proposal_id": r.proposal_id, "columns": r.columns,
                "rows": r.rows, "row_count": r.row_count,
                "truncated": bool(r.truncated), "duration_ms": r.duration_ms,
            }
            for r in session.scalars(select(Result).where(Result.proposal_id.in_(ids)))
        ]

    print(json.dumps(
        {"journal": journal, "proposals": proposals, "results": results},
        ensure_ascii=False, default=str,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
