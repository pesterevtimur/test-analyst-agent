<!--
  TEMPLATE: stamped into wikis/<slug>/index.md by wiki-llm-builder.
  Substitute every {{...}} placeholder before writing.
  Delete this comment after stamping.
-->

# {{DOMAIN_TITLE}} — Index

Hierarchical entry point for the `{{DOMAIN_SLUG}}` wiki. Each section below points to a sub-index for that page type.

> **Do not flatten this index.** Listing every page inline forces every query to load the whole list. Sub-indexes let the agent load only the slice it needs.

> **Status:** bootstrapped {{CREATED_DATE}}. No entries yet — the `wiki-ingest` skill populates the sections below as sources arrive.

## Entities

Concrete things — people, organizations, libraries, products, standards.

→ [`entities/`](./entities/) — no entries yet.

## Concepts

Abstract ideas — patterns, techniques, principles, models.

→ [`concepts/`](./concepts/) — no entries yet.

## Sources

One page per raw source. Each page documents the source-ID, citation format, and a one-paragraph summary.

→ [`sources/`](./sources/) — no entries yet.

## Contradictions

Pages documenting where two sources disagree on the same fact, plus how this wiki resolves the disagreement.

→ [`contradictions/`](./contradictions/) — no entries yet. (For a brand-new wiki this is the expected state.)

## Data

The structured layer. Tables extracted from raw sources, stored as CSV with sidecar `.meta.yaml`.

→ [`data/tables/`](./data/tables/) — no entries yet.

## Templates (lint-excluded)

Reference template pages showing the canonical format. Safe to delete once you have real content.

→ [`_templates/`](./_templates/) — currently contains `entity-template.md`.
