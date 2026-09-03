"""How much of the agent's prompt is actually checked by something.

The rule from SPEC section 8: every instruction left in the prompt is numbered,
and every number has at least one test. An instruction without a test does not
work, it only eats context, and it gets deleted rather than believed.

Two kinds of cover count, and they are reported apart because they cost
different things:

    тест       a deterministic test, runs in CI on every push, free
    вопрос     a question in the reference set, runs against a real model

An instruction covered only by a reference question is covered, but nobody finds
out it broke until the next reference run. An instruction covered by neither is
a defect in the prompt.

Run:
    python evals/tools/instruction_coverage.py
    python evals/tools/instruction_coverage.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "evals" / "src")]

from sap_agent_evals.dataset import load_dataset  # noqa: E402

PROMPT = ROOT / "agent" / "AGENTS.md"
TEST_DIRECTORIES = [ROOT / "mcp_server" / "tests", ROOT / "evals" / "tests"]
MARKER = re.compile(r"INSTR-(\d+)")
DECLARATION = re.compile(r"^\*\*INSTR-(\d+)\.\*\*\s*(.+?)\s*$", re.MULTILINE)


def declared() -> dict[int, str]:
    text = PROMPT.read_text(encoding="utf-8")
    found = {int(number): body for number, body in DECLARATION.findall(text)}
    if not found:
        raise SystemExit(f"{PROMPT}: не нашёл ни одной пронумерованной инструкции")
    missing = sorted(set(range(1, max(found) + 1)) - set(found))
    if missing:
        raise SystemExit(
            "нумерация инструкций с дырами: нет "
            + ", ".join(f"INSTR-{n}" for n in missing)
            + ". Дыра означает, что инструкцию удалили, а ссылки на неё остались."
        )
    return found


def covered_by_tests() -> dict[int, list[str]]:
    cover: dict[int, list[str]] = {}
    for directory in TEST_DIRECTORIES:
        for path in sorted(directory.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for number in {int(n) for n in MARKER.findall(text)}:
                cover.setdefault(number, []).append(
                    str(path.relative_to(ROOT))
                )
    return cover


def covered_by_questions() -> dict[int, list[str]]:
    cover: dict[int, list[str]] = {}
    for question in load_dataset().questions:
        for name in question.instructions:
            number = int(MARKER.match(name).group(1))
            cover.setdefault(number, []).append(question.id)
    return cover


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    instructions = declared()
    by_test = covered_by_tests()
    by_question = covered_by_questions()

    rows = []
    for number in sorted(instructions):
        tests = sorted(set(by_test.get(number, [])))
        questions = sorted(set(by_question.get(number, [])))
        rows.append(
            {
                "instruction": f"INSTR-{number}",
                "text": instructions[number][:70],
                "tests": tests,
                "questions": questions,
                "covered": bool(tests or questions),
            }
        )

    uncovered = [row for row in rows if not row["covered"]]
    with_tests = [row for row in rows if row["tests"]]

    if args.json:
        print(json.dumps(
            {
                "declared": len(rows),
                "covered": len(rows) - len(uncovered),
                "covered_by_test": len(with_tests),
                "rows": rows,
            },
            ensure_ascii=False, indent=2,
        ))
    else:
        for row in rows:
            mark = "  " if row["covered"] else "!!"
            tests = f"тестов {len(row['tests'])}" if row["tests"] else "тестов нет"
            questions = (
                f"вопросов {len(row['questions'])}" if row["questions"] else "вопросов нет"
            )
            print(f"{mark} {row['instruction']:<9} {tests:<12} {questions:<14} {row['text']}")
        print()
        print(
            f"инструкций {len(rows)}, покрыто {len(rows) - len(uncovered)}, "
            f"из них детерминированным тестом {len(with_tests)}"
        )

    if uncovered:
        print(
            "\nбез проверки: "
            + ", ".join(row["instruction"] for row in uncovered)
            + ". Инструкция без теста удаляется из промпта, а не остаётся в нём.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
