"""Settings, read once from the environment.

Every limit has a default that is safe rather than convenient: a missing
environment variable must not silently widen a limit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _paths(name: str, default: list[str]) -> list[Path]:
    raw = os.environ.get(name)
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()] or default
    return [Path(p) for p in parts]


@dataclass(frozen=True)
class Limits:
    """Three layers, because counting requests guards against frequency and not
    against weight: one sixty-second query hurts as much as a hundred light ones."""

    # Token bucket per user.
    refill_per_minute: float = 1.0
    bucket_size: int = 5
    daily_cap: int = 100
    # Concurrency. The global ceiling matters more than the per-user one: the
    # sum of per-user limits is always larger than the database can take.
    max_concurrent_per_user: int = 2
    max_concurrent_total: int = 6
    # Per query.
    max_rows: int = 1000
    query_timeout_seconds: int = 30
    # Auto-execution policy: anything larger waits for an analyst.
    auto_max_rows: int = 200
    auto_max_tables: int = 3


@dataclass(frozen=True)
class Settings:
    oracle_user: str
    oracle_password: str
    oracle_dsn: str
    semantic_sources: list[Path]
    state_path: Path
    host: str = "127.0.0.1"
    port: int = 8080
    limits: Limits = field(default_factory=Limits)

    @classmethod
    def from_env(cls) -> Settings:
        try:
            password = os.environ["ORACLE_APP_USER_PASSWORD"]
        except KeyError as exc:
            raise RuntimeError(
                "ORACLE_APP_USER_PASSWORD is not set. The server refuses to start "
                "rather than fall back to a default credential."
            ) from exc

        return cls(
            oracle_user=os.environ.get("ORACLE_APP_USER", "agent_ro"),
            oracle_password=password,
            oracle_dsn=os.environ.get("ORACLE_DSN", "127.0.0.1:1521/FREEPDB1"),
            semantic_sources=_paths("SEMANTIC_SOURCES", ["semantic/sap"]),
            state_path=Path(os.environ.get("STATE_PATH", "state/sap-agent.db")),
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=_int("MCP_PORT", 8080),
            limits=Limits(
                refill_per_minute=float(os.environ.get("LIMIT_REFILL_PER_MINUTE", "1")),
                bucket_size=_int("LIMIT_BUCKET_SIZE", 5),
                daily_cap=_int("LIMIT_DAILY_CAP", 100),
                max_concurrent_per_user=_int("LIMIT_CONCURRENT_PER_USER", 2),
                max_concurrent_total=_int("LIMIT_CONCURRENT_TOTAL", 6),
                max_rows=_int("LIMIT_MAX_ROWS", 1000),
                query_timeout_seconds=_int("LIMIT_QUERY_TIMEOUT_SECONDS", 30),
                auto_max_rows=_int("POLICY_AUTO_MAX_ROWS", 200),
                auto_max_tables=_int("POLICY_AUTO_MAX_TABLES", 3),
            ),
        )
