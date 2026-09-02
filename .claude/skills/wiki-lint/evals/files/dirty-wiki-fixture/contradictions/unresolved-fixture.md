---
type: contradiction
slug: unresolved-fixture
title: Unresolved Fixture Contradiction
created: 2025-01-01
updated: 2025-01-01
status: draft
edition: 2025
sources:
  - src:fake-source-2025
tags: [fixture]
---

# Unresolved Fixture Contradiction

## Summary

This file's frontmatter intentionally omits the `resolution:` field. That is the `unresolved-contradiction` warning. Lint must detect it.

## The disagreement

Two phantom sources disagree on the average latency: 3 ms vs 5 ms ^[src:fake-source-2025:§methods].

## Resolution

(empty — exactly the defect under test)
