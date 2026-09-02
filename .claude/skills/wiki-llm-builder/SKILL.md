---
name: wiki-llm-builder
description: Initialize (bootstrap) a brand-new LLM Wiki domain under wikis/<slug>/ with this project's hierarchical schema, citation contracts, and structured-data layer. Use whenever the user wants to start a new wiki, knowledge base, knowledge domain, or thematic note tree — e.g. "create a wiki for context engineering", "let's start a knowledge base about microservices", "инициализируй вики по теме X", "set up a new domain in wikis/ for distributed-systems papers". Use this even if the user does not literally say the word "wiki" but is clearly opening a fresh thematic knowledge area that should outlive the current session. Bootstrap-only: this skill creates the empty scaffold; populating it with sources is the job of the sibling skill wiki-ingest.
---

# Wiki LLM Builder

Initialize a new LLM Wiki domain — a thematic knowledge base under `wikis/<slug>/` that conforms to the four laws of this project (raw immutability, no manual wiki edits, citation-or-no-fact, tables-as-data).

## What "initialize" means here

You are creating the **skeleton only**. The wiki starts essentially empty, ready to be filled by the `wiki-ingest` skill. The skeleton encodes the contracts: every directory has a defined role, every template page demonstrates the citation format, and the wiki-local `CLAUDE.md` tells future agents how to operate inside this specific domain.

Filling the wiki with real facts is **not your job**. That belongs to `wiki-ingest`. If the user mentions sources during this conversation, acknowledge them and record their existence in `log.md` as pending ingests — but do not download, parse, or summarize them.

The reason for this hard separation: the project's first law is that skills do not bleed scope. A skill that bootstraps *and* ingests becomes hard to test, hard to reason about, and tempts an agent to skip the citation contract in the name of "while we're here". Keep it narrow.

## When to trigger

The `description` field already pushes triggering. In practice expect prompts like:

- "create a wiki for context engineering"
- "инициализируй вики по микросервисам"
- "I want to start a knowledge base on prompt-injection defenses, here are some links"
- "we need a fresh domain in wikis/ for distributed-systems papers"

You may also self-trigger when another skill (e.g. `wiki-query`) reports that no wiki exists for a topic and one is clearly needed.

## Procedure

Each step has a *why* and a *how*. Follow in order — later steps depend on earlier ones.

### Step 1 — Resolve the domain slug

User phrasing is rarely a clean filesystem name. "Context engineering!" must become `context-engineering`. "Микросервисы 2.0" must become something like `microservices-2-0`.

Normalize:
1. Lowercase.
2. Replace whitespace and punctuation with `-`.
3. Collapse repeated `-`; strip leading/trailing `-`.
4. If the source contains non-Latin characters, ask the user: transliterate, translate, or use Latin equivalent? Their choice goes into the wiki-local `CLAUDE.md` so future ingests are consistent.
5. **Confirm the slug with the user before creating anything.**

Why confirm: the slug is part of the wiki's permanent identity. It appears in paths, internal links, and source IDs. Renaming later requires rewriting every wikilink and every citation that references this wiki's source-IDs. Five seconds of confirmation buys hours of avoided rework.

### Step 2 — Idempotency check

Before writing anything, check whether `wikis/<slug>/` already exists and is non-empty. (Use `ls` / `Get-ChildItem` / the `Glob` tool.)

If it exists:
- If the user phrased the request as "create", "start", "initialize" → **stop and ask.** It may be an accidental re-init that would overwrite hand-edited `CLAUDE.md` or `log.md`.
- Offer three options: abort, refresh just the local `CLAUDE.md`, or pick a different slug.
- Never silently overwrite.

Why: this skill is destructive if it re-stamps over a wiki that already has content. The cost of asking is small; the cost of losing curated context is large.

### Step 3 — Create the directory tree

Create these directories under `wikis/<slug>/`:

```
entities/
concepts/
sources/
contradictions/
data/tables/
raw/
_templates/
```

If the project has no `wikis/` directory yet, create it too — it's just one extra `mkdir`.

Each subdirectory has a fixed role; see `references/wiki-schema.md` if you need the rationale.

### Step 4 — Stamp the wiki-local CLAUDE.md

Copy `references/template-claude-md.md` into `wikis/<slug>/CLAUDE.md` and substitute these placeholders:

- `{{DOMAIN_TITLE}}` — human-readable title (e.g. "Context Engineering").
- `{{DOMAIN_SLUG}}` — the slug from Step 1.
- `{{DOMAIN_SUMMARY}}` — one-sentence description of the domain (ask the user if absent).
- `{{CREATED_DATE}}` — today's date in YYYY-MM-DD.
- `{{LANG_NOTE}}` — language convention (e.g. "Russian", "English", "Mixed RU/EN — entity titles in English, prose in Russian"). Ask if unclear.

This file is the contract for agents working inside this wiki. It adds domain-specific rules on top of the project-root `CLAUDE.md`; it does not override anything.

### Step 5 — Stamp index.md

Copy `references/template-index-md.md` into `wikis/<slug>/index.md` with the same substitutions.

The index is **hierarchical by design** — it points to per-type sub-indexes (`entities/`, `concepts/`, `sources/`, etc.) rather than listing every page inline. Flat indexes break around 50–100 pages and force the agent to load the whole list whenever it queries a single fact.

Initial section bodies are placeholders ("No entries yet — first ingest will populate this section."). That placeholder is meaningful: it tells future agents the absence of content is expected at this stage, not a lint failure.

### Step 6 — Stamp log.md

Copy `references/template-log-md.md` into `wikis/<slug>/log.md`. Add one initial entry:

```
## [<DATE>] init | Wiki bootstrapped by wiki-llm-builder. <INIT_NOTE>
```

`<INIT_NOTE>` should mention any sources the user named as pending ingests (formatted as "Pending sources: <list>"). If there are none, write `Pending sources: none`.

### Step 7 — Drop in the template entity

Copy `assets/example-entity.md` into `wikis/<slug>/_templates/entity-template.md`.

The `_templates/` folder is **excluded from `wiki-lint`'s citation check** — its content is illustrative, not authoritative. The wiki-local `CLAUDE.md` already documents this exclusion.

The example entity demonstrates:
- YAML frontmatter with all required fields.
- A `## Summary` section with citation markers `^[src:<source-id>:<locator>]`.
- A `## Related` section with `[[wikilinks]]`.
- An `## Open questions` section.

It is obvious to a reader that this is a template: the title says "EXAMPLE — delete after first real entity", and the frontmatter has `status: template`.

### Step 8 — Raw README

Write `wikis/<slug>/raw/README.md`. Keep it short — one paragraph plus a bulleted rules list:

> This directory holds **immutable** source files (PDFs, web-clips, transcripts, paper exports). Drop files here manually.
>
> - Never edit or rename a file in `raw/` — doing so silently breaks every citation pointing to it.
> - New editions of an existing source land as new files (e.g. `gost-r-12345-2024.pdf` becomes `gost-r-12345-2026.pdf`); the old file stays so old citations keep resolving.
> - Source IDs are derived from filenames; see the wiki-local `CLAUDE.md` for the rule.
> - To add a source to the wiki, use the `wiki-ingest` skill.

### Step 9 — Verify and report

List the created tree (e.g. `ls -R wikis/<slug>/` or `Get-ChildItem -Recurse`) and report to the user:

1. The created paths (count + a brief tree).
2. The customized intro paragraph of the wiki-local `CLAUDE.md`, pasted back for confirmation.
3. The next step they should take: invoke `wiki-ingest` with their first source.

**Do not offer to ingest now.** Ingest is a separate skill with its own contract. Suggesting "want me to ingest while we're here?" creates exactly the kind of skill-bleeding this project is structured to avoid. If the user asked you to also ingest, point them at `wiki-ingest` and stop.

## What this skill explicitly does NOT do

- Does **not** download sources from the web.
- Does **not** populate `entities/`, `concepts/`, `sources/`, `contradictions/`, or `data/tables/`. Those are `wiki-ingest`'s job.
- Does **not** run `wiki-lint`. That's a separate skill.
- Does **not** create git commits. Commits are a user-level concern.
- Does **not** modify the project-root `CLAUDE.md` or root `log.md`. The new wiki's existence on disk is enough; there is no central registry to update.

## When the request is adjacent but not a fit

- "Add this source to existing wiki" → `wiki-ingest`, not this skill.
- "Ask the wiki about X" → `wiki-query`.
- "Check the wiki for issues" → `wiki-lint`.
- Project layout is missing entirely (no root `CLAUDE.md`, no `plan/`) → ask the user first whether they want to set up the surrounding scaffold; this skill assumes the project skeleton exists.

Hand off explicitly rather than expanding scope. The four laws of this project depend on each skill staying inside its lane.

## References

Load these on demand:

- `references/wiki-schema.md` — anatomy of wiki pages, full citation format, YAML schema, directory roles.
- `references/template-claude-md.md` — the template stamped into every new wiki-local `CLAUDE.md`.
- `references/template-index-md.md` — the template for the hierarchical index.
- `references/template-log-md.md` — the template for the wiki-local log.
- `assets/example-entity.md` — the template entity page that ships into every new wiki.

For project-wide context: the root `CLAUDE.md` and `harness/architecture.md` define the four laws and the lint contracts this skill encodes.
