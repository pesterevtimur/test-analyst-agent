"""The deterministic half of the judge, which is the half that runs in CI.

The model half is not tested here: it needs a key and a network call, and a test
that silently skips is worse than no test. It is exercised in the reference run.
"""

from __future__ import annotations

from sap_agent_evals.compare import Table
from sap_agent_evals.judge import Status, check_answer, judge

RESULT = Table.of(["CURRENCY", "REVENUE"], [["USD", 23765506.62]])
EMPTY = Table.of(["CURRENCY", "REVENUE"], [])
AS_OF = "2026-09-02T15:45:19"

GOOD = (
    "Выручка за 2021 год 23 765 506,62 USD. Считал по позициям фактуры с "
    "фильтром по манданту и году из календаря. Данные на 2026-09-02, это "
    "отчётная реплика."
)


def ids(checks, status) -> set[str]:
    return {c.id for c in checks if c.status is status}


def test_a_complete_answer_passes_every_rule() -> None:
    checks = check_answer(
        GOOD, result=RESULT, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert not ids(checks, Status.FAILED)


def test_a_number_that_is_not_in_the_result_fails() -> None:
    """INSTR-11: the number in the answer comes from the rows, or it came from
    somewhere nobody can audit."""
    answer = GOOD.replace("23 765 506,62", "31 000 000,00")
    checks = check_answer(
        answer, result=RESULT, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert "numbers-from-the-result" in ids(checks, Status.FAILED)


def test_the_same_number_written_differently_still_matches() -> None:
    answer = GOOD.replace("23 765 506,62", "23765506.62")
    checks = check_answer(
        answer, result=RESULT, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert "numbers-from-the-result" not in ids(checks, Status.FAILED)


def test_a_rounded_number_still_matches() -> None:
    answer = GOOD.replace("23 765 506,62", "23 765 507")
    checks = check_answer(
        answer, result=RESULT, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert "numbers-from-the-result" not in ids(checks, Status.FAILED)


def test_a_missing_data_moment_fails() -> None:
    answer = "Выручка за 2021 год 23 765 506,62 USD, считал по позициям фактуры."
    checks = check_answer(
        answer, result=RESULT, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert "data-as-of" in ids(checks, Status.FAILED)


def test_an_answer_that_never_says_how_it_was_obtained_fails() -> None:
    answer = "23 765 506,62 USD. Данные на 2026-09-02."
    checks = check_answer(
        answer, result=RESULT, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert "how-obtained" in ids(checks, Status.FAILED)


def test_calling_an_empty_result_a_zero_fails() -> None:
    """INSTR-8. The failure this catches looks like a correct answer."""
    answer = (
        "Выручка за 2023 год составила 0 USD. Считал по позициям фактуры, "
        "данные на 2026-09-02."
    )
    checks = check_answer(
        answer, result=EMPTY, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert "empty-is-not-zero" in ids(checks, Status.FAILED)


def test_saying_there_is_no_data_passes() -> None:
    answer = (
        "За 2023 год данных нет: продажи в реплике заканчиваются 31 декабря "
        "2022 года. Запрос отработал и вернул ноль строк. Данные на 2026-09-02."
    )
    checks = check_answer(
        answer, result=EMPTY, data_as_of=AS_OF, measure_columns=["REVENUE"]
    )
    assert not ids(checks, Status.FAILED)


def test_an_empty_answer_fails_immediately() -> None:
    checks = check_answer("   ", result=RESULT, data_as_of=AS_OF)
    assert ids(checks, Status.FAILED) == {"answer-exists"}


def test_the_verdict_without_the_model_carries_no_score() -> None:
    verdict = judge(
        question="Сколько мы продали за 2021 год?",
        answer=GOOD,
        result=RESULT,
        data_as_of=AS_OF,
        measure_columns=["REVENUE"],
        use_model=False,
    )
    assert verdict.ok
    assert verdict.score is None
