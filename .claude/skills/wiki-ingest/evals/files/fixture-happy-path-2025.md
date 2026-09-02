# MoonLib: a tiny key-value store

MoonLib is a fictional in-memory key-value store written in Rust by the (also fictional) MoonLabs team in 2024. This document is a test fixture for the `wiki-ingest` skill — it is intentionally short and dense so that ingest behavior is observable.

## Origin

MoonLib was first released on 2024-03-15 as an open-source project under the MIT license. Its initial author, Lin Yao, designed it as a teaching aid for an "internals of databases" course at MoonLabs Academy. The repository has since grown to 1,200 commits and is maintained by a four-person team.

## Architecture

The library is intentionally narrow in scope: it stores byte-slice keys mapped to byte-slice values, all in-memory, single-threaded. There is no persistence layer and no built-in replication. Reads and writes both complete in O(1) on average via a Robin Hood hash table.

MoonLib's central design choice is the **single-pass invariant**: every public API call must be expressible as exactly one traversal of the underlying table. This choice was made to keep tail latencies predictable; the cost is a smaller surface area (no range queries, no atomic batches).

## Adoption

By 2025 MoonLib was used in at least three production systems at small companies — a niche but real adoption story. The maintainers have explicitly declined to add a persistence layer despite community pressure, citing the single-pass invariant.
