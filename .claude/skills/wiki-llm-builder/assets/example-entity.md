---
type: template
slug: entity-template
title: EXAMPLE — delete after first real entity
created: 2026-05-12
updated: 2026-05-12
status: template
edition: 2026.05
sources:
  - src:example-source-2026
tags: [template]
---

# EXAMPLE — delete after first real entity

> **This is a template page.** It demonstrates the canonical format every real entity page in this wiki should follow. It lives in `_templates/` and is excluded from `wiki-lint`'s citation checks. Delete (or just leave) once the wiki has its first real entity.

## Summary

This page exists solely to demonstrate format. A hypothetical Example Project ships with a documented config interface ^[src:example-source-2026:§intro]. The reference is illustrative — there is no `raw/example-source-2026.*` file in this wiki, which is exactly why this page lives in `_templates/` and not in `entities/`.

## Key facts

- The example numeric value is 42 ^[src:example-source-2026:p3].
- Citation markers go immediately before the closing punctuation of the sentence ^[src:example-source-2026:§format-rules].
- The marker syntax is `^[src:<source-id>:<locator>]` — see the wiki-local `CLAUDE.md` for the full rule and the project-root `harness/architecture.md` for the rationale.

## Related

- [[some-other-entity]] — not yet ingested; unresolved wikilinks are surfaced (but not failed) by `wiki-lint` for new wikis.

## Open questions

- What does a real entity in this wiki look like? → Run `wiki-ingest` against a real source to find out.

## How to use this template

1. Copy this file into `entities/<your-slug>.md`.
2. Update the YAML frontmatter: set `type: entity`, real `slug`, real `title`, `status: draft`, and real `sources`.
3. Replace the example prose with content drawn from the actual source.
4. Verify every factual sentence has a citation marker pointing at a real `raw/` file.
5. You can leave this `_templates/` copy in place — `wiki-lint` skips it.
