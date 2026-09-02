"""Tests for the guard rails.

Written as attacks, not as demonstrations. A guard rail that has only ever been
shown working has not been tested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sap_agent_mcp.guards import Guards
from sap_agent_mcp.semantic import load

SEMANTIC = Path(__file__).resolve().parents[1] / "semantic"

GOOD = """
SELECT t.landx, SUM(v.netwr) AS revenue
FROM sh.zvbrp v
JOIN sh.zkna1 k ON k.kunnr = v.kunnr AND k.mandt = v.mandt
JOIN sh.zt005t t ON t.land1 = k.land1 AND t.mandt = k.mandt AND t.spras = 'E'
WHERE v.mandt = '100' AND k.lvorm = ' '
GROUP BY t.landx
"""


@pytest.fixture(scope="module")
def guards() -> Guards:
    return Guards(load([SEMANTIC / "sap"]), max_rows=1000)


def failed_ids(verdict) -> set[str]:
    return {check.id for check in verdict.failures}


# --- the happy path ---------------------------------------------------------

def test_a_correct_query_passes_every_check(guards):
    verdict = guards.check(GOOD)
    assert verdict.ok, [c.detail for c in verdict.failures]
    assert len(verdict.checks) == 5
    assert set(verdict.tables) == {"SH.ZVBRP", "SH.ZKNA1", "SH.ZT005T"}


def test_a_missing_limit_is_added_rather_than_refused(guards):
    verdict = guards.check(GOOD)
    assert verdict.limit_added is True
    assert verdict.row_limit == 1000
    assert "1000" in verdict.sql


def test_an_oversized_limit_is_capped(guards):
    verdict = guards.check("SELECT v.netwr FROM sh.zvbrp v WHERE v.mandt = '100' LIMIT 50000")
    assert verdict.ok
    assert verdict.row_limit == 1000
    assert verdict.limit_added is True


def test_a_reasonable_limit_is_left_alone(guards):
    verdict = guards.check("SELECT v.netwr FROM sh.zvbrp v WHERE v.mandt = '100' LIMIT 10")
    assert verdict.ok
    assert verdict.row_limit == 10
    assert verdict.limit_added is False


# --- writes ------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sh.zvbrp",
        "UPDATE sh.zvbrp SET netwr = 0",
        "INSERT INTO sh.zvbrp (mandt) VALUES ('100')",
        "DROP TABLE sh.zvbrp",
        "CREATE TABLE t AS SELECT * FROM sh.zvbrp",
        "TRUNCATE TABLE sh.zvbrp",
        "GRANT SELECT ON sh.zvbrp TO public",
    ],
)
def test_writes_are_refused(guards, sql):
    verdict = guards.check(sql)
    assert not verdict.ok
    assert "read-only" in failed_ids(verdict)


def test_a_second_statement_smuggled_after_a_semicolon_is_refused(guards):
    verdict = guards.check("SELECT 1 FROM sh.zvbrp; DROP TABLE sh.zvbrp")
    assert not verdict.ok
    assert "read-only" in failed_ids(verdict)


def test_a_write_hidden_inside_a_select_is_refused(guards):
    verdict = guards.check(
        "SELECT * FROM (SELECT netwr FROM sh.zvbrp) WHERE 1=1 UNION ALL SELECT 1 FROM dual"
    )
    # dual is not in the allow list, so this must fail on the allow list rather
    # than sneak through as a plain select.
    assert not verdict.ok


def test_garbage_is_refused_with_a_readable_reason(guards):
    verdict = guards.check("SELEKT * FROM")
    assert not verdict.ok
    assert "read-only" in failed_ids(verdict)
    assert verdict.failures[0].detail


# --- the allow list ----------------------------------------------------------

def test_a_table_outside_the_allow_list_is_refused(guards):
    verdict = guards.check("SELECT * FROM sh.customers")
    assert not verdict.ok
    assert "allowlist" in failed_ids(verdict)


def test_a_system_table_is_refused(guards):
    verdict = guards.check("SELECT username FROM sys.dba_users")
    assert not verdict.ok
    assert "allowlist" in failed_ids(verdict)


def test_an_unqualified_table_is_refused(guards):
    verdict = guards.check("SELECT netwr FROM zvbrp")
    assert not verdict.ok
    assert "allowlist" in failed_ids(verdict)


def test_a_column_that_does_not_exist_is_refused(guards):
    verdict = guards.check("SELECT v.no_such_column FROM sh.zvbrp v")
    assert not verdict.ok
    assert "allowlist" in failed_ids(verdict)


# --- personal data -----------------------------------------------------------

@pytest.mark.parametrize("column", ["telf1", "smtp_addr", "name1", "stras"])
def test_personal_columns_are_refused(guards, column):
    verdict = guards.check(f"SELECT k.{column} FROM sh.zkna1 k WHERE k.mandt = '100'")
    assert not verdict.ok
    assert "masking" in failed_ids(verdict)


def test_personal_data_is_refused_even_when_hidden_in_a_function(guards):
    verdict = guards.check(
        "SELECT UPPER(SUBSTR(k.smtp_addr, 1, 3)) FROM sh.zkna1 k WHERE k.mandt = '100'"
    )
    assert not verdict.ok
    assert "masking" in failed_ids(verdict)


def test_a_star_select_on_a_table_with_personal_data_does_not_leak(guards):
    """SELECT * expands to every column, personal ones included."""
    verdict = guards.check("SELECT * FROM sh.zkna1 WHERE mandt = '100'")
    assert not verdict.ok, "SELECT * on ZKNA1 must not pass: it returns phone and email"


# --- joins -------------------------------------------------------------------

def test_a_cross_join_without_a_condition_is_refused(guards):
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v JOIN sh.zmara m ON 1 = 1 WHERE v.mandt = '100'"
    )
    assert not verdict.ok
    assert "joins" in failed_ids(verdict)


def test_an_undeclared_join_is_refused(guards):
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v "
        "JOIN sh.zt005t t ON t.land1 = v.waerk "
        "WHERE v.mandt = '100'"
    )
    assert not verdict.ok
    assert "joins" in failed_ids(verdict)


def test_a_declared_join_passes(guards):
    verdict = guards.check(
        "SELECT SUM(v.netwr) FROM sh.zvbrp v "
        "JOIN sh.wakh a ON a.aktnr = v.aktnr AND a.mandt = v.mandt "
        "WHERE v.mandt = '100' AND v.aktnr <> '0000000999'"
    )
    assert verdict.ok, [c.detail for c in verdict.failures]


# --- the verdict is usable ---------------------------------------------------

def test_every_check_reports_in_russian_and_says_why(guards):
    verdict = guards.check("SELECT * FROM sh.customers")
    for check in verdict.checks:
        assert check.title and check.detail
        assert any("Ѐ" <= ch <= "ӿ" for ch in check.title), (
            f"check {check.id}: the title is not in Russian, the analyst reads it"
        )


def test_the_verdict_lists_every_check_not_just_the_first_failure(guards):
    verdict = guards.check(GOOD)
    assert [c.id for c in verdict.checks] == [
        "read-only",
        "allowlist",
        "masking",
        "joins",
        "row-limit",
    ]


def test_a_join_condition_that_relates_nothing_is_refused(guards):
    """ON 1 = 1 is a cartesian product wearing a join condition."""
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v JOIN sh.zmara m ON 1 = 1 WHERE v.mandt = '100'"
    )
    assert not verdict.ok
    assert "joins" in failed_ids(verdict)


def test_a_join_condition_that_only_filters_one_side_is_refused(guards):
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v JOIN sh.zmara m ON m.mandt = '100' "
        "WHERE v.mandt = '100'"
    )
    assert not verdict.ok
    assert "joins" in failed_ids(verdict)


def test_an_implicit_comma_join_is_refused(guards):
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v, sh.zmara m WHERE v.mandt = '100'"
    )
    assert not verdict.ok, "FROM a, b without a condition is a cartesian product"
