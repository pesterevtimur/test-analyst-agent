# Пины Superpowers

Неизменяемые копии выбранных скиллов Superpowers. Это не активные скиллы, они не срабатывают по описанию. Их роль: происхождение и справка, когда мы пишем или адаптируем свои скиллы.

## Зачем

Superpowers стоит как плагин Claude Code:

```
~/.claude/plugins/cache/claude-plugins-official/superpowers/<версия>/
```

Эта установка изменяемая, `claude plugin update` перезапишет её. Пины дают три вещи:

1. Ссылаться из своего скилла на конкретный апстрим по относительному пути.
2. Сравнить пин с текущей установкой и увидеть, что апстрим уехал.
3. Указать точную версию и SHA в поле `metadata.upstream` своего скилла.

## Что запинено

Копии совпадают с апстримом байт в байт, поверх добавлена только шапка-комментарий с происхождением. Рядом с `SKILL.md` лежат файлы-спутники, на которые он ссылается: без них ссылки внутри скилла битые.

| Скилл | Версия | SHA | Дата пина | Спутники |
|---|---|---|---|---|
| brainstorming | v6.3.0 | `b36e0829` | 2026-09-02 | `visual-companion.md`, `spec-document-reviewer-prompt.md`, `scripts/` |
| verification-before-completion | v6.3.0 | `b36e0829` | 2026-09-02 | нет |
| writing-skills | v6.3.0 | `b36e0829` | 2026-09-02 | `anthropic-best-practices.md`, `persuasion-principles.md`, `testing-skills-with-subagents.md`, `graphviz-conventions.dot`, `render-graphs.js`, `examples/` |

История: первый пин был сделан 2026-05-17 на v5.1.0 (`f2cbfbef`), только `SKILL.md`, без спутников. Перепиновка 2026-09-02 на v6.3.0. Расхождение на момент перепиновки: brainstorming 165 строк против 250, verification-before-completion 140 против 120, writing-skills 656 против 679.

## Как перепиновать

```bash
claude plugin update superpowers@claude-plugins-official
bash harness/scripts/repin-superpowers-references.sh
```

Скрипт берёт самую свежую версию из кеша плагинов, тянет SHA тега из GitHub, копирует директории скиллов целиком и ставит шапку. Дальше руками: обновить таблицу выше и проверить каждый свой скилл, у которого в `metadata.upstream` осталась старая версия.

Проверить, что пин честный:

```bash
P=~/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills
for s in brainstorming verification-before-completion writing-skills; do
  diff <(tail -n +9 harness/meta-skills/superpowers-references/$s/SKILL.md) $P/$s/SKILL.md \
    && echo "$s ок"
done
```

## Если перепиновка ломает адаптацию

Не подгоняй свой скилл под апстрим молча. Порядок такой:

1. Запиши в `log.md`, что именно изменилось в апстриме.
2. Реши явно: идти за апстримом, форкнуть паттерн или остаться на старой версии.
3. Поправь `metadata.upstream` в своём скилле под принятое решение.

## Как добавить новый пин

Если четвёртый скилл Superpowers становится частой опорой (например, `systematic-debugging` или `test-driven-development`), добавь его имя в массив `SKILLS` в `harness/scripts/repin-superpowers-references.sh`, прогони скрипт, впиши строку в таблицу выше и сошлись на него из `metadata.upstream` своего скилла.
