"""The MCP server: four tools, streamable HTTP, bound to the loopback interface.

Transport choice is deliberate and recorded in docs/adr/003-mcp-transport.md.
Over stdio the gateway starts one process per session, so the proposal queue,
the rate limiter and the journal would all be per session. With fifteen
analysts that means an approval nobody else can see and a limit anyone can
reset by opening a second session.

Identity comes from an HTTP header set by the gateway, never from a tool
argument. An agent that could name its own user could spend someone else's
quota and sign someone else's approval.
"""

from __future__ import annotations

import logging
import os
import sys

from mcp.server.mcpserver import Context, MCPServer

from .config import Settings
from .db import Database
from .guards import Guards
from .semantic import SemanticError, load
from .store import Store
from .tools import Tools

logger = logging.getLogger("sap_agent_mcp")

ANALYST_HEADER = "x-analyst-id"
TRACE_HEADER = "x-trace-id"

INSTRUCTIONS = """
Ты аналитик данных. У тебя есть ровно четыре инструмента и больше ничего:
ни оболочки, ни файлов, ни веба.

Порядок работы:
1. describe_schema, чтобы понять таблицы, поля, связи, ловушки и объявленные метрики.
2. propose_query, чтобы предложить SQL. Он проходит шесть проверок. Отказ приходит
   списком: читай, какая проверка не прошла, и исправляй запрос сам.
3. execute_query по идентификатору предложения. Если предложение ждёт подтверждения
   аналитика, дождись подтверждения, не пытайся обойти.
4. sanity_check, чтобы проверить результат на правдоподобие.

Правила:
- Если метрика объявлена в словаре, используй её выражение. Не считай по-своему.
- Если метрики нет, пиши выражение сам и обязательно пометь ответ строкой о том,
  что определение не из словаря.
- Пустой результат почти никогда не значит «нет данных». Проверь формат фильтра,
  подбивку номеров нулями и смысл признаков.
- В ответе всегда: таблица, короткое пояснение, как получено, чем ограничена
  интерпретация.
""".strip()


def build_server(settings: Settings) -> MCPServer:
    try:
        model = load(settings.semantic_sources)
    except SemanticError as exc:
        # A half-loaded dictionary means an allow list with holes in it, and a
        # hole in the allow list is the failure we are guarding against.
        print(f"Семантический слой не загрузился:\n{exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    logger.info(
        "semantic layer: %d tables, %d metrics from %s",
        len(model.tables), len(model.metrics),
        ", ".join(str(p) for p in settings.semantic_sources),
    )

    guards = Guards(model, max_rows=settings.limits.max_rows)
    store = Store(settings.state_path)
    database = Database(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=settings.oracle_dsn,
        max_sessions=settings.limits.max_concurrent_total,
    )
    tools = Tools(
        model=model, guards=guards, store=store, database=database,
        limits=settings.limits,
    )

    server = MCPServer(
        name="sap-agent",
        title="Данные Oracle и SAP только на чтение",
        instructions=INSTRUCTIONS,
        version="0.1.0",
    )

    def identity(context: Context) -> tuple[str, str | None]:
        """Who is asking, according to the gateway rather than the agent."""
        headers = {k.lower(): v for k, v in (context.headers or {}).items()}
        analyst = headers.get(ANALYST_HEADER) or os.environ.get("DEFAULT_ANALYST_ID")
        if not analyst:
            raise ValueError(
                f"Заголовок {ANALYST_HEADER} не передан и DEFAULT_ANALYST_ID не задан. "
                "Без личности вызывающего нельзя ни списать квоту, ни записать в журнал, "
                "поэтому запрос отклонён."
            )
        return analyst, headers.get(TRACE_HEADER)

    @server.tool(
        name="describe_schema",
        title="Описание таблиц и метрик",
        description=(
            "Возвращает семантический слой: таблицы, поля с человеческими названиями, "
            "ключи, разрешённые связи, ловушки и объявленные метрики. Вызывай первым, "
            "до сборки любого SQL. Без аргумента отдаёт всё."
        ),
    )
    async def describe_schema(context: Context, table: str | None = None) -> dict:
        analyst, _ = identity(context)
        return tools.describe_schema(table, user_id=analyst)

    @server.tool(
        name="propose_query",
        title="Предложить SQL",
        description=(
            "Прогоняет предложенный SQL через шесть проверок, оценивает объём через "
            "план выполнения и кладёт предложение в очередь. Возвращает идентификатор "
            "предложения и вердикт по каждой проверке. Ничего не выполняет."
        ),
    )
    async def propose_query(context: Context, question: str, sql: str) -> dict:
        analyst, trace = identity(context)
        return tools.propose_query(question, sql, user_id=analyst, trace_id=trace)

    @server.tool(
        name="execute_query",
        title="Выполнить подтверждённое предложение",
        description=(
            "Выполняет предложение по его идентификатору. SQL текстом не принимает: "
            "это и делает проверки обязательными. Работает только для подтверждённого "
            "или автоматически разрешённого предложения, и ровно один раз."
        ),
    )
    async def execute_query(context: Context, proposal_id: str) -> dict:
        analyst, trace = identity(context)
        return tools.execute_query(proposal_id, user_id=analyst, trace_id=trace)

    @server.tool(
        name="sanity_check",
        title="Проверка результата на правдоподобие",
        description=(
            "Проверяет полученный результат: пустой ответ, срез по пределу строк, "
            "полностью пустая колонка, отрицательные суммы, одинаковые значения "
            "после группировки. Не блокирует, а показывает, куда смотреть."
        ),
    )
    async def sanity_check(context: Context, result_id: str) -> dict:
        analyst, _ = identity(context)
        return tools.sanity_check(result_id, user_id=analyst)

    return server


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    server = build_server(settings)
    logger.info("listening on http://%s:%d/mcp", settings.host, settings.port)
    server.run(transport="streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
