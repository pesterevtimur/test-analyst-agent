"""Comparing an answer to the gold answer, by result and not by SQL text.

The mode is lenient with one hard edge, and both halves come from ADR-001 and
ADR-007:

    row order          ignored
    extra columns      allowed
    column names       ignored, columns are matched by their contents
    numbers            equal within 0.5% relative
    missing rows       error
    extra rows         error

The extra row is where this differs from the usual lenient comparison. An extra
row means a filter that did not fire, and a filter that did not fire puts
somebody else's data into an answer that goes to the business. For reporting
that is worse than an answer that is short.

Matching columns by contents rather than by name came from the first reference
run, 3 September. The agent answered "23 765 506,62 USD" correctly and scored
zero because it had aliased the column REVENUE_2021 instead of REVENUE. Nobody
ever told it which alias to use, and requiring one would measure obedience to an
unwritten convention rather than the answer. So a declared column is looked up
by name first and by its values second: the key column whose values are the same
set, the measure whose numbers agree row by row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Sequence

from .dataset import Expectation

# Values below this are treated as zero: floating point noise must not read as
# a wrong number, and no measure in this domain is meaningful at 1e-9.
ZERO = 1e-9


@dataclass(frozen=True)
class Table:
    """A result set, from either side of the comparison."""

    columns: list[str]
    rows: list[list[Any]]

    @classmethod
    def of(cls, columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> Table:
        return cls(
            columns=[str(c).strip().upper() for c in columns],
            rows=[list(row) for row in rows],
        )

    def index(self, column: str) -> int:
        try:
            return self.columns.index(column.upper())
        except ValueError as exc:
            raise KeyError(column) from exc

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class Mismatch:
    key: str
    column: str
    expected: Any
    actual: Any
    relative_difference: float | None

    def __str__(self) -> str:
        where = f"[{self.key}] " if self.key else ""
        if self.relative_difference is None:
            return f"{where}{self.column}: ожидалось {self.expected!r}, получено {self.actual!r}"
        return (
            f"{where}{self.column}: ожидалось {self.expected}, получено {self.actual}, "
            f"расхождение {self.relative_difference * 100:.3f}%"
        )


@dataclass
class Comparison:
    ok: bool = True
    missing_columns: list[str] = field(default_factory=list)
    missing_rows: list[str] = field(default_factory=list)
    extra_rows: list[str] = field(default_factory=list)
    duplicate_keys: list[str] = field(default_factory=list)
    mismatches: list[Mismatch] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return "совпало"
        parts: list[str] = []
        if self.missing_columns:
            parts.append("нет колонок: " + ", ".join(self.missing_columns))
        if self.duplicate_keys:
            parts.append(
                "ключ повторяется, строки задвоены: " + ", ".join(self.duplicate_keys[:5])
            )
        if self.missing_rows:
            parts.append(f"недостаёт строк: {len(self.missing_rows)} "
                         f"({', '.join(self.missing_rows[:5])})")
        if self.extra_rows:
            parts.append(f"лишние строки: {len(self.extra_rows)} "
                         f"({', '.join(self.extra_rows[:5])})")
        if self.mismatches:
            parts.append(
                f"расходятся значения: {len(self.mismatches)} "
                f"({'; '.join(str(m) for m in self.mismatches[:3])})"
            )
        return ". ".join(parts) if parts else "не совпало"


def _key_value(value: Any) -> str:
    """One canonical spelling for a key, so 03 and '03' are the same bucket."""
    if value is None:
        return "∅"
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10] if isinstance(value, date) else value.isoformat()
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, bool):
        return str(value)
    return str(value).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        return None if math.isnan(number) else number
    if isinstance(value, str):
        try:
            return float(value.replace(" ", "").replace(",", "."))
        except ValueError:
            return None
    return None


def _relative_difference(expected: float, actual: float) -> float:
    scale = max(abs(expected), abs(actual))
    if scale < ZERO:
        return 0.0
    return abs(expected - actual) / scale


def _values(table: Table, column: str) -> list[Any]:
    position = table.index(column)
    return [row[position] for row in table.rows]


def _match_key_column(expected: Table, actual: Table, column: str,
                      taken: set[str]) -> str | None:
    """Колонка ответа, где стоят ровно те же ключи, что и в эталоне."""
    wanted = sorted(_key_value(value) for value in _values(expected, column))
    for candidate in actual.columns:
        if candidate in taken:
            continue
        got = sorted(_key_value(value) for value in _values(actual, candidate))
        if got == wanted:
            return candidate
    return None


def _match_measure_column(
    expected_rows: dict[str, dict[str, Any]],
    actual: Table,
    column: str,
    keys: list[str],
    taken: set[str],
    tolerance: float,
) -> str | None:
    """Колонка ответа, чьи числа сходятся с эталонными построчно."""
    key_positions = [actual.index(k) for k in keys]
    for candidate in actual.columns:
        if candidate in taken:
            continue
        position = actual.index(candidate)
        matched = True
        for row in actual.rows:
            key = " | ".join(_key_value(row[p]) for p in key_positions)
            if key not in expected_rows:
                matched = False
                break
            gold = expected_rows[key][column]
            if _compare_value(key, column, gold, row[position], tolerance) is not None:
                matched = False
                break
        if matched:
            return candidate
    return None


def compare(expected: Table, actual: Table, expectation: Expectation) -> Comparison:
    """Compare one result set to another under the rules above."""
    result = Comparison()
    keys = [c.upper() for c in expectation.key_columns]
    measures = [c.upper() for c in expectation.measure_columns]

    # Имена колонок ответа никто не задавал, поэтому объявленная колонка ищется
    # сначала по имени, а потом по содержимому. Найденное соответствие живёт
    # только внутри сравнения: эталон продолжает называть колонки своими именами.
    taken: set[str] = set()
    renamed: dict[str, str] = {}
    missing: list[str] = []
    for column in keys:
        if column in actual.columns:
            renamed[column] = column
        else:
            found = _match_key_column(expected, actual, column, taken)
            if found is None:
                missing.append(column)
                continue
            renamed[column] = found
            result.notes.append(f"ключ {column} сопоставлен с колонкой {found} по значениям")
        taken.add(renamed[column])

    if missing:
        result.ok = False
        result.missing_columns = missing
        return result

    expected_rows = _bucket(expected, keys, measures, result, side="эталон")
    if not result.ok:
        return result

    actual_keys = [renamed[c] for c in keys]
    for column in measures:
        if column in actual.columns:
            renamed[column] = column
        else:
            found = _match_measure_column(
                expected_rows, actual, column, actual_keys, taken,
                expectation.tolerance,
            )
            if found is None:
                missing.append(column)
                continue
            renamed[column] = found
            result.notes.append(f"мера {column} сопоставлена с колонкой {found} по значениям")
        taken.add(renamed[column])

    if missing:
        result.ok = False
        result.missing_columns = missing
        return result

    # Ответ приводится к именам эталона, дальше сравнение идёт как раньше.
    reverse = {renamed[c]: c for c in keys + measures}
    actual = Table(
        columns=[reverse.get(c, c) for c in actual.columns],
        rows=actual.rows,
    )

    actual_rows = _bucket(actual, keys, measures, result, side="ответ")
    if not result.ok:
        return result

    for key in sorted(set(expected_rows) - set(actual_rows)):
        result.ok = False
        result.missing_rows.append(key or "единственная строка")

    for key in sorted(set(actual_rows) - set(expected_rows)):
        # ADR-007: an extra row is an error, not a rounding difference.
        result.ok = False
        result.extra_rows.append(key or "единственная строка")

    for key in sorted(set(expected_rows) & set(actual_rows)):
        for column in measures:
            gold = expected_rows[key][column]
            got = actual_rows[key][column]
            mismatch = _compare_value(key, column, gold, got, expectation.tolerance)
            if mismatch is not None:
                result.ok = False
                result.mismatches.append(mismatch)

    return result


def _compare_value(
    key: str, column: str, expected: Any, actual: Any, tolerance: float
) -> Mismatch | None:
    gold = _number(expected)
    got = _number(actual)

    if gold is None or got is None:
        # At least one side is not a number: compare as text. NULL equals NULL,
        # because "no rows matched this bucket" is a real answer.
        if _key_value(expected) == _key_value(actual):
            return None
        return Mismatch(key, column, expected, actual, None)

    difference = _relative_difference(gold, got)
    if difference <= tolerance:
        return None
    return Mismatch(key, column, gold, got, difference)


def _bucket(
    table: Table,
    keys: list[str],
    measures: list[str],
    result: Comparison,
    *,
    side: str,
) -> dict[str, dict[str, Any]]:
    """Rows keyed by their key columns; the empty key means a single-row answer."""
    buckets: dict[str, dict[str, Any]] = {}
    key_positions = [table.index(c) for c in keys] if keys else []
    measure_positions = {c: table.index(c) for c in measures}

    if not keys and table.row_count > 1:
        # No key columns means the question has one answer. Several rows mean the
        # grouping is wrong, which is a different answer, not a formatting issue.
        result.ok = False
        result.notes.append(
            f"{side}: строк {table.row_count}, а ключевых колонок нет. "
            "Вопрос предполагает одну строку."
        )
        if side == "ответ":
            result.extra_rows.append(f"лишних строк {table.row_count - 1}")
        return {}

    for row in table.rows:
        key = " | ".join(_key_value(row[position]) for position in key_positions)
        if key in buckets:
            result.ok = False
            result.duplicate_keys.append(f"{side}: {key or 'единственная строка'}")
            continue
        buckets[key] = {c: row[position] for c, position in measure_positions.items()}

    return buckets
