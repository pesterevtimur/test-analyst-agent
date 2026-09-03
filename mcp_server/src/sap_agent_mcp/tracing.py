"""Traces to Langfuse over OTLP, and nothing personal in them.

Two rules shape this file.

Masking happens before the write, not after. A trace that holds what the guard
rails refused is a second copy of the data with weaker access control, and then
the way around the restrictions is to read the traces.

Tracing is optional at runtime. Without keys the tracer is a no-op, so tests,
CI and a laptop without Langfuse run the same code path as production. An
observability layer that can stop the server is worse than no observability.

Transport is OTLP over HTTP, which is the supported path into Langfuse; the
legacy ingestion API is deprecated (checked 3 September 2026 against
langfuse.com/integrations/native/opentelemetry).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# Values that must never reach a trace even if they arrive inside free text: a
# business question can be typed with a customer's phone number in it.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s()-]?){10,15}(?!\d)")

# How much of a payload is worth keeping. A trace is for understanding a run,
# not for storing the answer: the answer is in the journal and in the result.
MAX_TEXT = 4000
MAX_ROWS = 5


def mask(value: Any) -> Any:
    """Redact anything that looks personal, at any depth."""
    if isinstance(value, str):
        redacted = _EMAIL.sub("[почта скрыта]", value)
        redacted = _PHONE.sub("[телефон скрыт]", redacted)
        return redacted[:MAX_TEXT]
    if isinstance(value, dict):
        return {key: mask(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(item) for item in value[:MAX_ROWS]]
    return value


def _json(value: Any) -> str:
    return json.dumps(mask(value), ensure_ascii=False, default=str)[: MAX_TEXT * 2]


class Tracing:
    """A tracer that either sends spans to Langfuse or does nothing at all."""

    def __init__(self, tracer: Any | None = None) -> None:
        self._tracer = tracer

    @property
    def enabled(self) -> bool:
        return self._tracer is not None

    @contextmanager
    def tool(
        self,
        name: str,
        *,
        user_id: str,
        trace_id: str | None = None,
        input: Any = None,
    ) -> Iterator["Span"]:
        if self._tracer is None:
            yield Span(None)
            return

        with self._tracer.start_as_current_span(name) as span:
            span.set_attribute("langfuse.user.id", user_id)
            # The session is the thread of one question: the messenger message,
            # the MCP calls, the row in SQLite and the card in the panel all
            # carry it, which is what makes a run reconstructable end to end.
            if trace_id:
                span.set_attribute("langfuse.session.id", trace_id)
            if input is not None:
                span.set_attribute("langfuse.observation.input", _json(input))
            yield Span(span)


class Span:
    def __init__(self, span: Any | None) -> None:
        self._span = span

    def output(self, value: Any) -> None:
        if self._span is not None:
            self._span.set_attribute("langfuse.observation.output", _json(value))

    def set(self, key: str, value: Any) -> None:
        if self._span is not None and value is not None:
            self._span.set_attribute(key, value)


def build(
    *,
    host: str | None = None,
    public_key: str | None = None,
    secret_key: str | None = None,
    service: str = "sap-agent-mcp",
) -> Tracing:
    """Build a tracer, or a no-op when the keys or the libraries are missing."""
    host = host or os.environ.get("LANGFUSE_HOST")
    public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")

    if not (host and public_key and secret_key):
        logger.info("tracing off: LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY or "
                    "LANGFUSE_SECRET_KEY is not set")
        return Tracing(None)

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:  # pragma: no cover - depends on the image
        logger.warning("tracing off: %s", exc)
        return Tracing(None)

    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    exporter = OTLPSpanExporter(
        endpoint=f"{host.rstrip('/')}/api/public/otel/v1/traces",
        headers={
            "Authorization": f"Basic {auth}",
            "x-langfuse-ingestion-version": "4",
        },
        timeout=10,
    )
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.info("tracing on: %s", host)
    return Tracing(trace.get_tracer(service))
