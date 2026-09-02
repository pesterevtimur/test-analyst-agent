"""Plausibility checks on a result that already ran.

These exist because the dangerous failure is not the query that errors. It is
the query that runs, returns something plausible, and is wrong. The clearest
case met during this project: a filter on a deletion flag mapped the wrong way
round returned zero rows with no error at all.

Nothing here blocks an answer. The job is to make the analyst look at the right
place.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .db import Rows


class Level(StrEnum):
    OK = "ok"
    ATTENTION = "attention"
    STOP = "stop"


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    level: Level
    text: str


class SanityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    observations: list[Observation]

    @property
    def worst(self) -> Level:
        for level in (Level.STOP, Level.ATTENTION):
            if any(o.level is level for o in self.observations):
                return level
        return Level.OK


def _numeric(values: list) -> list[float]:
    return [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]


def check(rows: Rows, *, row_limit: int, limit_imposed: bool = True) -> SanityReport:
    """limit_imposed says who set the row limit.

    Hitting a ceiling the guard rails added means the answer is cut off and
    aggregates over it are wrong. Hitting a limit the analyst wrote themselves,
    a top five, means exactly what they asked for. Treating both as truncation
    trains people to ignore the warning."""
    observations: list[Observation] = []

    if rows.row_count == 0:
        observations.append(
            Observation(
                id="empty-result",
                level=Level.STOP,
                text=(
                    "Результат пуст. Пустой ответ почти никогда не означает «нет "
                    "продаж»: чаще это неверный формат фильтра, перепутанный "
                    "признак или период вне данных. Проверьте формат квартала "
                    "(2021-02, где 02 это квартал), подбивку номеров нулями и "
                    "смысл признака удаления. Данные покрывают 2019-2023 годы."
                ),
            )
        )
        return SanityReport(observations=observations)

    if rows.truncated or rows.row_count >= row_limit:
        if limit_imposed:
            observations.append(
                Observation(
                    id="truncated",
                    level=Level.STOP,
                    text=(
                        f"Вернулось ровно {rows.row_count} строк, то есть предел, "
                        "который поставили ограничители. Ответ неполон, и агрегаты "
                        "по нему считать нельзя. Сузьте выборку или считайте "
                        "агрегат в самом запросе."
                    ),
                )
            )
        else:
            observations.append(
                Observation(
                    id="at-requested-limit",
                    level=Level.ATTENTION,
                    text=(
                        f"Вернулось ровно {rows.row_count} строк, столько и было "
                        "запрошено. Это не обрезка ответа, но за пределом выборки "
                        "могут быть ещё строки: если вопрос был про полный список, "
                        "а не про первые строки, ограничение надо снять."
                    ),
                )
            )

    for index, name in enumerate(rows.columns):
        column = [row[index] for row in rows.rows]
        numbers = _numeric(column)

        if column and all(value is None for value in column):
            observations.append(
                Observation(
                    id=f"all-null:{name}",
                    level=Level.ATTENTION,
                    text=(
                        f"Колонка {name} целиком пуста. Обычно это соединение, "
                        "которое не нашло соответствий, а не отсутствие значения."
                    ),
                )
            )
            continue

        if numbers and len(numbers) == len(column):
            negatives = [v for v in numbers if v < 0]
            if negatives and _looks_like_money(name):
                observations.append(
                    Observation(
                        id=f"negative:{name}",
                        level=Level.ATTENTION,
                        text=(
                            f"В колонке {name} есть отрицательные значения "
                            f"({len(negatives)} из {len(numbers)}). Для выручки или "
                            "количества это либо возвраты, либо ошибка знака. "
                            "Стоит сказать в ответе, что именно."
                        ),
                    )
                )
            if len(set(numbers)) == 1 and len(numbers) > 3:
                observations.append(
                    Observation(
                        id=f"constant:{name}",
                        level=Level.ATTENTION,
                        text=(
                            f"Все {len(numbers)} значений в колонке {name} одинаковы. "
                            "Часто это признак того, что группировка не сработала "
                            "и агрегат посчитан по всей выборке."
                        ),
                    )
                )

    if not observations:
        observations.append(
            Observation(
                id="ok",
                level=Level.OK,
                text=f"Проверки правдоподобия пройдены, строк {rows.row_count}.",
            )
        )
    return SanityReport(observations=observations)


def _looks_like_money(name: str) -> bool:
    lowered = name.lower()
    return any(
        token in lowered
        for token in ("netwr", "revenue", "amount", "sum", "выручк", "fkimg", "qty",
                      "quantity", "margin", "маржа", "stprs", "cost")
    )
