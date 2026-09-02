"""Tests for the semantic layer contracts and loader.

The semantic layer is the single source for the allow list and the masking
rules, so a hole here is a hole in the guard rails. These tests check the
contract refuses bad input, not only that good input loads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from sap_agent_mcp.semantic import SemanticError, Table, load, load_domain

REPO_SEMANTIC = Path(__file__).resolve().parents[1] / "semantic"


# --- the real semantic layer ------------------------------------------------

@pytest.fixture(scope="module")
def model():
    return load([REPO_SEMANTIC / "sap"])


def test_the_shipped_layer_loads(model):
    assert set(model.domains) == {"sap"}
    assert len(model.tables) == 8
    assert "ZVBRP" in model.tables


def test_every_table_has_a_grain_sentence(model):
    for table in model.tables.values():
        assert len(table.grain) > 20, f"{table.name}: grain is too vague to help"


def test_every_column_has_a_russian_title(model):
    for table in model.tables.values():
        for column in table.columns:
            assert column.title, f"{table.name}.{column.name}: no title"
            assert column.title != column.name, (
                f"{table.name}.{column.name}: the title just repeats the technical "
                "name, which is exactly what the semantic layer exists to avoid"
            )


def test_personal_columns_are_marked_and_none_are_keys(model):
    masked = model.masked_columns
    assert "SH.ZKNA1.TELF1" in masked
    assert "SH.ZKNA1.SMTP_ADDR" in masked
    assert "SH.ZKNA1.NAME1" in masked
    # The brief masks name, phone and email. Nothing else may be masked by
    # accident, because a masked column silently disappears from answers.
    assert masked == {
        "SH.ZKNA1.NAME1",
        "SH.ZKNA1.STRAS",
        "SH.ZKNA1.TELF1",
        "SH.ZKNA1.SMTP_ADDR",
    }


def test_allowed_tables_are_schema_qualified(model):
    assert model.qualified("zvbrp") == "SH.ZVBRP"
    assert all(name.startswith("SH.") for name in model.allowed_tables)


def test_mandt_is_a_required_filter_on_every_table(model):
    for table in model.tables.values():
        mandt = table.column("MANDT")
        assert mandt is not None, f"{table.name}: no MANDT column"
        assert mandt.required_filter, (
            f"{table.name}: MANDT has no required filter, so the client trap is "
            "documented nowhere"
        )


def test_metrics_reference_known_tables_and_carry_filters(model):
    assert "revenue" in model.metrics
    for metric in model.metrics.values():
        assert metric.base_table.upper() in model.tables
        assert metric.required_filters, (
            f"metric {metric.name}: no required filters, so the client filter can "
            "be forgotten silently"
        )


def test_critical_traps_are_present(model):
    """The traps found by measurement, not by reading column names."""
    ids = {
        gotcha.id
        for table in model.tables.values()
        for gotcha in table.gotchas
    } | {
        gotcha.id
        for metric in model.metrics.values()
        for gotcha in metric.gotchas
    }
    for required in (
        "matnr-padding",        # join on an unpadded number returns nothing
        "lvorm-inverted",       # the flag we mapped backwards on 2026-09-02
        "quartal-format",       # '2021-02' is a quarter, not a month
        "promo-placeholder",    # 0000000999 means "no promotion"
        "cost-grain-explosion", # joining costs on material alone doubles rows
    ):
        assert required in ids, f"trap {required} is not recorded anywhere"


# --- the contract refuses bad input -----------------------------------------

def _minimal_table(**overrides) -> dict:
    data = {
        "name": "T1",
        "title": "Таблица",
        "grain": "одна строка это одна запись",
        "columns": [{"name": "C1", "title": "Колонка", "type": "string"}],
    }
    data.update(overrides)
    return data


def test_unknown_key_is_rejected():
    with pytest.raises(ValidationError):
        Table.model_validate(_minimal_table(colums=[]))


def test_masked_column_cannot_be_a_key():
    with pytest.raises(ValidationError, match="cannot be part of the key"):
        Table.model_validate(
            _minimal_table(
                columns=[{"name": "C1", "title": "К", "type": "string",
                          "pii": True, "key": True}]
            )
        )


def test_duplicate_columns_are_rejected():
    with pytest.raises(ValidationError, match="duplicate columns"):
        Table.model_validate(
            _minimal_table(
                columns=[
                    {"name": "C1", "title": "К", "type": "string"},
                    {"name": "c1", "title": "К", "type": "string"},
                ]
            )
        )


def test_relation_to_unknown_table_is_rejected(tmp_path):
    domain = tmp_path / "d"
    (domain / "tables").mkdir(parents=True)
    (domain / "domain.yaml").write_text(
        yaml.safe_dump({"name": "demo", "title": "D", "db_schema": "SH"}), encoding="utf-8"
    )
    (domain / "tables" / "t1.yaml").write_text(
        yaml.safe_dump(
            _minimal_table(
                name="T1",
                relations=[{"to": "NOPE", "kind": "many_to_one",
                            "join_on": [{"left": "C1", "right": "C1"}]}],
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(SemanticError, match="relation to unknown table"):
        load([domain])


def test_file_name_must_match_table_name(tmp_path):
    domain = tmp_path / "d"
    (domain / "tables").mkdir(parents=True)
    (domain / "domain.yaml").write_text(
        yaml.safe_dump({"name": "demo", "title": "D", "db_schema": "SH"}), encoding="utf-8"
    )
    (domain / "tables" / "wrong.yaml").write_text(
        yaml.safe_dump(_minimal_table(name="T1")), encoding="utf-8"
    )
    with pytest.raises(SemanticError, match="but the file is"):
        load_domain(domain)


def test_missing_domain_file_is_an_error(tmp_path):
    (tmp_path / "tables").mkdir()
    with pytest.raises(SemanticError, match="no domain.yaml"):
        load_domain(tmp_path)
