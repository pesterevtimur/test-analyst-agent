---
type: entity
slug: entity-stale
title: Entity Stale
created: 2025-01-01
updated: 2025-01-01
status: draft
edition: 2024
sources:
  - src:fake-source-2025
tags: [fixture]
---

# Entity Stale

## Summary

This page's frontmatter `edition` is `2024`, but the source it cites (`fake-source-2025`) is at edition `2025`. That mismatch is the stale-claim defect; the page should be re-processed (or marked `status: stale`) by `wiki-ingest`, but lint must flag it first.

The source's average latency is 3 ms ^[src:fake-source-2025:§methods].

## Key facts

- Released in 2025 ^[src:fake-source-2025:§introduction].

## Related

- [[clean-entity]]

## Open questions

- None.
