"""State shared by every analyst: proposals, journal, rate limits.

SQLite, reached through SQLAlchemy. Not in the process memory, on purpose:
a restart must not lose someone else's pending approval, and it must not reset
a rate limit either, because a limit you can clear by waiting for a deploy is
not a limit.

Moving to PostgreSQL is a connection string. The condition that would force it
is a second worker, and it is recorded in docs/not-done.md.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import logging

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


logger = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class ProposalStatus(StrEnum):
    PENDING = "pending"        # waiting for an analyst
    APPROVED = "approved"      # analyst said yes, not executed yet
    AUTO = "auto"              # policy allowed it without an analyst
    REJECTED = "rejected"      # analyst said no
    EXECUTED = "executed"      # used up; a proposal runs exactly once
    SUPERSEDED = "superseded"  # analyst edited it into a new proposal
    BLOCKED = "blocked"        # guard rails refused it


class Base(DeclarativeBase):
    pass


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tables: Mapped[list[str]] = mapped_column(JSON, default=list)
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    row_limit: Mapped[int | None] = mapped_column(Integer)
    # True when the guard rails added or lowered the limit, False when the
    # analyst wrote it. The sanity check reads this to tell a cut-off answer
    # from a deliberate top-N.
    limit_imposed: Mapped[bool] = mapped_column(Integer, default=1)
    estimated_rows: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    plan: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy_reason: Mapped[str] = mapped_column(Text, default="")
    # The moment the replica described when this proposal was planned. A
    # proposal approved against one refresh and executed after the next answers
    # a different question with the same SQL, and nothing in the numbers says so.
    data_as_of: Mapped[str | None] = mapped_column(String(64))
    # The decision, kept rather than overwritten: on a review someone will ask
    # why this was approved, and the answer must be in the system.
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decision_note: Mapped[str | None] = mapped_column(Text)
    supersedes: Mapped[str | None] = mapped_column(String(32))


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    row_count: Mapped[int] = mapped_column(Integer)
    truncated: Mapped[bool] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer)
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    rows: Mapped[list[list[Any]]] = mapped_column(JSON, default=list)


class JournalEntry(Base):
    """Who did what, when, on what, how long it took and whether it was refused.

    Duplicates part of the trace on purpose. Tracing is a convenience and can be
    swapped out; the journal is an obligation and must survive that swap.
    """

    __tablename__ = "journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    tool: Mapped[str] = mapped_column(String(32), index=True)
    outcome: Mapped[str] = mapped_column(String(16), index=True)
    proposal_id: Mapped[str | None] = mapped_column(String(32), index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RateState(Base):
    __tablename__ = "rate_state"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    day: Mapped[str] = mapped_column(String(10))
    day_count: Mapped[int] = mapped_column(Integer, default=0)
    # Set by an analyst with a reason, which is written to the journal. Without
    # the reason, raising a limit becomes a quiet daily habit and the limits
    # turn into decoration.
    bonus: Mapped[int] = mapped_column(Integer, default=0)


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path}", future=True)

        @event.listens_for(self.engine, "connect")
        def _pragmas(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            # WAL so a reader never blocks the writer: the panel reads the queue
            # while the server writes to it.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns the model has and the stored schema does not.

        create_all() creates missing tables and never touches existing ones, so
        adding a field to a model leaves an old database silently one column
        behind. That surfaced here as a tool failing at runtime rather than the
        server refusing to start, which is the wrong way round.

        Only additive changes are applied, and every one is logged. Anything else
        (a column removed, a type changed) stops the server: a state store that
        quietly reshapes itself is worse than one that refuses to open.

        A project that outgrows this uses Alembic. The condition is recorded in
        docs/not-done.md.
        """
        inspector = inspect(self.engine)
        for table in Base.metadata.sorted_tables:
            stored = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in stored:
                    continue
                if not (column.nullable or column.default is not None):
                    raise RuntimeError(
                        f"{table.name}.{column.name} is missing from the stored schema "
                        "and is not nullable, so it cannot be added to existing rows. "
                        "Migrate the state database deliberately."
                    )
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} "
                ddl += column.type.compile(self.engine.dialect)
                with self.engine.begin() as connection:
                    connection.execute(text(ddl))
                logger.warning(
                    "state schema: added %s.%s to an existing database",
                    table.name, column.name,
                )

    def session(self) -> Session:
        return Session(self.engine, future=True)

    # -- journal ---------------------------------------------------------------

    def record(
        self,
        *,
        user_id: str,
        tool: str,
        outcome: str,
        trace_id: str | None = None,
        proposal_id: str | None = None,
        duration_ms: int | None = None,
        **detail: Any,
    ) -> None:
        with self.session() as session:
            session.add(
                JournalEntry(
                    user_id=user_id,
                    tool=tool,
                    outcome=outcome,
                    trace_id=trace_id,
                    proposal_id=proposal_id,
                    duration_ms=duration_ms,
                    detail=json.loads(json.dumps(detail, default=str)),
                )
            )
            session.commit()

    # -- proposals -------------------------------------------------------------

    def add_proposal(self, proposal: Proposal) -> Proposal:
        with self.session() as session:
            session.add(proposal)
            session.commit()
            session.refresh(proposal)
            session.expunge(proposal)
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        with self.session() as session:
            proposal = session.get(Proposal, proposal_id)
            if proposal is not None:
                session.expunge(proposal)
            return proposal

    def pending(self, limit: int = 50) -> list[Proposal]:
        with self.session() as session:
            rows = list(
                session.scalars(
                    select(Proposal)
                    .where(Proposal.status == ProposalStatus.PENDING)
                    .order_by(Proposal.created_at)
                    .limit(limit)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def decide(
        self, proposal_id: str, *, status: ProposalStatus, by: str, note: str = ""
    ) -> Proposal:
        """Approve or reject. Only a pending proposal can be decided."""
        with self.session() as session:
            proposal = session.get(Proposal, proposal_id, with_for_update=False)
            if proposal is None:
                raise KeyError(f"proposal {proposal_id} does not exist")
            if proposal.status != ProposalStatus.PENDING:
                raise ValueError(
                    f"proposal {proposal_id} is {proposal.status}, only a pending "
                    "proposal can be decided"
                )
            proposal.status = status
            proposal.decided_at = now()
            proposal.decided_by = by
            proposal.decision_note = note
            session.commit()
            session.refresh(proposal)
            session.expunge(proposal)
            return proposal

    def claim_for_execution(self, proposal_id: str, *, user_id: str) -> Proposal:
        """Take a proposal for execution, exactly once.

        Single use is what keeps approval meaningful: without it, an approved
        proposal could be replayed as many times as the caller likes.
        """
        with self.session() as session:
            proposal = session.get(Proposal, proposal_id)
            if proposal is None:
                raise KeyError(f"proposal {proposal_id} does not exist")
            if proposal.user_id != user_id:
                raise PermissionError(
                    f"proposal {proposal_id} belongs to another analyst"
                )
            if proposal.status not in (ProposalStatus.APPROVED, ProposalStatus.AUTO):
                raise ValueError(
                    f"proposal {proposal_id} is {proposal.status}, so it cannot run. "
                    "Only an approved or auto-approved proposal executes, and only once."
                )
            proposal.status = ProposalStatus.EXECUTED
            session.commit()
            session.refresh(proposal)
            session.expunge(proposal)
            return proposal

    # -- results ---------------------------------------------------------------

    def add_result(self, result: Result) -> Result:
        with self.session() as session:
            session.add(result)
            session.commit()
            session.refresh(result)
            session.expunge(result)
        return result

    def get_result(self, result_id: str) -> Result | None:
        with self.session() as session:
            result = session.get(Result, result_id)
            if result is not None:
                session.expunge(result)
            return result

    # -- rate limiting ---------------------------------------------------------

    def take_token(
        self,
        user_id: str,
        *,
        refill_per_minute: float,
        bucket_size: int,
        daily_cap: int,
        at: datetime | None = None,
    ) -> tuple[bool, str]:
        """Token bucket plus a daily cap. Returns (allowed, reason in Russian).

        Refusal says what ran out and when it comes back, because a silent
        refusal teaches people to retry rather than to wait.
        """
        moment = at or now()
        today = moment.date().isoformat()

        with self.session() as session:
            state = session.get(RateState, user_id)
            if state is None:
                state = RateState(
                    user_id=user_id,
                    tokens=float(bucket_size),
                    updated_at=moment,
                    day=today,
                    day_count=0,
                    # Column defaults are applied on INSERT, so an object that
                    # has not been flushed yet still reads None here.
                    bonus=0,
                )
                session.add(state)

            if state.day != today:
                state.day = today
                state.day_count = 0
                state.bonus = 0

            elapsed_minutes = max(
                0.0, (moment - state.updated_at.replace(tzinfo=UTC)).total_seconds() / 60
            )
            state.tokens = min(
                float(bucket_size), state.tokens + elapsed_minutes * refill_per_minute
            )
            state.updated_at = moment

            cap = daily_cap + (state.bonus or 0)
            if state.day_count >= cap:
                session.commit()
                return False, (
                    f"Исчерпан суточный лимит запросов: {state.day_count} из {cap}. "
                    "Счётчик обнулится в полночь по UTC. Поднять лимит может "
                    "аналитик в панели, с указанием причины."
                )

            if state.tokens < 1.0:
                wait_seconds = int((1.0 - state.tokens) / refill_per_minute * 60) + 1
                session.commit()
                return False, (
                    f"Слишком часто. Следующий запрос можно через {wait_seconds} секунд. "
                    f"Ёмкость всплеска {bucket_size} запросов, пополнение "
                    f"{refill_per_minute} в минуту."
                )

            state.tokens -= 1.0
            state.day_count += 1
            session.commit()
            return True, ""

    def grant_bonus(self, user_id: str, *, extra: int, by: str, reason: str) -> None:
        """Raise a daily cap for one person. The reason is mandatory."""
        if not reason.strip():
            raise ValueError(
                "raising a limit requires a reason: without one it becomes a quiet "
                "daily habit and the limits turn into decoration"
            )
        with self.session() as session:
            state = session.get(RateState, user_id)
            if state is None:
                state = RateState(
                    user_id=user_id, tokens=0.0, updated_at=now(),
                    day=now().date().isoformat(), day_count=0, bonus=0,
                )
                session.add(state)
            state.bonus = (state.bonus or 0) + extra
            session.commit()
        self.record(
            user_id=user_id, tool="limits", outcome="granted",
            extra=extra, by=by, reason=reason,
        )

    # -- concurrency -----------------------------------------------------------

    def running(self, *, user_id: str | None = None, window_seconds: int = 300) -> int:
        """How many executions are in flight, counted from the journal.

        A started execution writes a 'started' row and a finished one writes
        'finished'; the difference inside the window is what is running. The
        window keeps a crashed process from blocking the queue forever.
        """
        since = now() - timedelta(seconds=window_seconds)
        with self.session() as session:
            def count(outcome: str) -> int:
                query = select(func.count()).select_from(JournalEntry).where(
                    JournalEntry.tool == "execute_query",
                    JournalEntry.outcome == outcome,
                    JournalEntry.at >= since,
                )
                if user_id is not None:
                    query = query.where(JournalEntry.user_id == user_id)
                return session.scalar(query) or 0

            return max(0, count("started") - count("finished"))
