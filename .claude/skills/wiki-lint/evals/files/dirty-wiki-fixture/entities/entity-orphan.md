---
type: entity
slug: entity-orphan
title: Entity Orphan
created: 2025-01-01
updated: 2025-01-01
status: draft
edition: 2025
sources:
  - src:fake-source-2025
tags: [fixture]
---

# Entity Orphan

## Summary

This entity has zero inbound wikilinks anywhere in the fixture. It is also not referenced in `index.md`. That means lint should emit both `orphan-page` and `unindexed-page` findings for this page.

The source's average latency observation is 3 ms ^[src:fake-source-2025:§methods].

## Key facts

- Released in 2025 ^[src:fake-source-2025:§introduction].

## Related

- (intentionally none — keeping this page in isolation tests the warning checks)

## Open questions

- None.
