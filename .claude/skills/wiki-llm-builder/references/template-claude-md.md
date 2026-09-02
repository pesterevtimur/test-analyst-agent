<!--
  TEMPLATE: stamped into wikis/<slug>/CLAUDE.md by wiki-llm-builder.
  Substitute every {{...}} placeholder before writing.
  Delete this comment after stamping.
-->

# CLAUDE.md — {{DOMAIN_TITLE}}

This is the local contract for the `{{DOMAIN_SLUG}}` wiki. Agents working in this directory **read this file first**.

## What this wiki is about

{{DOMAIN_SUMMARY}}

- Created: {{CREATED_DATE}}
- Language convention: {{LANG_NOTE}}

## Laws this wiki inherits from the project root

Restated for self-containment — full versions live in the project-root `CLAUDE.md`.

1. **Wiki content is not written by hand.** Use `wiki-ingest` to add facts and `wiki-query` to retrieve them. Do not edit files under `entities/`, `concepts/`, `sources/`, `contradictions/`, or `data/tables/` directly.
2. **No claim without citation.** Every factual statement carries an inline marker `^[src:<source-id>:<locator>]`. Statements without markers fail `wiki-lint`.
3. **Tables are data, not prose.** Tables from raw sources live in `data/tables/<slug>.csv` with a sidecar `<slug>.meta.yaml`. The wiki page links to the file; it does not re-narrate the rows.
4. **Raw is immutable.** Files in `raw/` are never edited, renamed, or deleted. New editions land as new files; the old file stays so old citations keep resolving.

## Source-ID convention

Source IDs are derived from the filename in `raw/`, minus the extension, lowercased. The publication-year (or edition) suffix is part of the ID. Examples:

- `raw/karpathy-llm-wiki-2026.md` → source-id `karpathy-llm-wiki-2026`
- `raw/anthropic-skills-spec-v1.pdf` → source-id `anthropic-skills-spec-v1`

When a new edition arrives the suffix changes; the old source-id stays valid for already-cited pages until they are re-ingested and updated.

## Lint exclusions specific to this wiki

- `_templates/` — illustrative pages; excluded from citation and wikilink checks.

## Local conventions

_(Add domain-specific conventions here as the wiki matures. Examples to consider as patterns emerge: spelling preferences, how to cite transcripts vs PDFs, whether to keep entity titles in the original language or transliterate.)_

## How to query this wiki

Prefer the `wiki-query` skill. For ad-hoc reads, grep works fine:

```
grep -ri "<term>" wikis/{{DOMAIN_SLUG}}/
```

If this wiki exists and is relevant to the user's question, **do not answer from memory**. Read the wiki, cite it, return.

## How to extend this wiki

1. Drop a source file into `raw/`.
2. Invoke the `wiki-ingest` skill.
3. After ingest, the skill writes a `sources/<id>.md` summary, updates affected `entities/` and `concepts/`, and appends to `log.md`.
4. Run `wiki-lint` (when available) before considering the new content `blessed`.

## Entry point

Start at [`index.md`](./index.md). The index is hierarchical — sub-indexes for each page type — so a query never has to load the entire wiki at once.
