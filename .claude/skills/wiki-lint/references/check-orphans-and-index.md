# Check 5–8 — graph and index integrity

Four warning-level checks that all care about the wiki's *navigability*: can a reader (or another agent) get from `index.md` to every page, and is every page reachable via at least one inbound wikilink?

## Wikilink syntax

A wikilink is `[[<slug>]]` or `[[<slug>|<label>]]`. The slug between the brackets must match a `slug` field in some page's frontmatter (within this wiki).

When building the inbound-link graph:

- Extract all `[[<slug>]]` and `[[<slug>|...]]` occurrences from every non-template, non-raw page (including in `Related` sections and prose).
- The "graph node" for a page is its `slug` field (not its filename — they should match, but slug is authoritative).
- Edge `A → B` if page `A`'s body contains `[[<B's slug>]]`.

## Check 5 — orphan-page

A page is an orphan if no other page in this wiki links to it.

For each page in inventory:

- Count inbound edges (from the graph above).
- If count == 0 AND the page is not a "root type", emit a finding.

**Root types — pages that may legitimately have zero inbound links:**

- `type: source` — source pages are entry points by their own role; they don't need inbound links from entities/concepts (entities/concepts often link back to *them*, not the other way around, but that's not required).
- `type: template` — illustrative; excluded by Step 1 already.
- `type: contradiction` — appearing in a special index in `index.md` counts as not-orphan via `unindexed-page` instead.

**A note on direction.** Inbound, not outbound. A page with no *outbound* wikilinks may still be perfectly useful (e.g. a glossary definition). What we care about is whether someone navigating the wiki can *reach* this page.

Finding format:

```
- `<relative-path>` — slug `<slug>` has 0 inbound wikilinks
```

Order: by relative-path.

## Check 6 — unresolved-contradiction

Every file under `<target_wiki>/contradictions/` must have a `resolution:` field in its YAML frontmatter. The field's value should be:

- A short string explaining how this wiki resolves the contradiction (e.g. `"defer to source X as more recent"`).
- Or one of the special tokens: `pending` (intentionally unresolved, awaiting more info), `wontfix` (the contradiction is a feature of the domain).

If the frontmatter has no `resolution:` field or the field is empty/null, emit a finding:

```
- `<relative-path>` — frontmatter missing `resolution:` field
```

`resolution: pending` is **not** flagged — it counts as an explicit decision. `resolution:` followed by empty value (or no field at all) is the failure.

## Check 7 — flat-index

`<target_wiki>/index.md` is the entry point. It should be hierarchical (per `wiki-llm-builder`'s schema) — sub-sections per page-type, each linking to a sub-index. A flat list of every page inline gets unwieldy past ~50 entries.

Heuristic: emit a single `flat-index` finding iff

- `index.md` has more than **100 lines**, AND
- It contains fewer than **3 `##`-level headings**.

That's a coarse signal that the index has gone flat as content grew.

Do NOT emit for short indexes (< 100 lines is fine even flat).
Do NOT emit if the index has the structure but is empty per type (a hierarchical fresh wiki is still hierarchical).

Finding format:

```
- `index.md:1` — index has <N> lines, <M> `##` sub-sections (expected hierarchical structure)
```

## Check 8 — unindexed-page

For each page in inventory (excluding root types `source` and `template`), check whether `index.md` references the page in any of these forms:

- The slug as a wikilink `[[<slug>]]`.
- The relative path as a markdown link `(./entities/<slug>.md)` or `(entities/<slug>.md)`.
- The slug as plain text (last-resort match).
- The directory the page lives in is linked, AND the page is the only page in that directory (single-page section counts as indexed).

A page that fails all four checks is unindexed.

Sources (`type: source`) are exempted because some wikis prefer to list sources in the `Sources` sub-index rather than the main index. Sub-index coverage is a v0.2 concern.

Finding format:

```
- `<relative-path>` — slug `<slug>` not referenced in index.md
```

## Why these are warnings, not critical

A wiki with broken or missing citations is *wrong*. A wiki with orphan pages or a flat index is *messy*. The first poisons facts; the second slows navigation. Different severities reflect this. Some wikis at early ingest will have many warnings — that's expected, and the human triages them over the wiki's lifetime.

## The "first-ingest" pattern

For a wiki with one or two ingested sources, you will commonly see:

- Several orphan entities (no other source has mentioned them yet — they will gain inbound links as ingest proceeds).
- Several unindexed pages (the index hasn't been updated to list each individually; only the sub-index pointer exists).

This is healthy noise. Document the expected pattern in the report's `## How to act on this` block: don't tell the user to "fix every warning" on a one-source wiki; tell them which warnings are normal-at-this-stage and which are not.

For v0, output the findings as-is and trust the human to triage.
