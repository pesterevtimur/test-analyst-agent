"""Tests for the shared state.

The interesting cases are the ones that make approval meaningful: a proposal
runs once, a proposal belongs to one analyst, and a limit cannot be cleared by
restarting the process.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sap_agent_mcp.store import (
    Proposal,
    ProposalStatus,
    Store,
    new_id,
)


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "state.db")


def make_proposal(store: Store, *, user: str = "analyst-1", status=ProposalStatus.PENDING):
    return store.add_proposal(
        Proposal(
            id=new_id("prop"),
            user_id=user,
            question="Выручка по странам за второй квартал 2021",
            sql="SELECT 1 FROM sh.zvbrp",
            status=status,
            checks=[],
            tables=["SH.ZVBRP"],
            columns=["SH.ZVBRP.NETWR"],
            row_limit=1000,
        )
    )


# --- single use --------------------------------------------------------------

# INSTR-5: SQL reaches the database only through a proposal, and a proposal is
# single use, so an approval cannot be replayed.
def test_an_approved_proposal_executes_once(store):
    proposal = make_proposal(store)
    store.decide(proposal.id, status=ProposalStatus.APPROVED, by="analyst-1")

    claimed = store.claim_for_execution(proposal.id, user_id="analyst-1")
    assert claimed.status == ProposalStatus.EXECUTED

    with pytest.raises(ValueError, match="only once"):
        store.claim_for_execution(proposal.id, user_id="analyst-1")


# INSTR-7: a pending proposal waits for an analyst and cannot be executed by
# the agent, whatever it decides in the conversation.
def test_a_pending_proposal_cannot_execute(store):
    proposal = make_proposal(store)
    with pytest.raises(ValueError, match="cannot run"):
        store.claim_for_execution(proposal.id, user_id="analyst-1")


def test_a_rejected_proposal_cannot_execute(store):
    proposal = make_proposal(store)
    store.decide(proposal.id, status=ProposalStatus.REJECTED, by="analyst-1", note="не тот период")
    with pytest.raises(ValueError, match="cannot run"):
        store.claim_for_execution(proposal.id, user_id="analyst-1")


def test_a_proposal_belongs_to_one_analyst(store):
    proposal = make_proposal(store, user="analyst-1")
    store.decide(proposal.id, status=ProposalStatus.APPROVED, by="analyst-2")
    with pytest.raises(PermissionError, match="another analyst"):
        store.claim_for_execution(proposal.id, user_id="analyst-2")


def test_a_decision_cannot_be_overwritten(store):
    proposal = make_proposal(store)
    store.decide(proposal.id, status=ProposalStatus.APPROVED, by="analyst-1")
    with pytest.raises(ValueError, match="only a pending"):
        store.decide(proposal.id, status=ProposalStatus.REJECTED, by="analyst-2")


def test_the_decision_is_kept_with_who_and_when(store):
    proposal = make_proposal(store)
    decided = store.decide(
        proposal.id, status=ProposalStatus.APPROVED, by="ведущий аналитик",
        note="период уточнён у заказчика",
    )
    assert decided.decided_by == "ведущий аналитик"
    assert decided.decision_note == "период уточнён у заказчика"
    assert decided.decided_at is not None


# --- rate limiting -----------------------------------------------------------

LIMITS = {"refill_per_minute": 1.0, "bucket_size": 5, "daily_cap": 100}


def test_a_burst_is_allowed_up_to_the_bucket_size(store):
    at = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    for _ in range(5):
        allowed, reason = store.take_token("u1", at=at, **LIMITS)
        assert allowed, reason
    allowed, reason = store.take_token("u1", at=at, **LIMITS)
    assert not allowed
    assert "Слишком часто" in reason
    assert "секунд" in reason, "the refusal must say when the caller may retry"


def test_the_bucket_refills_over_time(store):
    at = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    for _ in range(5):
        store.take_token("u1", at=at, **LIMITS)
    allowed, _ = store.take_token("u1", at=at + timedelta(minutes=1), **LIMITS)
    assert allowed


def test_the_daily_cap_holds_even_when_the_bucket_is_full(store):
    at = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    limits = {"refill_per_minute": 60.0, "bucket_size": 5, "daily_cap": 3}
    for i in range(3):
        allowed, _ = store.take_token("u1", at=at + timedelta(minutes=i), **limits)
        assert allowed
    allowed, reason = store.take_token("u1", at=at + timedelta(minutes=9), **limits)
    assert not allowed
    assert "суточный" in reason


def test_the_daily_cap_resets_the_next_day(store):
    at = datetime(2026, 9, 2, 23, 0, tzinfo=UTC)
    limits = {"refill_per_minute": 60.0, "bucket_size": 5, "daily_cap": 1}
    assert store.take_token("u1", at=at, **limits)[0]
    assert not store.take_token("u1", at=at + timedelta(minutes=1), **limits)[0]
    assert store.take_token("u1", at=at + timedelta(hours=2), **limits)[0]


def test_a_limit_survives_a_restart(tmp_path):
    """Restarting the process must not hand back a fresh quota.

    Otherwise the way around the limit is to wait for a deploy.
    """
    at = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    limits = {"refill_per_minute": 1.0, "bucket_size": 2, "daily_cap": 100}
    path = tmp_path / "state.db"

    first = Store(path)
    assert first.take_token("u1", at=at, **limits)[0]
    assert first.take_token("u1", at=at, **limits)[0]
    assert not first.take_token("u1", at=at, **limits)[0]

    second = Store(path)
    allowed, reason = second.take_token("u1", at=at, **limits)
    assert not allowed, "a new process handed out a fresh bucket"
    assert "Слишком часто" in reason


def test_raising_a_limit_requires_a_reason(store):
    with pytest.raises(ValueError, match="requires a reason"):
        store.grant_bonus("u1", extra=50, by="analyst-1", reason="   ")


def test_a_granted_bonus_raises_the_daily_cap_and_is_journalled(store):
    at = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    limits = {"refill_per_minute": 60.0, "bucket_size": 5, "daily_cap": 1}
    assert store.take_token("u1", at=at, **limits)[0]
    assert not store.take_token("u1", at=at + timedelta(minutes=1), **limits)[0]

    store.grant_bonus("u1", extra=2, by="ведущий аналитик", reason="закрытие квартала")
    assert store.take_token("u1", at=at + timedelta(minutes=2), **limits)[0]

    with store.session() as session:
        from sap_agent_mcp.store import JournalEntry
        entries = session.query(JournalEntry).filter_by(tool="limits").all()
        assert len(entries) == 1
        assert entries[0].detail["reason"] == "закрытие квартала"


# --- journal and concurrency --------------------------------------------------

def test_refusals_are_journalled_too(store):
    store.record(user_id="u1", tool="propose_query", outcome="blocked", check="masking")
    with store.session() as session:
        from sap_agent_mcp.store import JournalEntry
        entry = session.query(JournalEntry).one()
        assert entry.outcome == "blocked"
        assert entry.detail["check"] == "masking"


def test_concurrency_counts_started_minus_finished(store):
    assert store.running() == 0
    store.record(user_id="u1", tool="execute_query", outcome="started")
    store.record(user_id="u2", tool="execute_query", outcome="started")
    assert store.running() == 2
    assert store.running(user_id="u1") == 1
    store.record(user_id="u1", tool="execute_query", outcome="finished")
    assert store.running() == 1
    assert store.running(user_id="u1") == 0


def test_a_proposal_remembers_the_data_moment_it_was_planned_against(store):
    proposal = store.add_proposal(
        Proposal(
            id=new_id("prop"), user_id="analyst-1", question="в", sql="SELECT 1 FROM sh.zvbrp",
            status=ProposalStatus.AUTO, checks=[], tables=[], columns=[], row_limit=10,
            data_as_of="2026-09-02T15:29:07+00:00",
        )
    )
    assert store.get_proposal(proposal.id).data_as_of == "2026-09-02T15:29:07+00:00"


def test_a_new_column_is_added_to_an_existing_state_database(tmp_path, caplog):
    """Adding a field to a model must not leave an old database a column behind.

    create_all() only creates missing tables, so without this the first tool call
    against an older state file fails at runtime instead of the server refusing
    to start.
    """
    import sqlalchemy as sa

    path = tmp_path / "state.db"
    Store(path)

    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(sa.text("ALTER TABLE proposals DROP COLUMN data_as_of"))
    with engine.connect() as connection:
        columns = {c["name"] for c in sa.inspect(engine).get_columns("proposals")}
    assert "data_as_of" not in columns

    Store(path)  # reopening must repair the schema
    columns = {c["name"] for c in sa.inspect(engine).get_columns("proposals")}
    assert "data_as_of" in columns
