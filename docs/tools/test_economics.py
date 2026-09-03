"""Модель пользы и текст, который её пересказывает, обязаны сходиться.

Документ с числами и скрипт, который их считает, расходятся по одному сценарию:
кто-то правит допущение, перезапускает скрипт, смотрит на новый вывод и забывает
поправить одну таблицу из пяти. Дальше в презентацию уезжает число, которого
модель уже не даёт.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs" / "tools"))

from economics import (  # noqa: E402
    Inputs,
    contribution,
    model,
    sensitivity_medium,
    sensitivity_mix,
    sensitivity_review_time,
)

DOCUMENT = (ROOT / "docs" / "economics.md").read_text(encoding="utf-8")
INPUTS = Inputs()
COMPUTED = model(INPUTS)


def spaced(value: float) -> str:
    """Рубли в документе пишутся с неразрывными пробелами по три знака."""
    return f"{round(value):,}".replace(",", " ")


def test_the_headline_numbers_are_the_ones_the_model_gives() -> None:
    assert f"{COMPUTED['questions_per_week_before']:.0f}" in DOCUMENT
    assert f"{COMPUTED['questions_per_week_after']:.0f}" in DOCUMENT
    assert f"{COMPUTED['throughput_gain'] * 100:.0f} процент" in DOCUMENT
    assert spaced(COMPUTED["money_saved_per_month_rub"]) in DOCUMENT


def test_the_wait_in_the_queue_matches() -> None:
    assert f"{COMPUTED['wait_after_months']:.0f}" in DOCUMENT


def test_every_sensitivity_row_appears_in_the_document() -> None:
    for row in sensitivity_review_time(INPUTS):
        assert spaced(row["money_per_month_rub"]) in DOCUMENT, row
    for row in sensitivity_medium(INPUTS):
        assert spaced(row["money_per_month_rub"]) in DOCUMENT, row
    for row in sensitivity_mix(INPUTS):
        assert spaced(row["money_per_month_rub"]) in DOCUMENT, row


def test_the_benefit_survives_the_worst_assumption_about_the_medium_class() -> None:
    """Если на среднем классе агент не помогает вовсе, польза обязана остаться
    положительной: иначе вывод «польза есть» держится на одном допущении."""
    worst = min(sensitivity_medium(INPUTS), key=lambda row: row["gain_percent"])
    assert worst["gain_percent"] > 0
    assert f"{worst['gain_percent']}%" in DOCUMENT or f"{worst['gain_percent']} процент" in DOCUMENT


def test_the_shares_of_the_benefit_add_up() -> None:
    assert abs(sum(row["share_of_benefit"] for row in contribution(INPUTS)) - 1) < 0.01


def test_the_medium_class_is_where_most_of_the_saving_is() -> None:
    """Утверждение документа, а не догадка: проверяется, а не пересказывается."""
    rows = {row["class"]: row["share_of_benefit"] for row in contribution(INPUTS)}
    assert rows["средний"] > rows["простой"] + rows["сложный"]


def test_the_model_costs_three_orders_less_than_the_hours_it_saves() -> None:
    assert COMPUTED["cost_ratio"] > 1000
