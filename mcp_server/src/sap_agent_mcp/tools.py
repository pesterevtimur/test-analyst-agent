"""The four tools the agent has. It has nothing else: no shell, no files, no web.

The chain is fixed and each link is narrow:

    describe_schema  ->  propose_query  ->  execute_query  ->  sanity_check

execute_query takes a proposal id and never SQL. That single fact is what makes
the guard rails unavoidable: accepting query text here would let one call skip
all six checks.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .config import Limits
from .db import Database, QueryRefused, QueryTimeout
from .guards import Guards, Verdict
from .sanity import SanityReport, check as sanity_check_rows
from .semantic.models import SemanticModel
from .store import Proposal, ProposalStatus, Result, Store, new_id


class ToolError(BaseModel):
    """A refusal the agent can act on.

    Errors come back as data rather than exceptions, and they say which check
    failed and what to do instead. An agent told only "no" can only guess.
    """

    model_config = ConfigDict(frozen=True)

    ok: bool = False
    error: str
    detail: str = ""
    checks: list[dict[str, Any]] = Field(default_factory=list)


class ProposalView(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool = True
    proposal_id: str
    status: str
    sql: str
    checks: list[dict[str, Any]]
    tables: list[str]
    row_limit: int | None
    limit_added: bool
    estimated_rows: int | None
    estimated_cost: float | None
    plan: list[str]
    policy: str
    policy_reason: str


class ResultView(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool = True
    result_id: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    sanity: dict[str, Any]
    data_as_of: str | None = None


class Tools:
    def __init__(
        self,
        *,
        model: SemanticModel,
        guards: Guards,
        store: Store,
        database: Database,
        limits: Limits,
    ) -> None:
        self.model = model
        self.guards = guards
        self.store = store
        self.db = database
        self.limits = limits

    # -- 1. describe_schema ----------------------------------------------------

    def describe_schema(self, table: str | None = None, *, user_id: str) -> dict[str, Any]:
        """Serve the semantic layer.

        With eight tables the whole thing fits in context, so there is no search
        over the dictionary. The size at which search becomes necessary is
        recorded in docs/not-done.md rather than guessed at now.
        """
        if table:
            key = table.upper().removeprefix("SH.")
            found = self.model.tables.get(key)
            if found is None:
                self.store.record(
                    user_id=user_id, tool="describe_schema", outcome="not_found", table=table
                )
                return ToolError(
                    error=f"Таблицы {table} нет в словаре.",
                    detail="Доступны: " + ", ".join(sorted(self.model.tables)),
                ).model_dump()
            tables = {key: found}
        else:
            tables = self.model.tables

        as_of = self.db.replica_as_of()
        payload = {
            "ok": True,
            # The agent reads a reporting replica, not the transactional system,
            # so every answer has to carry the moment the data describes.
            "data_as_of": as_of,
            "source": (
                "Отчётная реплика. Данные на "
                + (as_of or "неизвестный момент")
                + ". Это копия транзакционной базы, а не она сама, поэтому "
                "изменения после этого момента в ответах не видны. Указывайте "
                "этот момент в ответе бизнесу."
            ),
            "tables": [
                {
                    "name": self.model.qualified(name),
                    "title": t.title,
                    "description": t.description.strip(),
                    "grain": t.grain,
                    "columns": [
                        {
                            "name": c.name,
                            "title": c.title,
                            "type": c.type,
                            "description": c.description.strip(),
                            "key": c.key,
                            "masked": c.pii,
                            "values": c.values,
                            "required_filter": c.required_filter,
                        }
                        for c in t.columns
                    ],
                    "relations": [
                        {
                            "to": self.model.qualified(r.to),
                            "kind": r.kind,
                            "on": [f"{k.left} = {k.right}" for k in r.join_on],
                            "description": r.description.strip(),
                        }
                        for r in t.relations
                    ],
                    "gotchas": [
                        {"id": g.id, "severity": g.severity, "text": g.text.strip(),
                         "wrong": g.wrong, "right": g.right}
                        for g in t.gotchas
                    ],
                    "typical_filters": t.typical_filters,
                }
                for name, t in sorted(tables.items())
            ],
            "metrics": [
                {
                    "name": m.name,
                    "title": m.title,
                    "description": m.description.strip(),
                    "base_table": self.model.qualified(m.base_table),
                    "expression": " ".join(m.expression.split()),
                    "unit": m.unit,
                    "unit_column": m.unit_column,
                    "required_filters": m.required_filters,
                    "gotchas": [
                        {"id": g.id, "severity": g.severity, "text": g.text.strip()}
                        for g in m.gotchas
                    ],
                }
                for m in sorted(self.model.metrics.values(), key=lambda x: x.name)
            ],
            "rules": [
                "Если метрика объявлена, используйте её выражение и не считайте по-своему.",
                "Если нужной метрики нет, напишите выражение сами и обязательно "
                "пометьте ответ строкой о том, что определение не из словаря.",
                "Таблицы указываются со схемой: SH.ZVBRP, а не ZVBRP.",
                "Соединять можно только по объявленным связям.",
                "Персональные поля не запрашиваются: они помечены как masked.",
            ],
        }
        self.store.record(
            user_id=user_id, tool="describe_schema", outcome="ok",
            tables=len(payload["tables"]),
        )
        return payload

    # -- 2. propose_query ------------------------------------------------------

    def propose_query(
        self, question: str, sql: str, *, user_id: str, trace_id: str | None = None
    ) -> dict[str, Any]:
        started = time.monotonic()
        verdict: Verdict = self.guards.check(sql)
        checks = [c.model_dump() for c in verdict.checks]

        if not verdict.ok:
            proposal = self.store.add_proposal(
                Proposal(
                    id=new_id("prop"), user_id=user_id, trace_id=trace_id,
                    question=question, sql=sql, status=ProposalStatus.BLOCKED,
                    checks=checks, tables=verdict.tables, columns=verdict.columns,
                    row_limit=verdict.row_limit,
                    policy_reason="отклонено ограничителями",
                )
            )
            self.store.record(
                user_id=user_id, tool="propose_query", outcome="blocked",
                trace_id=trace_id, proposal_id=proposal.id,
                duration_ms=int((time.monotonic() - started) * 1000),
                failed=[c.id for c in verdict.failures],
            )
            return ToolError(
                error="Запрос не прошёл ограничители.",
                detail="; ".join(f"{c.title}: {c.detail}" for c in verdict.failures),
                checks=checks,
            ).model_dump()

        proposal_id = new_id("prop")
        try:
            plan = self.db.explain(verdict.sql, statement_id=proposal_id[:30])
        except QueryRefused as exc:
            self.store.record(
                user_id=user_id, tool="propose_query", outcome="explain_failed",
                trace_id=trace_id, error=str(exc),
            )
            return ToolError(
                error="База отказалась строить план запроса.",
                detail=str(exc), checks=checks,
            ).model_dump()

        policy, reason = self._policy(verdict, plan.estimated_rows)
        proposal = self.store.add_proposal(
            Proposal(
                id=proposal_id, user_id=user_id, trace_id=trace_id,
                question=question, sql=verdict.sql, status=policy,
                checks=checks, tables=verdict.tables, columns=verdict.columns,
                row_limit=verdict.row_limit, limit_imposed=int(verdict.limit_added),
                estimated_rows=plan.estimated_rows,
                estimated_cost=plan.estimated_cost, plan=plan.lines,
                policy_reason=reason,
            )
        )
        self.store.record(
            user_id=user_id, tool="propose_query", outcome="ok",
            trace_id=trace_id, proposal_id=proposal.id,
            duration_ms=int((time.monotonic() - started) * 1000),
            policy=policy, estimated_rows=plan.estimated_rows,
        )
        return ProposalView(
            proposal_id=proposal.id, status=policy, sql=verdict.sql, checks=checks,
            tables=verdict.tables, row_limit=verdict.row_limit,
            limit_added=verdict.limit_added, estimated_rows=plan.estimated_rows,
            estimated_cost=plan.estimated_cost, plan=plan.lines,
            policy=policy, policy_reason=reason,
        ).model_dump()

    def _policy(self, verdict: Verdict, estimated_rows: int | None) -> tuple[str, str]:
        """Small and simple runs itself. Everything else waits for an analyst.

        The thresholds are configuration, and the panel can flip a task either
        way. Data-dependent policy lives here rather than in the gateway config,
        because this is where the data is.
        """
        limits = self.limits
        if len(verdict.tables) > limits.auto_max_tables:
            return (
                ProposalStatus.PENDING,
                f"Таблиц {len(verdict.tables)}, порог автовыполнения "
                f"{limits.auto_max_tables}. Нужно подтверждение аналитика.",
            )
        if estimated_rows is None:
            return (
                ProposalStatus.PENDING,
                "База не дала оценку числа строк. Без оценки объёма запрос не "
                "выполняется автоматически.",
            )
        if estimated_rows > limits.auto_max_rows:
            return (
                ProposalStatus.PENDING,
                f"Оценка {estimated_rows} строк, порог автовыполнения "
                f"{limits.auto_max_rows}. Нужно подтверждение аналитика.",
            )
        return (
            ProposalStatus.AUTO,
            f"Простой запрос: таблиц {len(verdict.tables)}, оценка "
            f"{estimated_rows} строк. Выполняется без подтверждения.",
        )

    # -- 3. execute_query ------------------------------------------------------

    def execute_query(
        self, proposal_id: str, *, user_id: str, trace_id: str | None = None
    ) -> dict[str, Any]:
        limits = self.limits

        allowed, reason = self.store.take_token(
            user_id,
            refill_per_minute=limits.refill_per_minute,
            bucket_size=limits.bucket_size,
            daily_cap=limits.daily_cap,
        )
        if not allowed:
            self.store.record(
                user_id=user_id, tool="execute_query", outcome="rate_limited",
                trace_id=trace_id, proposal_id=proposal_id, reason=reason,
            )
            return ToolError(error="Лимит запросов исчерпан.", detail=reason).model_dump()

        if self.store.running() >= limits.max_concurrent_total:
            return ToolError(
                error="Сейчас выполняется предельное число запросов.",
                detail=(
                    f"Одновременно выполняется {limits.max_concurrent_total} запросов, "
                    "это общий потолок на всех. Повторите через минуту."
                ),
            ).model_dump()
        if self.store.running(user_id=user_id) >= limits.max_concurrent_per_user:
            return ToolError(
                error="У вас уже выполняются запросы.",
                detail=f"Одновременно можно {limits.max_concurrent_per_user}.",
            ).model_dump()

        try:
            proposal = self.store.claim_for_execution(proposal_id, user_id=user_id)
        except KeyError:
            return ToolError(error=f"Предложения {proposal_id} не существует.").model_dump()
        except PermissionError as exc:
            self.store.record(
                user_id=user_id, tool="execute_query", outcome="forbidden",
                trace_id=trace_id, proposal_id=proposal_id,
            )
            return ToolError(error="Чужое предложение.", detail=str(exc)).model_dump()
        except ValueError as exc:
            return ToolError(
                error="Предложение нельзя выполнить.",
                detail=(
                    f"{exc}. Предложение одноразовое: если оно уже выполнено, "
                    "соберите новое через propose_query."
                ),
            ).model_dump()

        self.store.record(
            user_id=user_id, tool="execute_query", outcome="started",
            trace_id=trace_id, proposal_id=proposal.id,
        )
        try:
            rows = self.db.run(
                proposal.sql,
                max_rows=proposal.row_limit or limits.max_rows,
                timeout_seconds=limits.query_timeout_seconds,
            )
        except (QueryTimeout, QueryRefused) as exc:
            self.store.record(
                user_id=user_id, tool="execute_query", outcome="finished",
                trace_id=trace_id, proposal_id=proposal.id, error=str(exc),
            )
            return ToolError(error="Запрос не выполнен.", detail=str(exc)).model_dump()

        result = self.store.add_result(
            Result(
                id=new_id("res"), proposal_id=proposal.id, row_count=rows.row_count,
                truncated=int(rows.truncated), duration_ms=rows.duration_ms,
                columns=rows.columns,
                rows=[[_jsonable(v) for v in row] for row in rows.rows],
            )
        )
        report = sanity_check_rows(
            rows,
            row_limit=proposal.row_limit or limits.max_rows,
            limit_imposed=bool(proposal.limit_imposed),
        )
        self.store.record(
            user_id=user_id, tool="execute_query", outcome="finished",
            trace_id=trace_id, proposal_id=proposal.id, duration_ms=rows.duration_ms,
            row_count=rows.row_count, truncated=rows.truncated,
            sanity=report.worst,
        )
        return ResultView(
            data_as_of=self.db.replica_as_of(),
            result_id=result.id, columns=rows.columns,
            rows=[[_jsonable(v) for v in row] for row in rows.rows],
            row_count=rows.row_count, truncated=rows.truncated,
            duration_ms=rows.duration_ms, sanity=report.model_dump(),
        ).model_dump()

    # -- 4. sanity_check -------------------------------------------------------

    def sanity_check(self, result_id: str, *, user_id: str) -> dict[str, Any]:
        result = self.store.get_result(result_id)
        if result is None:
            return ToolError(error=f"Результата {result_id} не существует.").model_dump()

        proposal = self.store.get_proposal(result.proposal_id)
        row_limit = (proposal.row_limit if proposal else None) or self.limits.max_rows
        from .db import Rows

        report: SanityReport = sanity_check_rows(
            Rows(
                columns=result.columns, rows=result.rows, row_count=result.row_count,
                truncated=bool(result.truncated), duration_ms=result.duration_ms,
            ),
            row_limit=row_limit,
            limit_imposed=bool(proposal.limit_imposed) if proposal else True,
        )
        self.store.record(
            user_id=user_id, tool="sanity_check", outcome=report.worst,
            proposal_id=result.proposal_id,
        )
        return {"ok": True, "result_id": result_id, **report.model_dump(),
                "worst": report.worst}


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
