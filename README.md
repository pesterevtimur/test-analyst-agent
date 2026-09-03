# Агент-аналитик над данными Oracle и SAP

Аналитик получает вопрос от бизнеса на обычном языке. Агент читает семантический слой, собирает SQL и отдаёт его на проверку: шесть детерминированных ограничителей, оценка объёма по плану выполнения, подтверждение аналитика в панели. Выполняет только подтверждённое, ровно один раз, и объясняет результат.

Владелец ответа остаётся аналитиком. Агент снимает механическую часть.

```
бизнес --> аналитик --> агент --> MCP-сервер --> отчётная реплика Oracle
                          |            |
                          |        ограничители, очередь, журнал
                          |            |
                       ответ <--- подтверждение в панели
```

## Что где лежит

| Каталог | Что внутри |
|---|---|
| `SPEC.md` | источник истины по содержанию |
| `mcp_server/` | четыре инструмента, шесть ограничителей, семантический слой |
| `agent/` | системная инструкция агента и конфигурация OpenClaw |
| `control_panel/` | панель: очередь, история, лимиты, эталонный набор |
| `evals/` | 30 вопросов, сравнение по результату, судья, траектория, давление |
| `infra/` | compose, установка Oracle, конфигурация трассировки |
| `docs/` | требования, границы, проверка, процесс, экономика, ADR |

## Запуск за десять минут

Нужны: docker с compose v2, git, python3, около 20 ГБ на диске и 4 ГБ свободной памяти.

**1. Секреты.**

```bash
cp .env.example .env
$EDITOR .env    # пароли Oracle, ключ модели, пароль панели
```

Всё, что в `.env`, наружу не уходит: файл в `.gitignore`, в git попадает только пример.

**2. Данные примера.**

```bash
bash infra/oracle/prepare.sh
```

Скачивает схему Sales History из `oracle-samples/db-sample-schemas`. В git она не лежит: один только `sales.csv` весит 71 МБ.

**3. База, сервер, панель.**

```bash
cd infra && docker compose --env-file ../.env up -d
```

Первый запуск ставит схему, снимает отчётную реплику, строит восемь представлений в именах SAP, заводит читающего пользователя и собирает статистику. Это занимает несколько минут, дальше запуск секундный.

Проверить, что данные на месте:

```bash
set -a && . ./.env && set +a
docker run --rm --network host -v "$PWD/infra/oracle:/w:ro" \
    -e ORACLE_APP_USER -e ORACLE_APP_USER_PASSWORD -e ORACLE_DSN \
    python:3.12-slim sh -c "pip install -q oracledb && python /w/smoke_check.py"
```

**4. Трассировка (необязательно).**

```bash
cd infra/observability
docker compose --env-file ../../.env -f langfuse-upstream.yml -f langfuse-override.yml up -d
```

Шесть контейнеров, около 2 ГБ памяти. Проект и ключи создаются сами из `LANGFUSE_INIT_*` в `.env`. Без этого шага сервер работает так же: трассировка выключается отсутствием ключей и не может уронить то, что наблюдает.

**5. Агент.**

```bash
openclaw config patch --file agent/openclaw-provider.json5
openclaw config patch --file agent/openclaw-agent.json5
cp agent/AGENTS.md ~/.openclaw/workspace/AGENTS.md
```

Подключение MCP-сервера к OpenClaw описано в `docs/process.md`.

## Куда смотреть

| Что | Адрес | Как открыть снаружи |
|---|---|---|
| Панель аналитика | http://127.0.0.1:8081 | `ssh -L 8081:127.0.0.1:8081 <сервер>` |
| Трассы Langfuse | http://127.0.0.1:3000 | `ssh -L 3000:127.0.0.1:3000 <сервер>` |
| MCP-сервер | http://127.0.0.1:8080/mcp | не открывается, только для агента |

Наружу не слушает ничего, кроме ssh. Это решение, а не недоделка.

## Проверки

Быстрый набор, без базы и без модели, идёт в CI на каждый push:

```bash
docker run --rm -v "$PWD:/w" -w /w \
    -e PYTHONPATH=/w/mcp_server/src:/w/evals/src:/w/control_panel/src \
    sap-agent-panel:dev python -m pytest mcp_server/tests evals/tests control_panel/tests -q
```

Замер 3 сентября 2026: 440 тестов за 5,6 секунды.

Сквозная проверка MCP на живой базе, включая то, что обязано не пройти:

```bash
set -a && . ./.env && set +a
docker run --rm --network host \
    -v "$PWD/mcp_server/scripts:/s:ro" -v sap-agent_mcp-state:/state \
    -e ORACLE_APP_USER -e ORACLE_APP_USER_PASSWORD \
    -e ORACLE_DSN=127.0.0.1:1521/REPPDB1 -e STATE_PATH=/state/sap-agent.db \
    sap-agent-mcp:dev python /s/smoke_e2e.py http://127.0.0.1:8080/mcp
```

Проверка ходит в очередь предложений, поэтому ей нужны и доступ к базе, и том с состоянием: она подтверждает предложение так, как это сделал бы аналитик, а потом пробует выполнить его второй раз и ждёт отказа.

Эталонные ответы и покрытие инструкций:

```bash
docker run --rm -v "$PWD:/w" -w /w -e PYTHONPATH=/w/mcp_server/src:/w/evals/src \
    sap-agent-mcp:dev sh -c "python evals/tools/freeze_gold.py --check && \
                             python evals/tools/instruction_coverage.py"
```

## Что читать дальше

- `docs/process.md`: как устроен путь вопроса от бизнеса до ответа.
- `docs/verification.md`: как измеряется качество и почему именно так.
- `docs/economics.md`: польза в часах и деньгах, с таблицами чувствительности.
- `docs/limits.md`: чего этот стенд не умеет.
- `docs/not-done.md`: что не сделано и почему.
- `docs/adr/`: принятые решения, каждое с альтернативами и последствиями.

## Границы стенда, коротко

Данные учебные. Аутентификации нет, один пароль на панель. Всё на одной машине. Точность измеряется на наборе, который написал автор агента, и смягчения этого смещения перечислены в `docs/verification.md`.
