---
name: wiki-ingest
description: Ingest a single source file from a bootstrapped LLM Wiki's `raw/` directory — extract entities and concepts, write a source-summary page, save tables as structured CSV (never prose), and stamp every factual sentence with a citation marker. Use whenever the user wants to add, ingest, absorb, process, or "feed in" a source to an existing wiki — e.g. "ingest karpathy-llm-wiki-2026.md into context-engineering", "впитай эту статью про Kafka в wiki microservices", "process this paper into the prompt-injection-defenses wiki", "добавь источник в вики X". The wiki must already exist (created by `wiki-llm-builder`); this skill refuses to ingest into a non-existent or empty wiki. v0.1 handles markdown sources only — PDFs and URL fetching are out of scope; for those, the user prepares the markdown first. v0.1 accepts an explicit `target_wiki` absolute path (or derives it from the source's location) so the skill can run in eval sandboxes, in real `wikis/<domain>/` directories, or in worktrees uniformly.
---

# Wiki Ingest (v0.1)

Add one source from a wiki's `raw/` directory to that wiki. Extract entities, concepts, and tables; write a source-summary page; cite every fact.

> **About v0.1.** The first attempt at this skill (v0) hard-coded `wikis/<wiki-slug>/` as the target. That made the skill un-runnable for evals (whose wiki lives in `_workspace/...`) and tempted the orchestrator to do inline writes directly into `wikis/...`, bypassing the skill. **That bypass violated law #2 of the project** ("wiki content is not written by hand"). v0.1 fixes this by making the target wiki an explicit parameter — every wiki-write the skill needs to do is resolved from `<target_wiki>/`, never from a fixed path. There is no longer any case where a caller needs to "go around" the skill to write into a wiki.

## What this skill is for and not for

**For:** taking a markdown file that already sits in `<target_wiki>/raw/` and turning it into properly-structured wiki content — `<target_wiki>/sources/`, `<target_wiki>/entities/`, `<target_wiki>/concepts/`, `<target_wiki>/data/tables/` — with every fact carrying a citation marker `^[src:<source-id>:<locator>]`.

**Not for (v0):**
- Downloading URLs. The user (or a later skill) places files in `raw/` manually.
- Parsing PDFs, .docx, or other non-text formats. The user converts to markdown first.
- Cross-source contradiction detection. A future skill (`wiki-lint` or a dedicated `wiki-reconcile`) will surface contradictions; v0 just records facts.
- Edition migration. If a source already has an entry with the same source-id, v0 stops and warns. It does not silently re-process.
- Editing the source. Files in `raw/` are immutable. If the source has issues (encoding, whitespace), that is a human chore, not the skill's.

These restrictions are not "limitations to apologize for" — they are the result of cleanly bounding what this skill owns. Trying to do more in v0 increases the failure surface and dilutes the citation contract.

## When you should trigger this skill

Concrete examples of triggering phrases:

- "ingest `<filename>` into `<wiki-slug>`"
- "впитай `<filename>` в вики `<wiki-slug>`"
- "process this paper into the wiki" (with a file already in `raw/`)
- "add this source to the wiki" (file already placed)
- "import the gist into context-engineering"

If the user gives you a URL or an un-converted PDF instead of a markdown file in `<target_wiki>/raw/`, **stop and explain**: the file must be placed in `<target_wiki>/raw/<name>.md` before this skill runs. Offer to wait while the user places it, or to convert one specific PDF for them as a separate step.

## Inputs you need from the user

Either ask or extract from the prompt:

1. **`<target_wiki>`** — absolute path to the wiki's root directory (e.g. `C:\...\agentic-ops-cc\wikis\context-engineering\` or `C:\...\_workspace\iteration-1\eval-1-happy-path\with_skill\outputs\wikis\sandbox\`). The directory must already exist and contain `CLAUDE.md`, `log.md`, and the standard subdirectory skeleton from `wiki-llm-builder`.

   **Resolution rule.** If the user gives an explicit `target_wiki: <absolute-path>` or names a directory directly, use that. If they only name the source file by a path containing `/wikis/<domain>/raw/<file>`, derive `target_wiki` as the path up to and including `<domain>/`. If neither rule produces an unambiguous absolute path, **stop and ask** — never guess.

2. **`<source-file>`** — the source file's absolute path or its filename relative to `<target_wiki>/raw/`. Markdown only for v0.1.

3. **`edition`** — the publication-year or version. If the filename ends in a 4-digit year (e.g. `karpathy-llm-wiki-2026.md`), use that. If the filename has no year suffix, ask. The edition becomes part of the source-id and of every citation; getting it right at ingest is much cheaper than rewriting citations later.

**Never assume `target_wiki = wikis/<some-slug>/` based on a default project layout.** That assumption is what produced the v0 violation: the skill ran fine for evals (which lived in `_workspace/`), but a real-world ingest had to bypass the skill because the orchestrator could not steer the skill at a non-`wikis/` path. Make the path explicit and the skill is portable.

## Procedure

Each step has a why and a how. Follow in order.

### Step 1 — Validate target_wiki and the source file

- `<target_wiki>` must be an absolute path to an existing directory. If it isn't, **stop**.
- `<target_wiki>/CLAUDE.md` must exist. If not, this wiki was never bootstrapped — refuse and point the user at `wiki-llm-builder`.
- `<target_wiki>/raw/<filename>` must exist and be a non-empty markdown file (extension `.md`, `.markdown`, or — with user confirmation — `.txt`).
- The source file must not be `raw/README.md` (that's the skeleton from `wiki-llm-builder`).

Refusing early saves you from creating half-formed pages that someone will have to clean up. Refusing early is also what makes the skill safe to point at *real* `wikis/<domain>/` directories — it will not write anything until preconditions pass.

### Step 2 — Compute the source-id and check idempotency

Source-id = filename without extension, lowercased, kebab-case. Examples:

| Filename | Source-id |
| --- | --- |
| `karpathy-llm-wiki-2026.md` | `karpathy-llm-wiki-2026` |
| `Anthropic_Skills-spec-v1.md` | `anthropic-skills-spec-v1` |
| `paper-2024.md` | `paper-2024` |

Then check `<target_wiki>/sources/<source-id>.md`. See `references/idempotency.md` for the full decision tree. Short version:

- File does not exist → proceed to Step 3 (fresh ingest).
- File exists with `edition` matching the new ingest → **stop with a warning**. The source has already been ingested. Tell the user; do nothing.
- File exists with a different edition → **stop with a warning**. v0 does not handle edition migration. Tell the user how to handle it manually if they really need it (rename the new file to include the new edition in its filename, then re-run; the previous source-id stays valid for old citations).

The reason for stopping rather than re-ingesting: re-running ingest would create duplicate facts or stale citations. The cost of re-doing the work outweighs the cost of failing loudly.

### Step 3 — Read the source and build a heading map

Read the entire file. As you read, build an internal heading map: for each heading, record its slug. Heading-slug rules:

- Lowercase.
- Replace whitespace and punctuation with `-`.
- Strip leading `-`.
- Collapse repeated `-`.
- Strip trailing `-`.

Examples:

| Heading | Slug |
| --- | --- |
| `# Introduction` | `introduction` |
| `## Operations → Ingest` | `operations-ingest` |
| `### What is qmd?` | `what-is-qmd` |

You will need this map in Step 6 every time you write a citation marker.

**For citation locators on markdown sources, the format is `§<heading-slug>`.** See `references/citation-extraction.md` for the full rule set (and what to do when a fact sits between two headings).

### Step 4 — Extract tables FIRST

Tables come first because they have the strictest contract (law #4: tables are data, never prose). Doing them first reduces the temptation to write a paragraph "summarizing" a table later.

For each markdown table (`| col | col |` blocks):

1. Generate a slug for the table from its caption or the surrounding heading. E.g. table under `## Performance benchmarks` → `performance-benchmarks` (append `-N` if multiple tables share a heading).
2. Write `<target_wiki>/data/tables/<slug>.csv` with the table rows. Quote cells containing commas or newlines per RFC 4180.
3. Write `<target_wiki>/data/tables/<slug>.meta.yaml` sidecar with `source`, `source_location` (the section the table appeared in), `extracted` date, `columns` list, and any notes (footnotes, units, caveats).

See `references/table-extraction.md` for sidecar schema and edge cases (multi-row headers, merged cells, footnotes attached to specific cells).

**Do not write the table's content into any other page as prose.** Wiki pages that need to reference the data link to the file with relative paths, e.g. `[Performance benchmarks](../data/tables/performance-benchmarks.csv)`.

### Step 5 — Identify entities and concepts

This is the LLM-judgment step. Read `references/entity-concept-detection.md` for heuristics. Short version:

- **Entity** = a concrete thing that could be the subject of a Wikipedia page. People (Karpathy), organizations (Anthropic), products/libraries (qmd, Kompl), specific standards (GOST R 12345).
- **Concept** = an abstract pattern or principle. Edition versioning, structured layer, lossy compression of context, citation marker.

For each, decide:

- New page in `<target_wiki>/entities/<slug>.md` or `<target_wiki>/concepts/<slug>.md`? Use kebab-case slug, unique within the wiki.
- Update an existing page if one exists with the same slug? Read the existing page first; merge new facts in, keeping old citations intact.

**Cap v0 at ~5 entities + ~5 concepts per ingest.** Going deeper is tempting but increases the chance of missing citations. Better to ingest twice (a future skill can do "re-mine for additional entities") than to bury citations under volume.

### Step 6 — Write pages with citations as you go

This is the most important step. **Every factual sentence carries an inline citation marker as you write it.** Do not write a paragraph, then go back and add citations — markers are too easy to forget that way.

Format: `^[src:<source-id>:§<heading-slug>]` for facts sitting under that heading. If the fact spans multiple sections, use the most specific one that supports the claim.

A "factual sentence" is any sentence that contains:
- A number (`load is 10 kN`, `42 papers reviewed`)
- A date (`published in 2024`)
- A named entity (`Anthropic released …`)
- A direct quote (`Karpathy wrote: "..."`)
- A causal or comparative claim (`X causes Y`, `X is faster than Y`)

Page schemas:

**`<target_wiki>/sources/<source-id>.md`** — required, exactly one per ingest. YAML frontmatter:

```yaml
---
type: source
slug: <source-id>
title: <human-readable title from the doc>
created: <today>
updated: <today>
status: draft
edition: <year or edition>
sources:
  - src:<source-id>
---
```

Body: one-paragraph summary (with citations, since even the summary makes factual claims), then a `## Citation format` block showing one or two example markers for this source, then a `## Key sections` list mapping section-slugs → 1-line description (useful for future agents picking locators).

**`<target_wiki>/entities/<slug>.md`** and **`<target_wiki>/concepts/<slug>.md`** — use the schema from the wiki's `_templates/entity-template.md`. Sections in order: Summary, Key facts, Related (`[[wikilinks]]`), Open questions.

When updating an existing entity/concept page: add new bullets to Key facts, add new sentences to Summary, append to Related/Open questions as needed. Never delete existing content from another source.

### Step 7 — Update the wiki-local log

Append one line to `<target_wiki>/log.md`:

```
## [<YYYY-MM-DD>] ingest | <source-id> | <N> entities, <M> concepts, <K> tables
```

If you stopped at Step 2 (idempotency warning), append a `note` line instead:

```
## [<YYYY-MM-DD>] note | wiki-ingest skipped <source-id>: <reason>
```

### Step 8 — Verify and report

Run a quick self-check before reporting success:

- Every page you created/updated has a citation marker on every factual sentence.
- Every citation marker points at a section slug that exists in your heading map from Step 3.
- Every table from the source exists as CSV + sidecar; no table content appears as prose anywhere.
- `<target_wiki>/sources/<source-id>.md` exists and has frontmatter `edition` matching what the user gave you.
- `<target_wiki>/log.md` has the new entry.

Report to the user:

1. Created files (paths, count).
2. The source-id you used and the edition.
3. Any entities/concepts you considered but skipped (and why — usually "deferred to keep v0 scope tight").
4. Next step: nothing required, but `wiki-lint` (when it exists) is the natural follow-up.

## What if you hit something the skill doesn't cover

- The source contains diagrams as images. Note them in the source-page's `## Key sections` block ("`§diagrams` contains figures; not extracted in v0") and move on. Future skill can OCR.
- The source is a transcript with timestamps. Use `<HH:MM:SS>` as the locator instead of `§<slug>`. Document the deviation in the source page's `## Citation format` block.
- The source's section structure is non-existent (flat doc). Use `¶<n>` (n-th paragraph) as the locator and document this in the source page.
- The user asks you to also delete or rename the raw file after ingest. Refuse. `raw/` is immutable (law #4 of the project).

## References

Load on demand:

- `references/citation-extraction.md` — locator rules per source type, paragraph-anchor fallbacks, multi-section facts.
- `references/entity-concept-detection.md` — heuristics for what counts as entity vs concept, slug uniqueness, when to update vs create.
- `references/table-extraction.md` — CSV format, meta.yaml schema, multi-row headers, footnotes.
- `references/idempotency.md` — the full decision tree for re-ingest scenarios.
- `assets/` — minimal page templates (source page, entity page, concept page).

For project context: root `CLAUDE.md` (four laws) and `harness/architecture.md` (anatomy of a wiki page, lint contracts) are the contract this skill enforces.
