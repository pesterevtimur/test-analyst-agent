"""The frozen gold answers, checked without a database.

Two things can rot here. The gold SQL gets edited and the frozen numbers stay,
so the set silently measures against an answer nobody produced. Or the frozen
answer stops matching what the question declares it compares on, and every run
scores zero for a reason that has nothing to do with the agent.
"""

from __future__ import annotations

import pytest

from sap_agent_evals import expected as frozen
from sap_agent_evals.compare import compare
from sap_agent_evals.dataset import Kind, load_dataset

DATASET = load_dataset()
ANSWERABLE = [q for q in DATASET.questions if q.kind is Kind.ANSWERABLE]


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_every_answerable_question_has_a_frozen_answer(question) -> None:
    assert frozen.exists(question.id), (
        f"{question.id}: нет замороженного результата. "
        "Запустите evals/tools/freeze_gold.py на поднятой реплике."
    )


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_frozen_answer_belongs_to_the_current_gold_sql(question) -> None:
    result = frozen.load(question.id)
    assert result.matches(question.gold_sql), (
        f"{question.id}: эталонный запрос изменился после заморозки. "
        "Перезаморозьте, иначе набор сверяется с ответом, которого никто не получал."
    )


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_frozen_answer_carries_the_columns_the_question_compares_on(question) -> None:
    result = frozen.load(question.id)
    declared = question.expect.key_columns + question.expect.measure_columns
    missing = [c for c in declared if c not in result.columns]
    assert not missing, f"{question.id}: {missing}"


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_frozen_answer_is_not_empty(question) -> None:
    """An empty gold answer means the filter never matched, not that the answer
    is nothing. Freezing one would make a broken query the standard."""
    assert frozen.load(question.id).row_count > 0, question.id


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q.id)
def test_frozen_answer_compares_equal_to_itself(question) -> None:
    """The comparison rules applied to the gold answer must return a match.

    Catches the case where the declared key does not identify a row: duplicated
    keys make every future run fail on grain, and the failure would look like
    the agent's fault.
    """
    table = frozen.load(question.id).as_table()
    result = compare(table, table, question.expect)
    assert result.ok, f"{question.id}: {result.summary}"
