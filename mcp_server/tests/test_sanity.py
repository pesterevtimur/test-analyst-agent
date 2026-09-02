"""Tests for the plausibility checks.

The check that matters most is the empty result: a query that runs, returns
nothing and reports no error is the failure this project exists to catch.
"""

from __future__ import annotations

from sap_agent_mcp.db import Rows
from sap_agent_mcp.sanity import Level, check


def rows(columns, data, *, truncated=False):
    return Rows(
        columns=columns,
        rows=data,
        row_count=len(data),
        truncated=truncated,
        duration_ms=12,
    )


def ids(report):
    return {o.id for o in report.observations}


def test_an_empty_result_stops_and_names_the_usual_causes():
    report = check(rows(["landx", "netwr"], []), row_limit=1000)
    assert report.worst is Level.STOP
    assert "empty-result" in ids(report)
    text = report.observations[0].text
    for hint in ("2021-02", "нулями", "признак", "2019-2023"):
        assert hint in text, f"the empty-result message must mention {hint}"


def test_a_truncated_result_stops_because_aggregates_over_it_are_wrong():
    data = [[f"c{i}", i] for i in range(1000)]
    report = check(rows(["landx", "netwr"], data, truncated=True), row_limit=1000)
    assert report.worst is Level.STOP
    assert "truncated" in ids(report)


def test_hitting_the_limit_exactly_counts_as_truncated():
    data = [[f"c{i}", i] for i in range(50)]
    report = check(rows(["landx", "netwr"], data), row_limit=50)
    assert "truncated" in ids(report)


def test_an_all_null_column_is_flagged_as_a_failed_join():
    report = check(rows(["landx", "netwr"], [["DE", None], ["FR", None]]), row_limit=1000)
    assert "all-null:netwr" in ids(report)


def test_negative_money_is_flagged():
    report = check(rows(["landx", "netwr"], [["DE", -5.0], ["FR", 10.0]]), row_limit=1000)
    assert "negative:netwr" in ids(report)


def test_a_constant_measure_is_flagged_as_a_broken_grouping():
    data = [["DE", 100.0], ["FR", 100.0], ["IT", 100.0], ["ES", 100.0]]
    report = check(rows(["landx", "netwr"], data), row_limit=1000)
    assert "constant:netwr" in ids(report)


def test_a_healthy_result_passes_quietly():
    data = [["DE", 559723.0], ["JP", 361597.0], ["GB", 351401.0]]
    report = check(rows(["landx", "netwr"], data), row_limit=1000)
    assert report.worst is Level.OK
    assert ids(report) == {"ok"}


def test_a_non_money_column_of_equal_small_numbers_is_not_noisy():
    """Do not flag identical values in a column that is not a measure."""
    data = [["DE", 1], ["FR", 1]]
    report = check(rows(["landx", "spras_id"], data), row_limit=1000)
    assert "constant:spras_id" not in ids(report)


def test_hitting_a_limit_the_analyst_asked_for_is_not_truncation():
    """A top five that returns five rows is the answer, not a cut-off answer.

    Calling both cases truncation trains people to ignore the warning.
    """
    data = [[f"c{i}", i] for i in range(5)]
    report = check(rows(["landx", "netwr"], data), row_limit=5, limit_imposed=False)
    assert report.worst is Level.ATTENTION
    assert "at-requested-limit" in ids(report)
    assert "truncated" not in ids(report)


def test_hitting_a_ceiling_the_guard_rails_imposed_still_stops():
    data = [[f"c{i}", i] for i in range(1000)]
    report = check(rows(["landx", "netwr"], data), row_limit=1000, limit_imposed=True)
    assert report.worst is Level.STOP
    assert "truncated" in ids(report)
