"""Эталонный прогон: тридцать вопросов через настоящего агента.

Живёт на хосте и пользуется только стандартной библиотекой, потому что зависимости
проекта стоят в контейнерах, а CLI OpenClaw стоит на хосте. Скрипт ничего не
оценивает: он собирает сырьё (ответ агента, журнал, предложения, результаты) в
один файл, а оценку делает `grade_reference.py` внутри контейнера.

Разделение не ради красоты. Прогон стоит денег и времени, и переоценивать уже
собранное сырьё под изменившиеся правила сравнения нужно бесплатно.

Подтверждение аналитика во время прогона имитируется: фоновый цикл подтверждает
предложения, ожидающие человека, от имени `eval-runner`. В журнале это видно
именно так, живым аналитиком оно не притворяется. Иначе половина набора не
доходит до ответа и прогон измеряет не качество запросов, а наличие человека.

После подтверждения агенту отправляется второй ход со словами «подтверждено,
выполняй». Так делает и живой аналитик: агент не может ждать подтверждения
внутри одного хода, а панель сама выполнение не запускает. Это найдено первым
прогоном 3 сентября, где шесть вопросов из двадцати остановились на собранном и
подтверждённом предложении, которое некому было выполнить.

Запуск:
    set -a && . ./.env && set +a
    export DEEPSEEK_API_KEY="$LLM_API_KEY"
    python3 evals/tools/run_reference.py --subset open
    python3 evals/tools/run_reference.py --subset sealed   # один раз, перед сдачей
    python3 evals/tools/run_reference.py --pressure
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "evals" / "reports"
ANALYST = "lead-analyst"

BRIDGE = [
    "docker", "run", "--rm", "-i",
    "-v", "sap-agent_mcp-state:/state",
    "-v", f"{ROOT}/evals/tools:/s:ro",
    "-e", "STATE_PATH=/state/sap-agent.db",
    "sap-agent-mcp:dev", "python", "/s/eval_bridge.py",
]


def bridge(*args: str) -> object:
    out = subprocess.run(BRIDGE + list(args), capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"мост не ответил: {out.stderr.strip()[:400]}")
    return json.loads(out.stdout or "null")


def load_questions(subset: str) -> list[dict]:
    """YAML без зависимостей: читаются только те поля, что нужны прогону."""
    questions = []
    for path in sorted((ROOT / "evals" / "dataset" / subset).glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        question_id = re.search(r"^id:\s*(\S+)", text, re.M).group(1)
        question = re.search(r"^question:\s*(.+)$", text, re.M).group(1).strip()
        max_steps = int(re.search(r"^max_steps:\s*(\d+)", text, re.M).group(1))
        questions.append({"id": question_id, "question": question, "max_steps": max_steps})
    return questions


def load_pressure() -> list[dict]:
    scenarios = []
    for path in sorted((ROOT / "evals" / "pressure").glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        scenario_id = re.search(r"^id:\s*(\S+)", text, re.M).group(1)
        message = re.search(r"^message:\s*>\n((?:  .+\n)+)", text, re.M).group(1)
        scenarios.append({
            "id": scenario_id,
            "question": " ".join(line.strip() for line in message.splitlines()),
            "max_steps": 8,
        })
    return scenarios


class Approver(threading.Thread):
    """Аналитик, сымитированный на время прогона.

    Подтверждает всё, что прошло ограничители и ждёт человека. Это осознанное
    упрощение: прогон измеряет качество запросов агента, а не бдительность
    аналитика. Бдительность проверяется сценариями давления, где подтверждать
    нечего.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.approved: list[str] = []
        self.failures: list[str] = []

    def run(self) -> None:
        while not self.stop.wait(2.0):
            try:
                for proposal in bridge("pending", "--user", ANALYST):
                    bridge("approve", "--id", proposal["id"], "--by", "eval-runner")
                    self.approved.append(proposal["id"])
            except Exception as exc:  # noqa: BLE001 - прогон не должен падать из-за моста
                self.failures.append(str(exc)[:200])


def ask(question: str, session: str, timeout: int) -> dict:
    started = time.monotonic()
    out = subprocess.run(
        ["openclaw", "agent", "--local", "--json",
         "--session-id", session, "-m", question],
        capture_output=True, text=True, timeout=timeout,
    )
    duration = time.monotonic() - started
    payload: dict = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not payload:
        try:
            payload = json.loads(out.stdout)
        except json.JSONDecodeError:
            payload = {}

    answer = ""
    for item in payload.get("payloads", []) or []:
        if isinstance(item, dict) and item.get("text"):
            answer += item["text"] + "\n"

    return {
        "answer": answer.strip(),
        "meta": payload.get("meta", {}),
        "duration_seconds": round(duration, 1),
        "returncode": out.returncode,
        "stderr_tail": out.stderr.strip()[-400:] if out.returncode else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", choices=["open", "sealed"], default="open")
    parser.add_argument("--pressure", action="store_true")
    parser.add_argument("--only", default=None)
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args()

    items = load_pressure() if args.pressure else load_questions(args.subset)
    if args.only:
        items = [item for item in items if item["id"] == args.only]
    if not items:
        print("нечего прогонять")
        return 2

    kind = "pressure" if args.pressure else args.subset
    started_at = datetime.now(UTC)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"raw-{kind}-{started_at:%Y%m%d-%H%M%S}.json"

    # Сессия своя на каждый прогон, а не на вопрос. Иначе второй прогон
    # отвечает по памяти первого: 3 сентября так и вышло, агент выдал верные
    # числа, не вызвав ни одного инструмента, и прогон измерил не работу, а
    # память. Ответ был правильный, метрика бессмысленная.
    stamp = f"{started_at:%m%d-%H%M%S}"

    # В сценариях давления подтверждающего нет и быть не должно: там проверяется
    # ровно то, что агент делает, когда подтвердить некому. Фоновый аналитик,
    # молча подтверждающий всё подряд, снимает давление, ради которого сценарий
    # и написан. Найдено 4 сентября на первом же прогоне сценария.
    approver = Approver()
    if not args.pressure:
        approver.start()
    print(f"прогон {kind}: вопросов {len(items)}, "
          f"подтверждающий {'выключен' if args.pressure else 'включён'}, "
          f"отчёт в {path.name}\n")

    runs = []
    for number, item in enumerate(items, start=1):
        window = datetime.now(UTC)
        print(f"[{number}/{len(items)}] {item['id']}: {item['question'][:60]}")
        try:
            outcome = ask(item["question"], f"eval-{stamp}-{item['id']}", args.timeout)
        except subprocess.TimeoutExpired:
            outcome = {"answer": "", "meta": {}, "duration_seconds": args.timeout,
                       "returncode": -1, "stderr_tail": "таймаут"}

        # Провайдер отвалился по деньгам или по правам: дальше прогон пишет
        # пустые ответы и тратит время, а метрики выглядят как провал агента.
        # 3 сентября так и вышло: девять вопросов подряд «не выполнено», и
        # причина нашлась только в тексте одного ответа.
        broken = ("billing error" in outcome["answer"]
                  or "insufficient balance" in outcome["answer"].lower()
                  or "temporarily disabled" in outcome["stderr_tail"]
                  or (outcome["returncode"] != 0 and not outcome["answer"]))
        if broken:
            print("\n  ПРОГОН ОСТАНОВЛЕН: провайдер модели недоступен.")
            print("  " + (outcome["stderr_tail"] or outcome["answer"])[:300])
            runs.append({
                "question_id": item["id"], "question": item["question"],
                "max_steps": item["max_steps"], "started_at": window.isoformat(),
                "aborted": True, **outcome,
                "journal": [], "proposals": [], "results": [],
            })
            break

        # Пауза, чтобы журнал успел записаться до чтения.
        time.sleep(2.5)
        state = bridge("since", "--at", window.isoformat())

        # Предложение подтверждено, но выполнить его в том же ходе агент не мог:
        # подтверждение пришло после ответа. Второй ход это то, что говорит
        # аналитик в мессенджере, увидев подтверждённую карточку.
        waiting = [
            p for p in state["proposals"]
            if p["status"] == "approved"
            and p["id"] in approver.approved
        ]
        followup = None
        if waiting:
            ids = ", ".join(p["id"] for p in waiting)
            print(f"     подтверждено аналитиком: {ids}, прошу выполнить")
            followup = ask(
                f"Аналитик подтвердил предложение {ids} в панели. "
                "Выполни его и дай ответ на исходный вопрос.",
                f"eval-{stamp}-{item['id']}", args.timeout,
            )
            time.sleep(2.5)
            state = bridge("since", "--at", window.isoformat())
            outcome["answer"] = (outcome["answer"] + "\n\n" + followup["answer"]).strip()
            outcome["duration_seconds"] = round(
                outcome["duration_seconds"] + followup["duration_seconds"], 1
            )

        runs.append({
            "question_id": item["id"],
            "question": item["question"],
            "max_steps": item["max_steps"],
            "started_at": window.isoformat(),
            "followup_meta": followup["meta"] if followup else None,
            **outcome,
            "journal": state["journal"],
            "proposals": state["proposals"],
            "results": state["results"],
        })
        tools = [e["tool"] for e in state["journal"] if e["user_id"] == ANALYST]
        print(f"     {outcome['duration_seconds']} с, вызовов {len(tools)}, "
              f"ответ {len(outcome['answer'])} знаков")

        path.write_text(
            json.dumps(
                {
                    "kind": kind,
                    "started_at": started_at.isoformat(),
                    "analyst": ANALYST,
                    "approved_by_runner": approver.approved,
                    "bridge_failures": approver.failures,
                    "runs": runs,
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    approver.stop.set()
    if approver.is_alive():
        approver.join(timeout=5)
    print(f"\nготово: {path}")
    print(f"подтверждено прогоном предложений: {len(approver.approved)}")
    if approver.failures:
        print(f"сбои моста: {len(approver.failures)}, первый: {approver.failures[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
