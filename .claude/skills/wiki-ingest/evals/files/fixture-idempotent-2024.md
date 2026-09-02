# StarStore: a graph store for tests

StarStore is a fictional graph database used here as a fixture for the `wiki-ingest` idempotency test. The point of this fixture is not that ingest extracts something interesting from it — the point is that a prior ingest of this exact source (at the same edition) already exists, and the skill must detect that and stop.

## Origin

StarStore was released in 2024 by the (fictional) StarLabs team as an experimental property-graph store. It is single-node, in-memory, and supports a small subset of openCypher queries.

## Why this fixture

This fixture is paired in the eval with a pre-existing `sources/fixture-idempotent-2024.md` page in the test wiki. The skill should:

1. Compute the source-id `fixture-idempotent-2024`.
2. Find the existing source page with the same edition (`2024`).
3. Stop with a warning that names the existing page and suggests the rename-with-new-edition path.
4. Append a `note` entry to `log.md`.
5. Create **no** new entities, concepts, or tables.
