# Glossary

Термины проекта в одном месте. Если встретишь термин не отсюда — добавь его при первом использовании.

---

**Agent harness** — связка контекста, инструментов, скиллов и контрактов, превращающая LLM в специализированного агента под задачу. Этот проект и есть личный harness.

**Citation-маркер** — inline-аннотация в wiki-странице, привязывающая факт к raw-источнику. Формат: `^[src:<source-id>:<locator>]`. Локатор может быть `§<секция>`, `p.<страница>`, `t=<timestamp>` (для видео/аудио).

**CLAUDE.md** — schema-файл для агента. Бывает корневой (этого проекта) и локальный (одной wiki или одного skill). Описывает правила работы. Аналог в OpenAI Codex / Antigravity — `AGENTS.md`.

**Contradiction page** — страница в `wikis/<domain>/contradictions/`, где зафиксировано разногласие между двумя или более источниками. Содержит источники, формулировки, и поле `resolution` — либо «X истинен потому что …», либо `unresolved`.

**Edition** — версия raw-источника. Когда выходит новая редакция стандарта/документа, старый файл остаётся, новый добавляется с новой меткой edition. Зависимые wiki-страницы помечаются `status: stale` до пересчёта.

**Entity page** — страница в `wikis/<domain>/entities/` о конкретной сущности (компания, технология, человек, стандарт).

**Concept page** — страница в `wikis/<domain>/concepts/` об абстрактной идее или паттерне (например, event sourcing, CAP-теорема).

**Ingest** — операция добавления нового raw-источника в wiki. Делается skill-ом `wiki-ingest`. Включает: чтение, извлечение entities/concepts, обновление существующих страниц, создание новых, апдейт `index.md` и `log.md`, lint-проверку.

**Lint-контракт** — инвариант wiki, проверяемый `wiki-lint`. Список — в `harness/architecture.md`, раздел 6. Critical-проверки блокируют публикацию; warning-проверки логируются.

**LLM Wiki** — паттерн Карпатого: персистентный, накапливающий markdown-knowledge-base, поддерживаемый агентом, а не человеком. См. [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

**MCP** (Model Context Protocol) — открытый протокол подключения внешних систем к LLM-агенту. Это «доступ»: auth, transport, tool discovery. Не «поведение».

**Orphan page** — wiki-страница, на которую нет входящих ссылок ни из одной другой страницы. Warning-level lint-issue: возможно, забыли cross-link.

**Progressive disclosure** — паттерн загрузки skill-контента: metadata всегда в контексте (~100 токенов), тело SKILL.md — когда скилл активирован (~3-5k токенов), references/scripts — по запросу. Позволяет иметь сотни skills без раздувания контекста.

**Raw** — слой 1: immutable источники (PDF, web-clips, transcripts). Никогда не редактируются. Адресуются по `source-id` (slug) и `edition`.

**Schema layer** — слой 3: `CLAUDE.md` файлы, задающие контракты. Корневой определяет правила проекта, локальные — правила одной wiki или skill.

**Skill** — папка с `SKILL.md` (обязательно) и опциональными `references/`, `scripts/`, `assets/`. YAML frontmatter с `name` и `description` всегда в контексте; тело — по триггеру. Открытый стандарт Anthropic; работает в Claude.ai, Claude Code, OpenAI Codex, Cursor, Gemini CLI.

**Skill-creator** — мета-skill от Anthropic, ставится плагином `claude plugin install skill-creator@claude-plugins-official`. Единственный способ создавать новые skills в этом проекте. Живёт вне репозитория, поэтому доступен во всех проектах. Умеет прогонять эвалы, грейдить результаты субагентами и оптимизировать description; чего не умеет, так это состязательной проверки на устойчивость под давлением, для этого есть `harness/meta-skills/skill-creator/addenda/pressure-testing.md`.

**Source page** — страница в `wikis/<domain>/sources/`, описывающая один raw-источник: что в нём, когда добавлен, какие entity/concept-страницы из него выросли.

**Stale claim** — фактическое утверждение в wiki, чей raw-источник обновился (новая edition), но wiki ещё не пересчиталась. Critical lint-issue.

**Structured layer** — wiki-данные в виде структурированных файлов (CSV, JSON, YAML), а не markdown-прозы. Используется для таблиц из raw. Лежит в `wikis/<domain>/data/`.

**Subagent** — отдельный экземпляр Claude в Claude Code с собственным контекстом и набором tools. Может вызывать skills. Не путать с самим skill.

**Tool** — функция, которую агент вызывает напрямую (file_write, web_search, и т.д.). «Чем делать». В отличие от skill, который говорит «что делать».

**Wiki** — слой 2: LLM-сгенерированные markdown-страницы по одному домену, со ссылками между собой и citations на raw. Адресуется по слагу. Никогда не редактируется руками.

**Wiki-ingest / wiki-lint / wiki-query / wiki-llm-builder** — четыре системных skill для работы с wiki. Создаются на днях 1-3 проекта.
