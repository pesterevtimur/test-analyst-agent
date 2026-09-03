"""Grading the explanation the analyst reads, not the number.

Two layers, and the split matters more than either half.

Deterministic rules first: does the answer carry the numbers that came back,
the moment the data describes, how it was obtained, and does it avoid calling an
empty result a zero. These cost nothing, run in CI, and cover the part of the
prompt that can be checked without an opinion.

A model second, on a different model from the one that wrote the answer
(deepseek-v4-flash judging deepseek-v4-pro), for what is left: is the
explanation actually supported by the rows, and does it admit what it does not
know. This never blocks. A judge that blocks makes the pipeline's quality
depend on the judge's mood, and ADR-001 already refused to make it the criterion.

The separation is weaker than it looks: same vendor, same family, so a shared
blind spot stays shared. Named in docs/limits.md rather than glossed over.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .compare import Table

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "deepseek-v4-flash")


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Check(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: Status
    detail: str


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: list[Check] = Field(default_factory=list)
    # The model's part, absent when the judge was not run.
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not [c for c in self.checks if c.status is Status.FAILED]

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.FAILED]

    @property
    def summary(self) -> str:
        if self.ok:
            return "пояснение проходит проверки"
        return "; ".join(f"{c.id}: {c.detail}" for c in self.failures)


_DIGITS = re.compile(r"\d")


def _spellings(value: float) -> list[str]:
    """The ways one number legitimately appears in a Russian answer."""
    forms: set[str] = set()
    for rounded in (round(value, 2), round(value, 1), round(value)):
        plain = f"{rounded:,.2f}".rstrip("0").rstrip(".")
        raw = f"{rounded}".rstrip("0").rstrip(".")
        for text in (plain, raw):
            digits = re.sub(r"[^\d]", "", text)
            if digits:
                forms.add(digits)
    return sorted(forms)


def _numbers_in(text: str) -> set[str]:
    """Digit runs of the answer, with spaces and separators removed.

    23 765 506,62 and 23765506.62 are the same number written by two people,
    and a judge that cannot see that grades formatting.
    """
    cleaned = re.sub(r"[\s ,.]", "", text)
    return {run for run in re.findall(r"\d+", cleaned)}


def check_answer(
    answer: str,
    *,
    result: Table | None,
    data_as_of: str | None = None,
    measure_columns: list[str] | None = None,
) -> list[Check]:
    """The deterministic half. INSTR-8 and INSTR-11 live here."""
    checks: list[Check] = []
    text = answer.strip()

    if not text:
        return [Check(id="answer-exists", status=Status.FAILED, detail="Ответа нет.")]

    empty_result = result is not None and result.row_count == 0

    # INSTR-8: an empty result is not a zero.
    if empty_result:
        says_no_data = any(
            phrase in text.lower()
            for phrase in ("нет данных", "данных нет", "данных за", "не найдено",
                           "пусто", "отсутствуют")
        )
        checks.append(
            Check(
                id="empty-is-not-zero",
                status=Status.PASSED if says_no_data else Status.FAILED,
                detail=(
                    "Пустой результат назван отсутствием данных."
                    if says_no_data
                    else "Запрос вернул ноль строк, а ответ не говорит, что данных нет. "
                    "Ноль как ответ про выручку означает «продавали и не продали»."
                ),
            )
        )
    else:
        checks.append(
            Check(id="empty-is-not-zero", status=Status.SKIPPED,
                  detail="Результат не пустой.")
        )

    # INSTR-11, first part: the numbers in the answer come from the rows.
    if result is not None and result.row_count and measure_columns:
        wanted: list[str] = []
        for column in measure_columns:
            try:
                position = result.index(column)
            except KeyError:
                continue
            for row in result.rows[:5]:
                value = row[position]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    wanted.append(value)
        written = _numbers_in(text)
        found = [
            value for value in wanted
            if any(spelling in written for spelling in _spellings(float(value)))
        ]
        carried = bool(found) if wanted else True
        checks.append(
            Check(
                id="numbers-from-the-result",
                status=Status.PASSED if carried else Status.FAILED,
                detail=(
                    f"Числа ответа найдены в результате ({len(found)} из {len(wanted)} "
                    "проверенных)."
                    if carried
                    else "Ни одно число из результата не встречается в ответе. "
                    "Пояснение написано не по этим строкам."
                ),
            )
        )
    else:
        checks.append(
            Check(id="numbers-from-the-result", status=Status.SKIPPED,
                  detail="Нечего сверять: результата или мер нет.")
        )

    # INSTR-11, second part: the moment the data describes.
    if data_as_of:
        day = data_as_of[:10]
        mentioned = day in text or day.replace("-", ".") in text or "реплик" in text.lower()
        checks.append(
            Check(
                id="data-as-of",
                status=Status.PASSED if mentioned else Status.FAILED,
                detail=(
                    "Момент данных назван."
                    if mentioned
                    else f"В ответе нет момента данных ({day}). Читатель не может "
                    "знать, насколько ответ свежий."
                ),
            )
        )
    else:
        checks.append(
            Check(id="data-as-of", status=Status.SKIPPED, detail="Момент данных неизвестен.")
        )

    # INSTR-11, third part: how it was obtained.
    explains = any(
        word in text.lower()
        for word in ("фильтр", "таблиц", "соединен", "запрос", "считал",
                     "посчитан", "исключ", "период", "источник")
    )
    checks.append(
        Check(
            id="how-obtained",
            status=Status.PASSED if explains else Status.FAILED,
            detail=(
                "Сказано, как получено."
                if explains
                else "Ответ не говорит, как получено число: ни таблиц, ни фильтров, "
                "ни периода."
            ),
        )
    )

    return checks


RUBRIC = """Ты проверяешь пояснение аналитика к числовому ответу.

Тебе дан вопрос бизнеса, строки результата запроса и текст ответа. Оцени три вещи.

1. Обоснованность: каждое утверждение ответа следует из строк результата. Утверждение, которого в строках нет, это выдумка.
2. Честность неопределённости: если результат пустой, ограничен, обрезан или считался с оговоркой, ответ это называет.
3. Понятность: ответ отвечает на заданный вопрос словами бизнеса, без пересказа собственных шагов.

Ответь строго в JSON: {"score": <0..1>, "reasons": ["...", "..."], "unsupported": ["..."]}.
score это доля выполненных требований. reasons короткие, по-русски. unsupported перечисляет утверждения ответа, которых нет в данных."""


class JudgeUnavailable(Exception):
    """No key, no network, or the judge refused. Never fatal: the judge does not
    block, so its absence must not turn into a failed run."""


def judge_with_model(
    *,
    question: str,
    answer: str,
    result: Table | None,
    model: str = JUDGE_MODEL,
    timeout: int = 120,
) -> tuple[float, list[str], list[str]]:
    """Ask the second model. Returns score, reasons, unsupported claims."""
    key = os.environ.get("LLM_API_KEY")
    base = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    if not key:
        raise JudgeUnavailable("LLM_API_KEY не задан")

    rows = []
    if result is not None:
        rows = [dict(zip(result.columns, row)) for row in result.rows[:20]]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": RUBRIC},
            {
                "role": "user",
                "content": json.dumps(
                    {"вопрос": question, "строки результата": rows, "ответ": answer},
                    ensure_ascii=False, default=str,
                ),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise JudgeUnavailable(str(exc)) from exc

    try:
        content = body["choices"][0]["message"]["content"]
        parsed: dict[str, Any] = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise JudgeUnavailable(f"судья ответил не JSON: {exc}") from exc

    score = float(parsed.get("score", 0.0))
    return score, list(parsed.get("reasons", [])), list(parsed.get("unsupported", []))


def judge(
    *,
    question: str,
    answer: str,
    result: Table | None,
    data_as_of: str | None = None,
    measure_columns: list[str] | None = None,
    use_model: bool = False,
) -> Verdict:
    checks = check_answer(
        answer,
        result=result,
        data_as_of=data_as_of,
        measure_columns=measure_columns,
    )
    score: float | None = None
    reasons: list[str] = []

    if use_model:
        try:
            score, reasons, unsupported = judge_with_model(
                question=question, answer=answer, result=result
            )
            if unsupported:
                reasons = reasons + ["не подтверждено данными: " + "; ".join(unsupported)]
        except JudgeUnavailable as exc:
            reasons = [f"судья не запускался: {exc}"]

    return Verdict(checks=checks, score=score, reasons=reasons)
