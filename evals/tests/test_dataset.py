"""What the reference set has to be true of itself.

These run without a database and without a model, so they belong to the fast CI
set (ADR-006). What they cannot check is whether a gold query returns the right
numbers; that is what freezing against the replica is for.
"""

from __future__ import annotations

from collections import Counter

from sap_agent_evals.dataset import Difficulty, Kind, load_dataset

DATASET = load_dataset()


def test_thirty_questions() -> None:
    assert len(DATASET.questions) == 30


def test_twenty_open_ten_sealed() -> None:
    assert len(DATASET.open) == 20
    assert len(DATASET.sealed) == 10


def test_six_traps() -> None:
    """SPEC section 8: six of the thirty are questions whose right answer is no."""
    assert len(DATASET.traps) == 6
    assert sum(1 for q in DATASET.traps if q.sealed) == 2


def test_every_difficulty_class_is_represented_in_both_subsets() -> None:
    for subset in (DATASET.open, DATASET.sealed):
        present = {q.difficulty for q in subset}
        assert present == set(Difficulty), present


def test_trap_types_cover_the_three_named_in_spec() -> None:
    kinds = {q.trap_type for q in DATASET.traps}
    # SPEC names three: out of allowlist, ambiguous wording, no answer in this
    # data. Personal data is the fourth, added because it is the one refusal
    # that must never be negotiable.
    assert {"ambiguous", "no-data", "pii", "out-of-scope"} == {str(k) for k in kinds}


def test_ids_are_unique_and_sorted_within_subsets() -> None:
    ids = [q.id for q in DATASET.questions]
    assert len(set(ids)) == len(ids)


def test_answerable_questions_carry_gold_sql_and_columns() -> None:
    for question in DATASET.answerable:
        assert question.gold_sql, question.id
        assert question.expect.measure_columns, question.id


def test_traps_carry_a_reason_and_forbidden_behaviour() -> None:
    for question in DATASET.traps:
        assert question.expect.refusal_reason.strip(), question.id
        assert question.expect.must_not, question.id
        assert question.expect.should_offer.strip(), question.id


def test_questions_are_written_in_business_language() -> None:
    """No table or column names in the question text.

    The mitigation from SPEC section 8: wording comes from the business, not from
    the semantic layer the agent reads. A question containing ZVBRP measures how
    well the agent copies, not how well it understands.
    """
    forbidden = (
        "ZVBRP", "ZKNA1", "ZMARA", "ZT005T", "ZTVTWT", "ZT009B", "WAKH", "ZKEKO",
        "NETWR", "MANDT", "LVORM", "AKTNR", "SELECT",
    )
    for question in DATASET.questions:
        text = question.question.upper()
        found = [word for word in forbidden if word in text]
        assert not found, f"{question.id}: {found}"


def test_documented_traps_of_the_semantic_layer_are_exercised() -> None:
    """Every critical gotcha in the dictionary is hit by at least one question."""
    from sap_agent_mcp.semantic.loader import load

    model = load(_semantic_sources())
    critical = {
        gotcha.id
        for table in model.tables.values()
        for gotcha in table.gotchas
        if gotcha.severity == "critical"
    } | {
        gotcha.id
        for metric in model.metrics.values()
        for gotcha in metric.gotchas
        if gotcha.severity == "critical"
    }
    covered = {name for question in DATASET.questions for name in question.gotchas}
    assert not (critical - covered), sorted(critical - covered)


def test_metrics_named_by_questions_exist_in_the_dictionary() -> None:
    from sap_agent_mcp.semantic.loader import load

    model = load(_semantic_sources())
    for question in DATASET.questions:
        for metric in question.metrics:
            assert metric in model.metrics, f"{question.id}: {metric}"


def test_difficulty_mix_is_not_lopsided() -> None:
    counts = Counter(q.difficulty for q in DATASET.questions)
    # Nothing here is a law; the point is that a set of thirty easy questions
    # would report an accuracy that means nothing.
    assert counts[Difficulty.SIMPLE] >= 8
    assert counts[Difficulty.MEDIUM] >= 8
    assert counts[Difficulty.COMPLEX] >= 5


def test_expected_tools_are_the_four_the_agent_has() -> None:
    allowed = {"describe_schema", "propose_query", "execute_query", "sanity_check"}
    for question in DATASET.questions:
        assert set(question.expected_tools) <= allowed, question.id
        assert "describe_schema" in question.expected_tools, question.id
        if question.kind is Kind.ANSWERABLE:
            assert "execute_query" in question.expected_tools, question.id


def _semantic_sources() -> list:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    return [root / "mcp_server" / "semantic" / "sap"]
