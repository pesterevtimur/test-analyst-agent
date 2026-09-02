"""Load the semantic layer from a list of directories.

Sources are a list, not one file, so a second subject area (the SAP-shaped
views today, SFLIGHT later) plugs in through configuration without touching the
server or the guard rails.

Layout of one domain directory:

    <domain>/
      domain.yaml       name, title, db_schema
      tables/*.yaml     one table per file
      metrics.yaml      optional
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Domain, Metric, SemanticModel, Table


class SemanticError(Exception):
    """A semantic layer that fails to load stops the server.

    Deliberate: running with a half-loaded dictionary means an allow list with
    holes in it, and a hole in the allow list is the whole failure we are
    guarding against.
    """


def _read_yaml(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise SemanticError(f"{path}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SemanticError(f"{path}: expected a mapping at the top level")
    return data


def _fail(path: Path, what: str, exc: ValidationError) -> SemanticError:
    lines = [f"{path}: {what} does not match the contract:"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "(root)"
        lines.append(f"  {location}: {error['msg']}")
    return SemanticError("\n".join(lines))


def load_domain(directory: Path) -> tuple[Domain, list[Table], list[Metric]]:
    domain_file = directory / "domain.yaml"
    if not domain_file.is_file():
        raise SemanticError(f"{directory}: no domain.yaml")

    try:
        domain = Domain.model_validate(_read_yaml(domain_file))
    except ValidationError as exc:
        raise _fail(domain_file, "domain", exc) from exc

    tables_dir = directory / "tables"
    if not tables_dir.is_dir():
        raise SemanticError(f"{directory}: no tables/ directory")

    tables: list[Table] = []
    for path in sorted(tables_dir.glob("*.yaml")):
        try:
            table = Table.model_validate(_read_yaml(path))
        except ValidationError as exc:
            raise _fail(path, "table", exc) from exc
        if table.name.upper() != path.stem.upper():
            raise SemanticError(
                f"{path}: table is named {table.name} but the file is {path.stem}.yaml. "
                "Keep them equal so a table can be found by its name."
            )
        tables.append(table)

    if not tables:
        raise SemanticError(f"{tables_dir}: no table files")

    metrics: list[Metric] = []
    metrics_file = directory / "metrics.yaml"
    if metrics_file.is_file():
        raw = _read_yaml(metrics_file).get("metrics", [])
        if not isinstance(raw, list):
            raise SemanticError(f"{metrics_file}: 'metrics' must be a list")
        for item in raw:
            try:
                metrics.append(Metric.model_validate(item))
            except ValidationError as exc:
                raise _fail(metrics_file, "metric", exc) from exc

    return domain, tables, metrics


def load(sources: list[Path]) -> SemanticModel:
    domains: dict[str, Domain] = {}
    tables: dict[str, Table] = {}
    metrics: dict[str, Metric] = {}
    table_domain: dict[str, str] = {}

    if not sources:
        raise SemanticError("no semantic sources configured")

    for directory in sources:
        if not directory.is_dir():
            raise SemanticError(f"{directory}: not a directory")

        domain, domain_tables, domain_metrics = load_domain(directory)
        if domain.name in domains:
            raise SemanticError(f"domain {domain.name} is declared twice")
        domains[domain.name] = domain

        for table in domain_tables:
            key = table.name.upper()
            if key in tables:
                other = table_domain[key]
                raise SemanticError(
                    f"table {key} is declared in both {other} and {domain.name}. "
                    "Table names must be unique across domains, because the agent "
                    "refers to them by name alone."
                )
            tables[key] = table
            table_domain[key] = domain.name

        for metric in domain_metrics:
            if metric.name in metrics:
                raise SemanticError(f"metric {metric.name} is declared twice")
            metrics[metric.name] = metric

    try:
        return SemanticModel(
            domains=domains, tables=tables, metrics=metrics, table_domain=table_domain
        )
    except ValidationError as exc:
        raise SemanticError(f"the semantic layer is inconsistent: {exc}") from exc
