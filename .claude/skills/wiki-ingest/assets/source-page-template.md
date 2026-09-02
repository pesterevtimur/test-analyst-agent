<!--
  TEMPLATE: stamped by wiki-ingest into wikis/<wiki>/sources/<source-id>.md.
  Substitute {{...}} placeholders.
  Delete this comment after stamping.
-->
---
type: source
slug: {{SOURCE_ID}}
title: {{SOURCE_TITLE}}
created: {{TODAY}}
updated: {{TODAY}}
status: draft
edition: {{EDITION}}
sources:
  - src:{{SOURCE_ID}}
tags: []
---

# {{SOURCE_TITLE}}

## Summary

{{ONE_TO_TWO_PARAGRAPH_SUMMARY_WITH_CITATIONS}}

## Citation format

For citations to this source, use the marker `^[src:{{SOURCE_ID}}:§<heading-slug>]`. Example: `^[src:{{SOURCE_ID}}:{{EXAMPLE_LOCATOR}}]`.

When a fact sits between two headings, cite the closest preceding heading. When there are no headings, fall back to `¶<n>` (n-th paragraph). See the wiki-local `CLAUDE.md` for the full rule.

## Key sections

A one-line description of each top-level heading in the source, mapped to its slug. Useful for future agents picking locators.

{{HEADING_MAP}}

## Open questions

Things the source mentioned that are worth ingesting in a future pass but were left out of this one (entity/concept cap, deferred tables, etc.).

{{OPEN_QUESTIONS}}
