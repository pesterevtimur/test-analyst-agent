# Отчёты прогонов

Что здесь лежит:

- `report-*.json`: оценённый прогон: метрики, разбор каждого вопроса, ответ агента, вердикт сравнения, траектория. Коммитится.
- `raw-*.json`: сырьё прогона до оценки. В git не идёт (крупное и воспроизводимое), но именно из него пересчитывается оценка, когда меняются правила сравнения.
- `*.md`: сводка прогона для человека.

## Как читать метрики

| Метрика | Что означает |
|---|---|
| `accuracy_by_result` | доля отвечаемых вопросов, где результат сошёлся с эталоном |
| `accuracy_by_difficulty` | то же по классам сложности из финансовой модели |
| `traps_refused_correctly` | доля ловушек, где агент отказался, а не выдумал |
| `trajectory_conformance` | доля прогонов, где путь соответствовал ожидаемому |
| `judge_deterministic_pass` | доля ответов, прошедших проверки пояснения без модели |
| `diagnoses` | разбор промахов: не выполнено, неверные числа, другой набор строк, другая форма результата |
| `cost_usd_per_question` | замеренная стоимость вопроса |

`diagnoses` важнее общей точности при разборе. «Не выполнено» и «неверные числа» это разные болезни с разным лечением, и складывать их в одну цифру значит лечить наугад.

## Как получить

```bash
set -a && . ./.env && set +a
export DEEPSEEK_API_KEY="$LLM_API_KEY"
python3 evals/tools/run_reference.py --subset open        # рабочие вопросы
python3 evals/tools/run_reference.py --pressure           # сценарии давления
python3 evals/tools/run_reference.py --subset sealed      # один раз, перед сдачей

docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/w" -w /w \
    -e PYTHONPATH=/w/mcp_server/src:/w/evals/src \
    sap-agent-mcp:dev python evals/tools/grade_reference.py \
    evals/reports/raw-open-<...>.json
```
