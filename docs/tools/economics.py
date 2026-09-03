"""Арифметика очереди и финансовая модель, считаемые, а не написанные.

Числа в `docs/economics.md` берутся отсюда. Так их можно пересчитать под другие
допущения одной командой, а не переписывать текст и надеяться, что нигде не
осталось старой цифры.

У каждого входного числа назван источник: замер, оценка, ответ заказчика. Это
не украшение. Модель целиком держится на двух величинах, которых никто не мерил
(поток запросов и время аналитика на проверку предложения), и читатель обязан
видеть, какая часть вывода стоит на замере, а какая на догадке.

Запуск:
    python3 docs/tools/economics.py
    python3 docs/tools/economics.py --json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field

# --- входные числа -----------------------------------------------------------


@dataclass(frozen=True)
class Inputs:
    # Ответ Тимура, 3 сентября 2026. Считаем полной стоимостью часа для
    # компании; если это ставка «на руки», вся польза в деньгах примерно
    # удваивается, то есть допущение консервативное.
    rate_rub_per_hour: int = 4000

    # Бриф: команда 10-15 аналитиков. Берём середину.
    analysts: int = 12
    # Оценка автора: сколько часов в неделю аналитик реально тратит на вопросы
    # бизнеса, а не на совещания, дежурства и разбор инцидентов.
    productive_hours_per_week: float = 25.0

    # Оценка Тимура, сентябрь 2026, середины диапазонов из SPEC, раздел 9.
    hours_simple: float = 0.75    # диапазон 0.5-1
    hours_medium: float = 5.0     # диапазон 3-7
    hours_complex: float = 16.0   # диапазон 1-3 дня

    # Оценка автора, требует проверки у заказчика: как распределяются вопросы
    # по классам. Самое неустойчивое место модели после времени проверки.
    share_simple: float = 0.50
    share_medium: float = 0.35
    share_complex: float = 0.15

    # С агентом. Простой вопрос сводится к проверке предложения в панели,
    # средний теряет поиск таблиц и сборку SQL, сложный почти не меняется:
    # там время уходит на сверку с источником и разбор расхождений.
    review_hours_simple: float = 1 / 6      # 10 минут
    hours_medium_with_agent: float = 3.0
    hours_complex_with_agent: float = 15.0

    # Бриф: очередь расписана примерно на два года.
    backlog_years: float = 2.0

    # Замер 2 сентября 2026: около 0.2 цента за шаг, задача из пяти шагов.
    # Курс взят грубо и назван допущением: точность здесь ни на что не влияет,
    # величина на три порядка меньше часа аналитика.
    agent_cost_usd_per_task: float = 0.01
    usd_rub: float = 90.0
    attempts_per_question: float = 3.0

    sources: dict[str, str] = field(default_factory=lambda: {
        "rate_rub_per_hour": "ответ Тимура, 3 сентября 2026",
        "analysts": "бриф, 10-15, взята середина",
        "productive_hours_per_week": "оценка автора",
        "hours_*": "оценка Тимура, сентябрь 2026",
        "share_*": "оценка автора, требует проверки у заказчика",
        "review_hours_simple": "оценка автора, ключевой параметр модели",
        "backlog_years": "бриф",
        "agent_cost_usd_per_task": "замер 2 сентября 2026",
        "поток запросов в неделю": "неизвестен, Тимур точного числа не назвал; "
                                   "в модель входит как параметр, а не как константа",
    })


# --- расчёт ------------------------------------------------------------------


def weighted_hours(inputs: Inputs, *, with_agent: bool) -> float:
    """Средние часы аналитика на один вопрос по смеси классов."""
    simple = inputs.review_hours_simple if with_agent else inputs.hours_simple
    medium = inputs.hours_medium_with_agent if with_agent else inputs.hours_medium
    complex_ = inputs.hours_complex_with_agent if with_agent else inputs.hours_complex
    return (
        inputs.share_simple * simple
        + inputs.share_medium * medium
        + inputs.share_complex * complex_
    )


def model(inputs: Inputs) -> dict:
    capacity_hours = inputs.analysts * inputs.productive_hours_per_week

    before = weighted_hours(inputs, with_agent=False)
    after = weighted_hours(inputs, with_agent=True)

    throughput_before = capacity_hours / before
    throughput_after = capacity_hours / after
    gain = throughput_after / throughput_before - 1

    # Ожидание в очереди: при неизменном запасе заявок оно обратно пропорционально
    # пропускной способности. Это и есть вся арифметика очереди: длину очереди
    # никто не измерял, а отношение «во сколько раз» от неё не зависит.
    wait_before_months = inputs.backlog_years * 12
    wait_after_months = wait_before_months / (1 + gain)

    # Деньги считаются на том же числе вопросов: столько же ответов, меньше часов.
    hours_saved_per_week = throughput_before * (before - after)
    money_saved_per_month = hours_saved_per_week * 4.33 * inputs.rate_rub_per_hour

    agent_cost_per_question = (
        inputs.agent_cost_usd_per_task * inputs.attempts_per_question * inputs.usd_rub
    )
    agent_cost_per_month = agent_cost_per_question * throughput_before * 4.33

    return {
        "capacity_hours_per_week": capacity_hours,
        "hours_per_question_before": before,
        "hours_per_question_after": after,
        "questions_per_week_before": throughput_before,
        "questions_per_week_after": throughput_after,
        "throughput_gain": gain,
        "wait_before_months": wait_before_months,
        "wait_after_months": wait_after_months,
        "hours_saved_per_week": hours_saved_per_week,
        "money_saved_per_month_rub": money_saved_per_month,
        "agent_cost_per_question_rub": agent_cost_per_question,
        "agent_cost_per_month_rub": agent_cost_per_month,
        "cost_ratio": money_saved_per_month / agent_cost_per_month,
    }


def cost_per_class(inputs: Inputs) -> list[dict]:
    rate = inputs.rate_rub_per_hour
    return [
        {"class": "простой", "hours": "0,5-1", "rub": f"{int(0.5 * rate)} - {int(1 * rate)}"},
        {"class": "средний", "hours": "3-7", "rub": f"{int(3 * rate)} - {int(7 * rate)}"},
        {"class": "сложный", "hours": "8-24", "rub": f"{int(8 * rate)} - {int(24 * rate)}"},
    ]


def sensitivity_review_time(inputs: Inputs) -> list[dict]:
    """Главная неизвестная: сколько минут уходит на проверку предложения.

    Всё обещание пользы на простом классе живёт внутри этого числа. При проверке
    в 45 минут простой вопрос не выигрывает ничего: столько он и стоил.
    """
    rows = []
    for minutes in (5, 10, 20, 30, 45, 60):
        variant = Inputs(**{**{k: v for k, v in asdict(inputs).items() if k != "sources"},
                            "review_hours_simple": minutes / 60})
        computed = model(variant)
        rows.append({
            "review_minutes": minutes,
            "questions_per_week": round(computed["questions_per_week_after"], 1),
            "gain_percent": round(computed["throughput_gain"] * 100),
            "wait_months": round(computed["wait_after_months"], 1),
            "money_per_month_rub": round(computed["money_saved_per_month_rub"]),
        })
    return rows


def sensitivity_mix(inputs: Inputs) -> list[dict]:
    """Вторая неизвестная: какая доля вопросов простая."""
    rows = []
    for simple in (0.3, 0.4, 0.5, 0.6, 0.7):
        rest = 1 - simple
        variant = Inputs(**{**{k: v for k, v in asdict(inputs).items() if k != "sources"},
                            "share_simple": simple,
                            "share_medium": rest * 0.7,
                            "share_complex": rest * 0.3})
        computed = model(variant)
        rows.append({
            "share_simple": simple,
            "gain_percent": round(computed["throughput_gain"] * 100),
            "wait_months": round(computed["wait_after_months"], 1),
            "money_per_month_rub": round(computed["money_saved_per_month_rub"]),
        })
    return rows



def contribution(inputs: Inputs) -> list[dict]:
    """Откуда берётся польза. Считается до того, как её приписали агенту.

    Модель легко прочитать как «агент закрывает простые вопросы», и это будет
    неверно: больше половины экономии даёт средний класс, где агент не отвечает
    сам, а снимает поиск таблиц и сборку запроса.
    """
    pairs = [
        ("простой", inputs.share_simple, inputs.hours_simple, inputs.review_hours_simple),
        ("средний", inputs.share_medium, inputs.hours_medium, inputs.hours_medium_with_agent),
        ("сложный", inputs.share_complex, inputs.hours_complex, inputs.hours_complex_with_agent),
    ]
    total = sum(share * (before - after) for _, share, before, after in pairs)
    return [
        {
            "class": name,
            "hours_saved_per_question": round(share * (before - after), 3),
            "share_of_benefit": round(share * (before - after) / total, 3),
        }
        for name, share, before, after in pairs
    ]


def sensitivity_medium(inputs: Inputs) -> list[dict]:
    """Главное допущение модели: во что превращается средний вопрос."""
    rows = []
    for hours in (5.0, 4.5, 4.0, 3.5, 3.0, 2.5):
        variant = Inputs(**{**{k: v for k, v in asdict(inputs).items() if k != "sources"},
                            "hours_medium_with_agent": hours})
        computed = model(variant)
        rows.append({
            "hours_medium_with_agent": hours,
            "gain_percent": round(computed["throughput_gain"] * 100),
            "wait_months": round(computed["wait_after_months"], 1),
            "money_per_month_rub": round(computed["money_saved_per_month_rub"]),
        })
    return rows


def break_even(inputs: Inputs) -> dict:
    """При каком времени проверки польза на классе обнуляется."""
    return {
        "simple_minutes": round(inputs.hours_simple * 60),
        "medium_hours": inputs.hours_medium,
        "complex_hours": inputs.hours_complex,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    inputs = Inputs()
    computed = model(inputs)

    if args.json:
        print(json.dumps(
            {
                "inputs": asdict(inputs),
                "model": computed,
                "cost_per_class": cost_per_class(inputs),
                "sensitivity_review_time": sensitivity_review_time(inputs),
                "sensitivity_mix": sensitivity_mix(inputs),
                "sensitivity_medium": sensitivity_medium(inputs),
                "contribution": contribution(inputs),
                "break_even": break_even(inputs),
            },
            ensure_ascii=False, indent=2,
        ))
        return 0

    print("Стоимость вопроса по классам, ставка "
          f"{inputs.rate_rub_per_hour} рублей в час\n")
    print("| Класс | Часы | Рублей |")
    print("|---|---|---|")
    for row in cost_per_class(inputs):
        print(f"| {row['class']} | {row['hours']} | {row['rub']} |")

    print("\nПропускная способность команды\n")
    print(f"  часов в неделю на всех: {computed['capacity_hours_per_week']:.0f}")
    print(f"  часов на вопрос сейчас: {computed['hours_per_question_before']:.2f}")
    print(f"  часов на вопрос с агентом: {computed['hours_per_question_after']:.2f}")
    print(f"  вопросов в неделю сейчас: {computed['questions_per_week_before']:.1f}")
    print(f"  вопросов в неделю с агентом: {computed['questions_per_week_after']:.1f}")
    print(f"  прирост: {computed['throughput_gain'] * 100:.0f} процентов")
    print(f"  ожидание в очереди: {computed['wait_before_months']:.0f} месяцев "
          f"было, {computed['wait_after_months']:.1f} стало")

    print("\nДеньги\n")
    print(f"  сэкономлено часов в неделю: {computed['hours_saved_per_week']:.1f}")
    print(f"  сэкономлено рублей в месяц: {computed['money_saved_per_month_rub']:,.0f}"
          .replace(",", " "))
    print(f"  стоимость агента в месяц: {computed['agent_cost_per_month_rub']:,.0f}"
          .replace(",", " "))
    print(f"  отношение пользы к стоимости модели: {computed['cost_ratio']:,.0f} к 1"
          .replace(",", " "))

    print("\nЧувствительность к времени проверки предложения\n")
    print("| Минут на проверку | Вопросов в неделю | Прирост | Ожидание, месяцев | Рублей в месяц |")
    print("|---|---|---|---|---|")
    for row in sensitivity_review_time(inputs):
        print(f"| {row['review_minutes']} | {row['questions_per_week']} | "
              f"{row['gain_percent']}% | {row['wait_months']} | "
              f"{row['money_per_month_rub']:,}".replace(",", " ") + " |")

    print("\nЧувствительность к доле простых вопросов\n")
    print("| Доля простых | Прирост | Ожидание, месяцев | Рублей в месяц |")
    print("|---|---|---|---|")
    for row in sensitivity_mix(inputs):
        print(f"| {row['share_simple']:.0%} | {row['gain_percent']}% | "
              f"{row['wait_months']} | {row['money_per_month_rub']:,}".replace(",", " ") + " |")

    print("\nЧувствительность к среднему классу, где лежит большая часть пользы\n")
    print("| Часов на средний вопрос с агентом | Прирост | Ожидание, месяцев | Рублей в месяц |")
    print("|---|---|---|---|")
    for row in sensitivity_medium(inputs):
        print(f"| {row['hours_medium_with_agent']} | {row['gain_percent']}% | "
              f"{row['wait_months']} | {row['money_per_month_rub']:,}".replace(",", " ") + " |")

    print("\nОткуда берётся экономия\n")
    print("| Класс | Часов на вопрос | Доля пользы |")
    print("|---|---|---|")
    for row in contribution(inputs):
        print(f"| {row['class']} | {row['hours_saved_per_question']} | "
              f"{row['share_of_benefit']:.0%} |")

    limits = break_even(inputs)
    print("\nГде польза обнуляется\n")
    print(f"  простой вопрос: проверка дольше {limits['simple_minutes']} минут")
    print(f"  средний вопрос: работа с агентом дольше {limits['medium_hours']:.0f} часов")
    print(f"  сложный вопрос: работа с агентом дольше {limits['complex_hours']:.0f} часов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
