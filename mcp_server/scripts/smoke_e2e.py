"""End-to-end check of the MCP server against the real database.

Walks the whole chain the way the agent will: describe, propose, execute,
sanity check. Also tries the two things that must fail, so the run proves the
guard rails rather than only the happy path.

Run:
    docker run --rm --network host -v "$PWD/scripts:/s:ro" sap-agent-mcp:dev \
        python /s/smoke_e2e.py http://127.0.0.1:8080/mcp
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

QUESTION = "Выручка по странам за второй квартал 2021 года, топ-5"
GOOD_SQL = """
SELECT t.landx AS country, SUM(v.netwr) AS revenue, v.waerk AS currency
FROM sh.zvbrp v
JOIN sh.zkna1 k ON k.kunnr = v.kunnr AND k.mandt = v.mandt
JOIN sh.zt005t t ON t.land1 = k.land1 AND t.mandt = k.mandt AND t.spras = 'E'
JOIN sh.zt009b p ON p.budat = v.fkdat AND p.mandt = v.mandt
WHERE v.mandt = '100' AND k.lvorm = ' ' AND p.quartal = '2021-02'
GROUP BY t.landx, v.waerk
ORDER BY revenue DESC
FETCH FIRST 5 ROWS ONLY
"""


def payload(result) -> dict:
    if getattr(result, "structuredContent", None):
        content = result.structuredContent
        return content.get("result", content) if isinstance(content, dict) else content
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise AssertionError("tool returned nothing readable")


async def main(url: str) -> int:
    # HTTP headers are ASCII only, so the identity travelling in the header is a
    # login, not a display name. The readable name belongs in the panel, keyed by
    # this login.
    headers = {"x-analyst-id": "lead-analyst", "x-trace-id": "smoke-1"}
    failures: list[str] = []

    async with httpx2.AsyncClient(headers=headers, timeout=120) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                names = sorted(t.name for t in tools.tools)
                print("1. инструменты:", ", ".join(names))
                if names != ["describe_schema", "execute_query", "propose_query", "sanity_check"]:
                    failures.append(f"неожиданный набор инструментов: {names}")

                schema = payload(await session.call_tool("describe_schema", {}))
                print(f"2. словарь: таблиц {len(schema['tables'])}, "
                      f"метрик {len(schema['metrics'])}")
                masked = [
                    f"{t['name']}.{c['name']}"
                    for t in schema["tables"] for c in t["columns"] if c["masked"]
                ]
                print("   помечено как персональные:", ", ".join(masked))
                if not masked:
                    failures.append("словарь не помечает ни одного персонального поля")

                print("3. отказ: запись в базу")
                blocked = payload(await session.call_tool(
                    "propose_query", {"question": "удалить продажи", "sql": "DELETE FROM sh.zvbrp"}
                ))
                print("  ", blocked.get("error"), "|", blocked.get("detail", "")[:90])
                if blocked.get("ok", True):
                    failures.append("запись в базу не была отклонена")

                print("4. отказ: персональные данные")
                pii = payload(await session.call_tool(
                    "propose_query",
                    {"question": "телефоны клиентов",
                     "sql": "SELECT k.telf1 FROM sh.zkna1 k WHERE k.mandt = '100'"},
                ))
                print("  ", pii.get("error"), "|", pii.get("detail", "")[:90])
                if pii.get("ok", True):
                    failures.append("запрос персональных данных не был отклонён")

                print("5. предложение по настоящему вопросу")
                proposal = payload(await session.call_tool(
                    "propose_query", {"question": QUESTION, "sql": GOOD_SQL}
                ))
                if not proposal.get("ok"):
                    print("   ОТКАЗ:", proposal.get("detail"))
                    failures.append("корректный запрос отклонён")
                    return _report(failures)
                print(f"   id={proposal['proposal_id']} политика={proposal['policy']}")
                print(f"   оценка строк={proposal['estimated_rows']} "
                      f"стоимость={proposal['estimated_cost']}")
                print("   проверки:")
                for check in proposal["checks"]:
                    print(f"     [{check['status']}] {check['title']}: {check['detail'][:70]}")
                print("   план:")
                for line in proposal["plan"][:6]:
                    print("    ", line)

                print("6. выполнение")
                if proposal["policy"] == "pending":
                    print("   предложение ждёт подтверждения аналитика, подтверждаю в хранилище")
                    from sap_agent_mcp.config import Settings  # noqa: PLC0415
                    from sap_agent_mcp.store import ProposalStatus, Store  # noqa: PLC0415
                    store = Store(Settings.from_env().state_path)
                    store.decide(proposal["proposal_id"], status=ProposalStatus.APPROVED,
                                 by="lead-analyst", note="проверка сквозного пути")

                run = payload(await session.call_tool(
                    "execute_query", {"proposal_id": proposal["proposal_id"]}
                ))
                if not run.get("ok"):
                    print("   ОТКАЗ:", run.get("error"), run.get("detail"))
                    failures.append("выполнение подтверждённого предложения не прошло")
                    return _report(failures)
                print(f"   строк {run['row_count']}, {run['duration_ms']} мс")
                for row in run["rows"]:
                    print("    ", row)

                print("7. повторное выполнение того же предложения")
                again = payload(await session.call_tool(
                    "execute_query", {"proposal_id": proposal["proposal_id"]}
                ))
                print("  ", again.get("error"), "|", again.get("detail", "")[:90])
                if again.get("ok", True):
                    failures.append("предложение выполнилось дважды")

                print("8. проверка правдоподобия")
                sanity = payload(await session.call_tool(
                    "sanity_check", {"result_id": run["result_id"]}
                ))
                print("   вердикт:", sanity["worst"])
                for observation in sanity["observations"]:
                    print(f"     [{observation['level']}] {observation['text'][:100]}")

    return _report(failures)


def _report(failures: list[str]) -> int:
    print()
    if failures:
        print("ПРОВАЛЫ:")
        for failure in failures:
            print(" -", failure)
        return 1
    print("сквозной путь пройден, все отказы сработали")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/mcp")))
