"""Tracing: what must never reach it, and that its absence changes nothing.

The masking test is the one that matters. A trace holding what the guard rails
refused would be a second copy of the data with weaker access control, and the
way around the restrictions would be to read the traces instead of the tables.
"""

from __future__ import annotations

from sap_agent_mcp.tracing import MAX_ROWS, Tracing, build, mask


def test_an_email_is_redacted() -> None:
    assert "ivanov@example.com" not in mask("напиши на ivanov@example.com")
    assert "[почта скрыта]" in mask("напиши на ivanov@example.com")


def test_a_phone_number_is_redacted() -> None:
    assert "[телефон скрыт]" in mask("клиент просил перезвонить: +7 916 123-45-67")


def test_masking_reaches_into_dictionaries_and_lists() -> None:
    payload = {"question": "позвони на +7 916 123 45 67", "rows": [["ivanov@example.com"]]}
    masked = mask(payload)
    assert "916" not in str(masked)
    assert "ivanov@example.com" not in str(masked)


def test_rows_are_cut_rather_than_stored_whole() -> None:
    """A trace is for understanding a run. The answer lives in the result and in
    the journal, and copying it here would make the trace a data store."""
    masked = mask([[i] for i in range(100)])
    assert len(masked) == MAX_ROWS


def test_long_text_is_truncated() -> None:
    assert len(mask("a" * 10_000)) <= 4000


def test_without_keys_tracing_is_a_no_op_and_not_an_error(monkeypatch) -> None:
    for name in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    tracing = build()
    assert not tracing.enabled
    with tracing.tool("describe_schema", user_id="analyst-1") as span:
        span.output({"tables": 8})  # must not raise


def test_a_disabled_tracer_still_yields_a_usable_span() -> None:
    with Tracing(None).tool("propose_query", user_id="analyst-1") as span:
        span.set("sap.rows", 3)
        span.output("что угодно")
