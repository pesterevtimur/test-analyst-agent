# .claude/skills/

Папка для собственных skills этого проекта. Claude Code сканирует её при старте сессии и автоматически делает все skills отсюда доступными.

## Что сюда кладётся

Каждый skill это директория с `SKILL.md` (обязательно) и опциональными `references/`, `scripts/`, `assets/`, `evals/`. Структура по [Anthropic Agent Skills spec](https://agentskills.io/specification).

## Как сюда что-то попадает

**Только через `skill-creator`**. Он ставится плагином:

```
claude plugin install skill-creator@claude-plugins-official
```

Это правило №1 проекта (см. корневой `CLAUDE.md`). Для скиллов, которые что-то запрещают (в тексте есть «MUST not», «block», «refuse», «stop and ask»), поверх обычного потока применяется `harness/meta-skills/skill-creator/addenda/pressure-testing.md`.

Не создавай `SKILL.md` руками. Не копируй чужие skills из awesome-каталогов без аудита и адаптации.

## Как проверить, что skill виден

В Claude Code:
```
/skills
```
Должен показать список всех skills из этой папки + из `~/.claude/skills/`.

## Что здесь лежит

Дисциплина:
- `evidence-before-action`: запрещает исходящее действие без свежей проверки фактов в том же ходе

Работа с wiki:
- `wiki-llm-builder`: инициализирует новую wiki по теме
- `wiki-ingest`: добавляет источник в wiki
- `wiki-lint`: health-check
- `wiki-query`: запрос с citations

План проекта лежит в `BRIEF.md` и `SPEC.md`.

## Замечание: project vs personal skills

- **`.claude/skills/`** (эта папка): project-scoped. Коммитится в git, едет вместе с репо.
- **`~/.claude/skills/`**: personal. Доступны во всех проектах. Сюда мы кладём только `skill-creator` (он мета-инструмент).

Если по ходу проекта получится skill общего назначения (например, обобщённый `wiki-query`), его можно скопировать в personal, чтобы использовать в других проектах.
