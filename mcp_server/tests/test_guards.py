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
    assert len(verdict.checks) == 6
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
        "default-filters",
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


# --- row limits in both Oracle spellings -------------------------------------

def test_fetch_first_is_recognised_as_a_limit(guards):
    """Oracle spells it FETCH FIRST n ROWS ONLY, and sqlglot parses it into a
    different node than LIMIT. Reading only one shape threw the analyst's own
    limit away and answered a different question."""
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v WHERE v.mandt = '100' FETCH FIRST 5 ROWS ONLY"
    )
    assert verdict.ok
    assert verdict.row_limit == 5
    assert verdict.limit_added is False
    assert "5" in verdict.sql


def test_an_oversized_fetch_first_is_capped(guards):
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v WHERE v.mandt = '100' FETCH FIRST 99999 ROWS ONLY"
    )
    assert verdict.ok
    assert verdict.row_limit == 1000
    assert verdict.limit_added is True


def test_an_added_limit_is_rendered_in_oracle_syntax(guards):
    verdict = guards.check("SELECT v.netwr FROM sh.zvbrp v WHERE v.mandt = '100'")
    assert "FETCH FIRST 1000 ROWS ONLY" in verdict.sql.upper()


def test_a_non_numeric_limit_falls_back_to_the_ceiling(guards):
    """A limit that is not a plain number cannot be trusted to be small."""
    verdict = guards.check(
        "SELECT v.netwr FROM sh.zvbrp v WHERE v.mandt = '100' FETCH FIRST :n ROWS ONLY"
    )
    assert verdict.row_limit == 1000
    assert verdict.limit_added is True


# --- filters that are expected but not mandatory ------------------------------

def test_a_missing_deletion_filter_warns_without_blocking(guards):
    """The agent read this trap in the dictionary and wrote the query without it
    anyway, which is why the check exists. It warns rather than refuses, because
    a question about deleted records is legitimate."""
    verdict = guards.check(
        "SELECT COUNT(*) FROM sh.zkna1 k WHERE k.mandt = '100'"
    )
    assert verdict.ok, "a missing default filter must not block the query"
    warned = {c.id for c in verdict.warnings}
    assert "default-filters" in warned
    detail = next(c.detail for c in verdict.warnings)
    assert "LVORM" in detail
    assert "подтвердите" in detail


def test_the_deletion_filter_present_passes_quietly(guards):
    verdict = guards.check(
        "SELECT COUNT(*) FROM sh.zkna1 k WHERE k.mandt = '100' AND k.lvorm = ' '"
    )
    assert verdict.ok
    assert not verdict.warnings


def test_a_default_filter_written_in_the_join_also_counts(guards):
    verdict = guards.check(
        "SELECT SUM(v.netwr) FROM sh.zvbrp v "
        "JOIN sh.zkna1 k ON k.kunnr = v.kunnr AND k.mandt = v.mandt AND k.lvorm = ' ' "
        "WHERE v.mandt = '100'"
    )
    assert verdict.ok
    assert not verdict.warnings


def test_a_warning_is_reported_separately_from_a_failure(guards):
    verdict = guards.check("SELECT COUNT(*) FROM sh.zkna1 k WHERE k.mandt = '100'")
    assert verdict.failures == []
    assert len(verdict.warnings) == 1


# --- filters the dictionary declares mandatory --------------------------------

def test_a_query_without_the_client_filter_is_refused(guards):
    """INSTR-4. Moved out of the prompt into the guard rails on day 4: the client
    field is checkable without a model, and an instruction the model can forget
    is not a boundary. Reading another landscape's rows is not a question anybody
    legitimately asks, so this fails instead of warning."""
    verdict = guards.check("SELECT SUM(v.netwr) FROM sh.zvbrp v")
    assert not verdict.ok
    assert "default-filters" in failed_ids(verdict)
    detail = next(c.detail for c in verdict.failures)
    assert "MANDT" in detail
    assert "чужого контура" in detail


def test_the_client_filter_is_required_on_every_table_in_the_query(guards):
    """One table filtered and the other not is the same hole, harder to see."""
    verdict = guards.check(
        "SELECT SUM(v.netwr) FROM sh.zvbrp v "
        "JOIN sh.zmara m ON m.matnr = v.matnr "
        "WHERE v.mandt = '100' AND m.lvorm = ' '"
    )
    assert not verdict.ok
    assert "default-filters" in failed_ids(verdict)
    assert "ZMARA.MANDT" in next(c.detail for c in verdict.failures)


def test_the_client_filter_carried_by_a_join_counts(guards):
    """A filter travels along an equality: m.mandt = v.mandt plus one literal
    constrains both tables, and demanding the literal twice would be theatre."""
    verdict = guards.check(
        "SELECT SUM(v.netwr) FROM sh.zvbrp v "
        "JOIN sh.zmara m ON m.matnr = v.matnr AND m.mandt = v.mandt "
        "WHERE v.mandt = '100' AND m.lvorm = ' '"
    )
    assert verdict.ok, [c.detail for c in verdict.failures]


def test_the_client_filter_is_checked_inside_subqueries_too(guards):
    verdict = guards.check(
        "SELECT COUNT(*) AS customers FROM ("
        "  SELECT DISTINCT v.kunnr AS kunnr FROM sh.zvbrp v WHERE v.mandt = '100'"
        "  MINUS"
        "  SELECT DISTINCT v.kunnr AS kunnr FROM sh.zvbrp v WHERE v.fkdat > DATE '2022-01-01'"
        ")"
    )
    assert not verdict.ok
    assert "default-filters" in failed_ids(verdict)


def test_a_missing_required_filter_outranks_a_missing_default_one(guards):
    """Both wrong at once reports the blocking one: the agent must fix that first,
    and a warning next to a refusal reads as advice about a query that never ran."""
    verdict = guards.check("SELECT COUNT(*) FROM sh.zkna1 k")
    assert not verdict.ok
    assert "default-filters" in failed_ids(verdict)
    assert verdict.warnings == []
