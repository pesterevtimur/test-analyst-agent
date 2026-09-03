"""Every gold query goes through the real guard rails.

Not a formality. The gold SQL is what the agent is asked to match, so a gold
query the guard rails would refuse means the set contains a question the system
cannot answer no matter how good the model is. That is a defect in the guard
rails or in the question, and it has to surface here rather than during the
final run.

No database: the guard rails are static analysis over the semantic layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sap_agent_evals.dataset import GuardExpectation, Kind, load_dataset
from sap_agent_mcp.guards import Guards, Status
from sap_agent_mcp.semantic.loader import load

ROOT = Path(__file__).resolve().parents[2]
DATASET = load_dataset()
GUARDS = Guards(load([ROOT / "mcp_server" / "semantic" / "sap"]), max_rows=1000)

ANSWERABLE = [q for q in DATASET.questions if q.kind is Kind.ANSWERABLE]


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_gold_sql_survives_the_guard_rails(question) -> None:
    verdict = GUARDS.check(question.gold_sql)
    failures = "; ".join(f"{c.id}: {c.detail}" for c in verdict.failures)
    assert verdict.ok, f"{question.id}: {failures}"


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_guard_verdict_is_the_one_the_question_declares(question) -> None:
    verdict = GUARDS.check(question.gold_sql)
    warned = [c.id for c in verdict.warnings]
    expected = question.expect.guard
    if expected is GuardExpectation.PASSED:
        assert not warned, f"{question.id}: неожиданные предупреждения {warned}"
    elif expected is GuardExpectation.WARNING:
        assert warned, f"{question.id}: ожидалось предупреждение, его нет"


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_gold_sql_touches_only_declared_tables(question) -> None:
    verdict = GUARDS.check(question.gold_sql)
    assert verdict.tables, question.id
    assert all(name.startswith("SH.") for name in verdict.tables), verdict.tables


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_gold_sql_asks_for_no_personal_data(question) -> None:
    verdict = GUARDS.check(question.gold_sql)
    masking = next(c for c in verdict.checks if c.id == "masking")
    assert masking.status is Status.PASSED, question.id


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_declared_measure_columns_appear_in_the_gold_query(question) -> None:
    """The names the comparison keys on must be the names the query returns."""
    text = " ".join(question.gold_sql.split()).upper()
    for column in question.expect.key_columns + question.expect.measure_columns:
        assert f" AS {column}" in text, f"{question.id}: нет колонки {column}"
