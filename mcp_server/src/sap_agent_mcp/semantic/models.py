"""Typed contracts for the semantic layer.

The semantic layer is the core of this project: it is what turns MATNR into
"material number" and pins one definition of revenue. Everything downstream is
derived from it rather than written twice:

  * the allow list of tables, columns and joins comes from here,
  * the masking rules come from here,
  * describe_schema serves it to the agent verbatim.

One source of truth. A dictionary in YAML and a second list in code would
diverge within a week.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")]


class Strict(BaseModel):
    """Reject unknown keys everywhere.

    A typo in a YAML key must fail the load, not silently drop a masking rule.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    DATE = "date"


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Gotcha(Strict):
    """A trap an analyst knows and no schema records.

    Free Russian text on purpose. Formalising this would kill the point: the
    value is exactly the part that does not fit a schema.
    """

    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")]
    severity: Severity = Severity.WARNING
    text: Annotated[str, Field(min_length=10)]
    # What a query looks like when it walks into this trap, and what it should
    # look like instead. Both optional: some traps have no SQL shape.
    wrong: str | None = None
    right: str | None = None


class Column(Strict):
    name: Identifier
    title: Annotated[str, Field(min_length=1)]
    type: ColumnType
    description: str = ""
    # Part of the natural key of the table, used to explain grain.
    key: bool = False
    # Personal data. Never returned, never traced, never explained by example.
    pii: bool = False
    # Column holding the unit or currency this measure is expressed in.
    unit_column: Identifier | None = None
    # Values the column can take, when the set is small and worth stating.
    values: dict[str, str] = Field(default_factory=dict)
    # A filter that must be present in every query touching this table, given
    # as an SQL fragment relative to the column, e.g. "= '100'".
    required_filter: str | None = None
    # A filter that is right in almost every report but not always: excluding
    # rows flagged for deletion, for instance. A question about deleted records
    # is legitimate, so a missing default filter is a warning the analyst sees
    # on the approval card, not a refusal.
    default_filter: str | None = None

    @model_validator(mode="after")
    def _pii_columns_are_not_keys(self) -> Column:
        if self.pii and self.key:
            raise ValueError(
                f"column {self.name}: a masked column cannot be part of the key, "
                "joining on it would leak the value it hides"
            )
        return self


class JoinKey(Strict):
    left: Identifier
    right: Identifier


class Relation(Strict):
    """A join the agent is allowed to write. Anything else is refused.

    The join columns live under `join_on`, not `on`. YAML 1.1, which PyYAML
    implements, reads a bare `on` key as the boolean true, so `on:` in a YAML
    file never reaches this model as a string key. Renaming the field is
    cheaper than remembering to quote it in every table file forever.
    """

    to: Identifier
    kind: Literal["many_to_one", "one_to_many", "one_to_one"]
    join_on: Annotated[list[JoinKey], Field(min_length=1)]
    description: str = ""


class Table(Strict):
    name: Identifier
    title: Annotated[str, Field(min_length=1)]
    description: str = ""
    # What one row means. The single most useful sentence about a table and the
    # one most often missing.
    grain: Annotated[str, Field(min_length=5)]
    columns: Annotated[list[Column], Field(min_length=1)]
    relations: list[Relation] = Field(default_factory=list)
    gotchas: list[Gotcha] = Field(default_factory=list)
    typical_filters: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _column_names_are_unique(self) -> Table:
        names = [c.name.upper() for c in self.columns]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"table {self.name}: duplicate columns {sorted(duplicates)}")
        return self

    def column(self, name: str) -> Column | None:
        upper = name.upper()
        return next((c for c in self.columns if c.name.upper() == upper), None)

    @property
    def pii_columns(self) -> list[str]:
        return [c.name.upper() for c in self.columns if c.pii]


class Metric(Strict):
    """A measure with one agreed definition.

    The rule the agent follows: if a metric is declared, use it and do not
    invent an equivalent. If it is not declared, the answer must be marked as
    carrying a definition that is not from the dictionary.
    """

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
    title: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=10)]
    base_table: Identifier
    # The SQL expression, written against base_table and its declared relations.
    expression: Annotated[str, Field(min_length=3)]
    unit: str | None = None
    unit_column: str | None = None
    required_filters: list[str] = Field(default_factory=list)
    gotchas: list[Gotcha] = Field(default_factory=list)


class Domain(Strict):
    """One set of descriptions: bare SH tables, SAP-shaped views, later SFLIGHT.

    Domains are a list of directories rather than one file so a second subject
    area plugs in through configuration, without touching the server or the
    guard rails.
    """

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")]
    title: Annotated[str, Field(min_length=1)]
    db_schema: Identifier
    description: str = ""


class SemanticModel(Strict):
    """Everything loaded, ready to answer questions about itself."""

    domains: dict[str, Domain]
    tables: dict[str, Table]
    metrics: dict[str, Metric]
    # table name -> domain name
    table_domain: dict[str, str]

    @model_validator(mode="after")
    def _relations_and_metrics_point_at_known_tables(self) -> SemanticModel:
        known = set(self.tables)
        for table in self.tables.values():
            for relation in table.relations:
                target = relation.to.upper()
                if target not in known:
                    raise ValueError(
                        f"table {table.name}: relation to unknown table {relation.to}"
                    )
                other = self.tables[target]
                for key in relation.join_on:
                    if table.column(key.left) is None:
                        raise ValueError(
                            f"table {table.name}: join column {key.left} does not exist"
                        )
                    if other.column(key.right) is None:
                        raise ValueError(
                            f"table {table.name}: join column {other.name}.{key.right} "
                            "does not exist"
                        )
        for metric in self.metrics.values():
            if metric.base_table.upper() not in known:
                raise ValueError(
                    f"metric {metric.name}: unknown base table {metric.base_table}"
                )
        return self

    def qualified(self, table_name: str) -> str:
        """SCHEMA.TABLE, the only form the guard rails accept."""
        table = self.tables[table_name.upper()]
        domain = self.domains[self.table_domain[table.name.upper()]]
        return f"{domain.db_schema.upper()}.{table.name.upper()}"

    @property
    def allowed_tables(self) -> set[str]:
        return {self.qualified(name) for name in self.tables}

    @property
    def masked_columns(self) -> set[str]:
        """SCHEMA.TABLE.COLUMN for every column that must never be returned."""
        out: set[str] = set()
        for name, table in self.tables.items():
            for column in table.pii_columns:
                out.add(f"{self.qualified(name)}.{column}")
        return out
