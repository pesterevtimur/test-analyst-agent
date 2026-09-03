"""The comparison rules, one test per rule.

The rules are worth testing on their own because they decide what counts as a
right answer. A tolerant comparison reports quality the project does not have;
a strict one reports failures that are formatting.
"""

from __future__ import annotations

from datetime import date

from sap_agent_evals.compare import Table, compare
from sap_agent_evals.dataset import Expectation

BY_COUNTRY = Expectation(key_columns=["country"], measure_columns=["revenue"])
SINGLE = Expectation(key_columns=[], measure_columns=["revenue"])


def table(rows, columns=("COUNTRY", "REVENUE")) -> Table:
    return Table.of(columns, rows)


def test_identical_results_match() -> None:
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    assert compare(gold, gold, BY_COUNTRY).ok


def test_row_order_does_not_matter() -> None:
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    got = table([["Japan", 50.0], ["Italy", 100.0]])
    assert compare(gold, got, BY_COUNTRY).ok


def test_extra_columns_are_allowed() -> None:
    gold = table([["Italy", 100.0]])
    got = Table.of(["COUNTRY", "REVENUE", "CURRENCY"], [["Italy", 100.0, "USD"]])
    assert compare(gold, got, BY_COUNTRY).ok


def test_column_case_does_not_matter() -> None:
    gold = table([["Italy", 100.0]])
    got = Table.of(["country", "revenue"], [["Italy", 100.0]])
    assert compare(gold, got, BY_COUNTRY).ok


def test_numbers_within_half_a_percent_match() -> None:
    gold = table([["Italy", 1000.0]])
    got = table([["Italy", 1004.0]])
    assert compare(gold, got, BY_COUNTRY).ok


def test_numbers_outside_the_tolerance_do_not_match() -> None:
    gold = table([["Italy", 1000.0]])
    got = table([["Italy", 1006.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok
    assert result.mismatches
    assert "расхождение" in result.summary


def test_missing_row_is_an_error() -> None:
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    got = table([["Italy", 100.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok
    assert result.missing_rows == ["Japan"]


def test_extra_row_is_an_error() -> None:
    """ADR-007. An extra row is a filter that did not fire."""
    gold = table([["Italy", 100.0]])
    got = table([["Italy", 100.0], ["Japan", 50.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok
    assert result.extra_rows == ["Japan"]
    assert "лишние строки" in result.summary


def test_a_measure_under_another_name_is_matched_by_its_values() -> None:
    """Nobody told the agent which alias to use, so the alias is not the answer.

    This rule came out of the first reference run: a correct number scored zero
    because the column was called TOTAL instead of REVENUE.
    """
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    got = Table.of(["COUNTRY", "TOTAL"], [["Italy", 100.0], ["Japan", 50.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert result.ok, result.summary
    assert any("сопоставлена" in note for note in result.notes)


def test_a_key_under_another_name_is_matched_by_its_values() -> None:
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    got = Table.of(["СТРАНА", "REVENUE"], [["Japan", 50.0], ["Italy", 100.0]])
    assert compare(gold, got, BY_COUNTRY).ok


def test_a_measure_that_is_nowhere_in_the_answer_is_still_an_error() -> None:
    """Renaming is forgiven, absence is not: no column carries these numbers."""
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    got = Table.of(["COUNTRY", "TOTAL"], [["Italy", 7.0], ["Japan", 8.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok
    assert result.missing_columns == ["REVENUE"] or result.mismatches


def test_matching_by_values_does_not_forgive_a_wrong_number() -> None:
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    got = Table.of(["COUNTRY", "TOTAL"], [["Italy", 100.0], ["Japan", 80.0]])
    assert not compare(gold, got, BY_COUNTRY).ok


def test_matching_by_values_does_not_forgive_a_missing_row() -> None:
    gold = table([["Italy", 100.0], ["Japan", 50.0]])
    got = Table.of(["COUNTRY", "TOTAL"], [["Italy", 100.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok


def test_duplicated_key_is_an_error() -> None:
    """The signature of a join that exploded the grain."""
    gold = table([["Italy", 100.0]])
    got = table([["Italy", 50.0], ["Italy", 50.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok
    assert result.duplicate_keys


def test_single_row_answer_with_no_keys() -> None:
    gold = Table.of(["REVENUE"], [[100.0]])
    got = Table.of(["REVENUE"], [[100.4]])
    assert compare(gold, got, SINGLE).ok


def test_single_row_answer_that_came_back_grouped_is_an_error() -> None:
    gold = Table.of(["REVENUE"], [[100.0]])
    got = Table.of(["REVENUE"], [[60.0], [40.0]])
    result = compare(gold, got, SINGLE)
    assert not result.ok
    assert result.extra_rows


def test_keys_compare_by_value_not_by_spelling() -> None:
    """03 the number and '03' the string are the same channel."""
    gold = Table.of(["CHANNEL", "REVENUE"], [["03", 100.0]])
    got = Table.of(["CHANNEL", "REVENUE"], [[" 03 ", 100.0]])
    expectation = Expectation(key_columns=["channel"], measure_columns=["revenue"])
    assert compare(gold, got, expectation).ok


def test_dates_in_keys_compare_as_dates() -> None:
    gold = Table.of(["DAY", "REVENUE"], [[date(2022, 1, 1), 100.0]])
    got = Table.of(["DAY", "REVENUE"], [["2022-01-01", 100.0]])
    expectation = Expectation(key_columns=["day"], measure_columns=["revenue"])
    assert compare(gold, got, expectation).ok


def test_null_measure_equals_null_measure() -> None:
    gold = table([["Italy", None]])
    got = table([["Italy", None]])
    assert compare(gold, got, BY_COUNTRY).ok


def test_null_against_a_number_is_a_mismatch() -> None:
    gold = table([["Italy", None]])
    got = table([["Italy", 0.0]])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok


def test_zero_expected_requires_zero() -> None:
    gold = table([["Italy", 0.0]])
    got = table([["Italy", 0.4]])
    assert not compare(gold, got, BY_COUNTRY).ok


def test_text_measures_compare_exactly() -> None:
    gold = Table.of(["COUNTRY", "UNIT"], [["Italy", "PC"]])
    got = Table.of(["COUNTRY", "UNIT"], [["Italy", "KG"]])
    expectation = Expectation(key_columns=["country"], measure_columns=["unit"])
    assert not compare(gold, got, expectation).ok


def test_empty_result_matches_empty_result() -> None:
    gold = table([])
    got = table([])
    assert compare(gold, got, BY_COUNTRY).ok


def test_empty_answer_to_a_non_empty_question_is_an_error() -> None:
    gold = table([["Italy", 100.0]])
    got = table([])
    result = compare(gold, got, BY_COUNTRY)
    assert not result.ok
    assert result.missing_rows
