"""Guard rails that run before any SQL reaches the database.

Six deterministic checks, no model involved. This is the layer that does not
depend on the prompt, the model or the vendor: whatever the agent proposes, it
passes here or it does not run.

The verdict is a list, not a boolean. An agent told only "rejected" can do
nothing but guess; an agent told which check failed and why can fix its own
query. The same list is what the analyst sees on the approval card.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated

import sqlglot
from pydantic import BaseModel, ConfigDict, Field
from sqlglot import exp
from sqlglot.errors import ParseError, OptimizeError
from sqlglot.optimizer.qualify import qualify

from .semantic.models import SemanticModel

DIALECT = "oracle"

# Statements that read. Anything else is refused outright rather than inspected,
# because a list of allowed shapes is safe to get wrong in only one direction.
_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Except, exp.Intersect)


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class Check(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    status: Status
    detail: str

    @property
    def failed(self) -> bool:
        return self.status is Status.FAILED


class Verdict(BaseModel):
    """The result of all six checks, plus what the query turned out to touch."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    checks: list[Check]
    sql: str
    tables: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    row_limit: int | None = None
    limit_added: bool = False

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.failed]


def _limit_value(node: exp.Expression | None) -> int | None:
    """The row count from either LIMIT n or FETCH FIRST n ROWS ONLY."""
    if node is None:
        return None
    if isinstance(node, exp.Fetch):
        count = node.args.get("count")
    else:
        count = node.args.get("expression")
    if isinstance(count, exp.Literal) and count.is_int:
        return int(count.name)
    # A limit that is not a plain number (a bind variable, an expression) is
    # treated as absent, so the ceiling is applied rather than assumed.
    return None


def _make_limit(rows: int) -> exp.Fetch:
    """Oracle spells a row limit FETCH FIRST n ROWS ONLY."""
    return exp.Fetch(
        direction="FIRST",
        count=exp.Literal.number(rows),
        limit_options=exp.LimitOptions(percent=False, rows=True, with_ties=False),
    )


def _passed(check_id: str, title: str, detail: str) -> Check:
    return Check(id=check_id, title=title, status=Status.PASSED, detail=detail)


def _failed(check_id: str, title: str, detail: str) -> Check:
    return Check(id=check_id, title=title, status=Status.FAILED, detail=detail)


def sqlglot_schema(model: SemanticModel) -> dict:
    """The semantic layer expressed the way sqlglot wants it, for name resolution.

    Types are approximate on purpose: this schema exists to resolve which table
    a bare column belongs to, not to type-check expressions.
    """
    schema: dict[str, dict[str, dict[str, str]]] = {}
    for name, table in model.tables.items():
        db = model.domains[model.table_domain[name]].db_schema.upper()
        columns = {
            column.name.upper(): {
                "string": "VARCHAR",
                "number": "NUMBER",
                "date": "DATE",
            }[column.type]
            for column in table.columns
        }
        schema.setdefault(db, {})[name] = columns
    return schema


class Guards:
    def __init__(self, model: SemanticModel, max_rows: int = 1000) -> None:
        self.model = model
        self.max_rows = max_rows
        self._schema = sqlglot_schema(model)

    # -- check 1 --------------------------------------------------------------

    def _check_read_only(self, sql: str) -> tuple[Check, exp.Expression | None]:
        title = "Только чтение, одна инструкция"
        stripped = sql.strip().rstrip(";").strip()
        if not stripped:
            return _failed("read-only", title, "Запрос пустой."), None
        try:
            statements = sqlglot.parse(stripped, read=DIALECT)
        except ParseError as exc:
            message = str(exc).splitlines()[0]
            return _failed("read-only", title, f"Запрос не разбирается: {message}"), None

        statements = [s for s in statements if s is not None]
        if len(statements) != 1:
            return (
                _failed(
                    "read-only",
                    title,
                    f"Ожидается ровно одна инструкция, найдено {len(statements)}. "
                    "Несколько инструкций через точку с запятой не выполняются.",
                ),
                None,
            )

        statement = statements[0]
        if not isinstance(statement, _ALLOWED_ROOTS):
            kind = type(statement).__name__.upper()
            return (
                _failed(
                    "read-only",
                    title,
                    f"Разрешён только SELECT, получено {kind}. "
                    "Запись в базу невозможна ни при каких условиях.",
                ),
                None,
            )

        # A SELECT can still hide a write: Oracle allows INSERT inside a CTE in
        # some shapes, and functions can have side effects. Refuse anything that
        # contains a write node anywhere in the tree.
        writes = [
            node
            for node in statement.walk()
            if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Merge,
                                 exp.Create, exp.Drop, exp.Alter, exp.Command))
        ]
        if writes:
            kinds = sorted({type(node).__name__.upper() for node in writes})
            return (
                _failed(
                    "read-only",
                    title,
                    f"Внутри запроса найдены изменяющие конструкции: {', '.join(kinds)}.",
                ),
                None,
            )

        return _passed("read-only", title, "Одна инструкция, только чтение."), statement

    # -- check 2 --------------------------------------------------------------

    def _check_allowlist(
        self, statement: exp.Expression
    ) -> tuple[Check, exp.Expression | None, list[str], list[str]]:
        title = "Таблицы и колонки из списка разрешённых"
        allowed = self.model.allowed_tables

        used: list[str] = []
        for table in statement.find_all(exp.Table):
            name = table.name.upper()
            db = (table.db or "").upper()
            qualified = f"{db}.{name}" if db else name
            used.append(qualified)

        unqualified = sorted({t for t in used if "." not in t})
        if unqualified:
            return (
                _failed(
                    "allowlist",
                    title,
                    "Таблицы указаны без схемы: "
                    + ", ".join(unqualified)
                    + ". Пишите SH.ZVBRP, иначе непонятно, к какой схеме запрос.",
                ),
                None,
                [],
                [],
            )

        unknown = sorted({t for t in used if t not in allowed})
        if unknown:
            return (
                _failed(
                    "allowlist",
                    title,
                    "Вне списка разрешённых: "
                    + ", ".join(unknown)
                    + ". Доступны: "
                    + ", ".join(sorted(allowed))
                    + ".",
                ),
                None,
                [],
                [],
            )

        # Resolve every bare column to its table. This both validates column
        # names and gives the masking check something exact to work with.
        try:
            resolved = qualify(
                statement.copy(),
                schema=self._schema,
                dialect=DIALECT,
                qualify_columns=True,
                validate_qualify_columns=True,
                infer_schema=False,
            )
        except (OptimizeError, sqlglot.errors.SqlglotError) as exc:
            return (
                _failed(
                    "allowlist",
                    title,
                    f"Колонки не разрешаются по словарю: {str(exc).splitlines()[0]}",
                ),
                None,
                [],
                [],
            )

        columns = sorted(
            {
                f"{self._table_of(resolved, column)}.{column.name.upper()}"
                for column in resolved.find_all(exp.Column)
                if column.name != "*"
            }
        )
        return (
            _passed(
                "allowlist",
                title,
                f"Таблиц {len(set(used))}, колонок {len(columns)}, все в словаре.",
            ),
            resolved,
            sorted(set(used)),
            columns,
        )

    @staticmethod
    def _table_of(resolved: exp.Expression, column: exp.Column) -> str:
        """Map a qualified column back to SCHEMA.TABLE using the query's aliases."""
        alias = (column.table or "").upper()
        for table in resolved.find_all(exp.Table):
            name = table.alias_or_name.upper()
            if name == alias:
                return f"{(table.db or '').upper()}.{table.name.upper()}"
        return alias

    # -- check 3 --------------------------------------------------------------

    def _check_masking(self, columns: list[str]) -> Check:
        title = "Персональные данные не запрашиваются"
        masked = self.model.masked_columns
        hits = sorted(set(columns) & masked)
        if hits:
            return _failed(
                "masking",
                title,
                "Запрошены персональные поля: "
                + ", ".join(hits)
                + ". Они не выдаются никогда, ни в результате, ни в трассе.",
            )
        return _passed("masking", title, "Персональных полей в запросе нет.")

    # -- check 4 --------------------------------------------------------------

    def _check_row_limit(
        self, statement: exp.Expression
    ) -> tuple[Check, exp.Expression, int, bool]:
        title = "Ограничение числа строк"

        # sqlglot stores both shapes under args["limit"]: an exp.Limit for
        # LIMIT n and an exp.Fetch for Oracle's FETCH FIRST n ROWS ONLY. Reading
        # only the first shape silently threw away the analyst's own limit, so a
        # request for the top five came back with everything. Caught by the
        # end-to-end run on 2026-09-02.
        existing = statement.args.get("limit")
        current = _limit_value(existing)

        if current is None:
            statement.set("limit", _make_limit(self.max_rows))
            return (
                _passed(
                    "row-limit",
                    title,
                    f"Ограничение отсутствовало и добавлено: {self.max_rows} строк.",
                ),
                statement,
                self.max_rows,
                True,
            )

        if current > self.max_rows:
            statement.set("limit", _make_limit(self.max_rows))
            return (
                _passed(
                    "row-limit",
                    title,
                    f"Запрошено {current} строк, срезано до предела {self.max_rows}.",
                ),
                statement,
                self.max_rows,
                True,
            )

        return (
            _passed("row-limit", title, f"Ограничение задано в запросе: {current} строк."),
            statement,
            current,
            False,
        )

    # -- check 5 --------------------------------------------------------------

    def _check_joins(self, resolved: exp.Expression) -> Check:
        title = "Соединения только из объявленных связей"
        declared: set[frozenset[str]] = set()
        for name, table in self.model.tables.items():
            left_q = self.model.qualified(name)
            for relation in table.relations:
                declared.add(frozenset({left_q, self.model.qualified(relation.to)}))

        joins = list(resolved.find_all(exp.Join))
        checked = 0

        for join in joins:
            on = join.args.get("on")
            if on is None:
                return _failed(
                    "joins",
                    title,
                    "Найдено соединение без условия. Декартово произведение "
                    "запрещено: на таблице фактов это миллиарды строк.",
                )

            # Pairs of tables actually related by an equality inside this join.
            pairs: set[frozenset[str]] = set()
            for equality in on.find_all(exp.EQ):
                sides = {
                    self._table_of(resolved, column)
                    for column in equality.find_all(exp.Column)
                }
                if len(sides) == 2:
                    pairs.add(frozenset(sides))

            if not pairs:
                # A condition exists but relates no two tables: ON 1 = 1, or a
                # join whose condition only filters one side. Same cartesian
                # product as no condition at all, just harder to spot.
                return _failed(
                    "joins",
                    title,
                    "Условие соединения не связывает таблицы между собой "
                    f"(например ON 1 = 1): {on.sql(dialect=DIALECT)}. "
                    "Это то же декартово произведение.",
                )

            undeclared = sorted(
                " + ".join(sorted(pair)) for pair in pairs - declared
            )
            if undeclared:
                return _failed(
                    "joins",
                    title,
                    "Соединения, которых нет в словаре: "
                    + "; ".join(undeclared)
                    + ". Разрешённые связи описаны в семантическом слое.",
                )
            checked += len(pairs)

        return _passed(
            "joins", title, f"Соединений {len(joins)}, связей {checked}, все из словаря."
        )

    # -- entry point ----------------------------------------------------------

    def check(self, sql: str) -> Verdict:
        """Run every check. Later checks are skipped only when their input is missing."""
        checks: list[Check] = []

        read_only, statement = self._check_read_only(sql)
        checks.append(read_only)
        if statement is None:
            return Verdict(ok=False, checks=checks, sql=sql)

        allowlist, resolved, tables, columns = self._check_allowlist(statement)
        checks.append(allowlist)
        if resolved is None:
            return Verdict(ok=False, checks=checks, sql=sql)

        checks.append(self._check_masking(columns))
        checks.append(self._check_joins(resolved))

        row_limit_check, limited, row_limit, added = self._check_row_limit(statement)
        checks.append(row_limit_check)

        normalized = limited.sql(dialect=DIALECT, pretty=True)
        ok = not any(check.failed for check in checks)
        return Verdict(
            ok=ok,
            checks=checks,
            sql=normalized,
            tables=tables,
            columns=columns,
            row_limit=row_limit,
            limit_added=added,
        )
