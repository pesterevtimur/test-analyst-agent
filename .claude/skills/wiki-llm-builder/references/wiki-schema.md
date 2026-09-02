# Wiki page anatomy

The canonical schema for pages inside any wiki under `wikis/<domain>/`. The `wiki-lint` skill (when implemented) will enforce these rules; for now treat them as the contract every other wiki-skill assumes.

## Table of contents

1. [Page types](#page-types)
2. [YAML frontmatter](#yaml-frontmatter)
3. [Body structure](#body-structure)
4. [Citation markers](#citation-markers)
5. [Wikilinks](#wikilinks)
6. [Tables (the structured layer)](#tables-the-structured-layer)
7. [Directory roles](#directory-roles)

---

## Page types

Every wiki page declares a `type` in YAML frontmatter. The type determines which directory it lives in and which body sections are expected.

| Type            | Directory          | Purpose                                                                    |
| --------------- | ------------------ | -------------------------------------------------------------------------- |
| `entity`        | `entities/`        | A concrete thing: person, organization, library, product, standard.        |
| `concept`       | `concepts/`        | An abstract idea: pattern, technique, principle, model.                    |
| `source`        | `sources/`         | A one-page summary of one raw source — what's in it, how to cite it.       |
| `contradiction` | `contradictions/`  | Where two sources disagree, plus how this wiki resolves the disagreement.  |
| `comparison`    | `concepts/`        | Stitches two or three entities/concepts side by side.                      |
| `template`      | `_templates/`      | Illustrative; excluded from lint.                                          |

## YAML frontmatter

Required:

```yaml
---
type: entity | concept | source | contradiction | comparison | template
slug: kebab-case-unique-within-this-wiki
title: Human-readable title
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft | blessed | stale | template
edition: YYYY.MM
sources:
  - src:source-id-1
  - src:source-id-2
---
```

Optional:

```yaml
related: [other-slug-1, other-slug-2]
tags: [tag1, tag2]
language: ru | en | mixed
```

### Field semantics

- **slug** — lowercase kebab-case, unique within this wiki. Used in filenames and wikilinks.
- **status**:
  - `draft` — newly ingested, not yet reviewed.
  - `blessed` — reviewed, citation coverage validated.
  - `stale` — a referenced source got a new edition; numbers may have changed.
  - `template` — a `_templates/` example; lint-excluded.
- **edition** — coarse-grained version stamp for this page. Bumps on meaningful rewrites, not typo fixes.
- **sources** — flat list of source-IDs. Every source-ID must correspond to a file in `raw/` or to a page in `sources/`.

## Body structure

Required sections, in order:

```markdown
# {{Title}}

## Summary
1–3 paragraphs. Every factual sentence ends with a citation marker.

## Key facts
Bulleted list. Each bullet = one fact + one citation marker.

## Related
- [[wikilink-1]]
- [[wikilink-2]]

## Open questions
What this page does not yet answer. Useful for `wiki-lint` to spot gaps.
```

Optional sections (add as warranted):

- `## History` — for entities/concepts that evolved over time.
- `## Examples` — concrete cases that illustrate the entity/concept.
- `## Counterexamples` — what is NOT this thing.
- `## See also` — pointers to comparison pages, contradictions involving this.

## Citation markers

Format: `^[src:<source-id>:<locator>]`

- `<source-id>` — the stable ID of a source registered in `sources/`. Example: `karpathy-llm-wiki-2026`.
- `<locator>` — where in the source the fact lives. Section number, page, timestamp, paragraph anchor.

Locator examples:

- `§4.2` — section 4.2
- `p17` — page 17
- `0:23:15` — video timestamp
- `¶intro-3` — third paragraph of the intro

Examples in prose:

```markdown
The maximum sustained load is 10 kN ^[src:gost-r-12345-2024:§4.2].

Anthropic published the Skills spec in October 2025 ^[src:anthropic-skills-2025:p1].
```

Rules enforced by `wiki-lint`:

- Every factual sentence (containing a number, date, named entity, quote, or claim) carries a marker.
- Markers go immediately before the sentence-ending punctuation.
- Multiple markers per sentence are allowed when the sentence combines facts from different sources.
- A marker referencing a non-existent source-id is a `broken-citation` failure.

## Wikilinks

`[[slug]]` resolves to the page with `slug: <slug>` in any directory of this wiki. Cross-wiki links use a relative path: `[[../microservices/kafka]]`.

Wiki-lint flags wikilinks that don't resolve. Brand-new wikis will have many — that's expected; the count drops as ingest fills in entities.

## Tables (the structured layer)

If a raw source contains a table, the table's data lives in `data/tables/<slug>.csv` with a sidecar `<slug>.meta.yaml`. The wiki page references the table by relative link; **it never re-flows the rows as prose**.

Sidecar format:

```yaml
---
source: src:gost-r-12345-2024
source_location: §6.1, table 3
extracted: 2026-05-12
columns:
  - name: load_kN
    type: number
    description: Maximum sustained load in kilonewtons.
  - name: temperature_C
    type: number
notes: |
  Original table includes a footnote about test conditions;
  preserved as data/tables/<slug>.notes.md.
---
```

Why this rule exists: prose summaries of tables silently drop precision (rounding, dropped rows, transposed columns). The structured copy preserves fidelity; the page provides the narrative.

## Directory roles

```
wikis/<domain>/
├── CLAUDE.md           Local schema/contract for agents working in this wiki.
├── index.md            Hierarchical entry point; points to per-type sub-indexes.
├── log.md              Append-only journal of ingests, lints, contradictions.
├── entities/           Concrete things.
├── concepts/           Abstract ideas.
├── sources/            One page per raw source: ID, citation format, summary.
├── contradictions/     Disagreements between sources, with resolution field.
├── data/
│   └── tables/         Structured layer. Tables as CSV + .meta.yaml sidecars.
├── raw/                Immutable source files. Never edited.
└── _templates/         Lint-excluded examples; safe to delete.
```
