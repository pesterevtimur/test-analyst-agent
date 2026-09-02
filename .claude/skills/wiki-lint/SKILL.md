---
name: wiki-lint
description: Audit a bootstrapped LLM Wiki for the eight project-defined health invariants: missing citations, broken citations, stale claims (source-edition drift), table-as-prose violations, orphan pages, unresolved contradictions, flat index, and unindexed pages. Returns a deterministic, severity-ranked report (critical vs warning) the user or a future `wiki-lint-fix` skill can act on. Use whenever the user wants to lint, audit, health-check, validate, or "check what's wrong with" a wiki, e.g. "lint the context-engineering wiki", "проверь wikis/microservices на ошибки", "health-check this wiki", "what's wrong with wikis/X". Use even when the user does not literally say "lint": phrases like "is this wiki ready to ship", "audit my wiki", or "find problems" should trigger this skill. v0 is read-only, it never edits the wiki; fixes belong to a future companion skill. Takes an explicit `target_wiki` absolute path, so it works on real `wikis/<domain>/` and on eval-sandbox wikis uniformly.
---

# Wiki Lint (v0)

Audit one bootstrapped LLM Wiki against the eight project health invariants. Emit a deterministic, severity-ranked report.

## What this skill is for and not for

**For:** auditing an existing wiki. Reading every page under `<target_wiki>/`, every citation marker, every wikilink, and reconciling with `<target_wiki>/raw/` and `<target_wiki>/index.md` to find violations of the project's eight lint contracts.

**Not for (v0):**
- **Fixing.** This skill is read-only. It writes one report file (and one optional `log.md` warning todo). It does not modify wiki content. Fixes are a future skill (`wiki-lint-fix`).
- **Cross-wiki linting.** One wiki per invocation.
- **Replacing `wiki-query`.** Lint is structure-only; it does not answer content questions.

The "no fixing" rule is deliberate. A lint that fixes is a lint that hides which findings the author was on the hook for vs which were auto-resolved. Keeping lint and fix in separate skills makes the human review cheap and the failure modes legible.

## When you should trigger

Phrases:
- "lint the context-engineering wiki"
- "проверь wikis/microservices на ошибки"
- "health-check my wiki"
- "audit the wiki"
- "is wikis/X ready to ship"
- "what's wrong with my wiki"

If the user gives you a wiki that hasn't been bootstrapped (no `CLAUDE.md`, no `log.md`), stop and point them at `wiki-llm-builder`.

If the user wants to "fix" something the lint found, say it: that's a future skill, not this one. Offer to write a per-finding todo list they can work through manually if useful.

## Inputs

- **`<target_wiki>`** — absolute path to the wiki root (the directory containing `CLAUDE.md`, `index.md`, `log.md`, the subdir tree). Same convention as `wiki-ingest` v0.1.
- (Optional) **`--severity`** — `critical` (skip warnings) or `all` (default). Used when the user wants a quick gate-check, not a full audit.

Refuse if `<target_wiki>/CLAUDE.md` does not exist.

## The eight checks

The full table with rationale and detection rules lives in the project's `harness/architecture.md` (section 6). Brief reminders here; load the relevant `references/` file when you need to actually implement a check.

| # | Name | Severity | One-line meaning |
|---|---|---|---|
| 1 | `missing-citation` | **critical** | A factual sentence without a `^[src:...]` marker |
| 2 | `broken-citation` | **critical** | A marker pointing at a non-existent source-id or non-existent heading slug |
| 3 | `stale-claim` | **critical** | A page citing a source whose `edition` no longer matches the source page's `edition` |
| 4 | `table-as-prose` | **critical** | Numeric-dense prose that should have been a CSV |
| 5 | `orphan-page` | warning | A wiki page with zero inbound `[[wikilinks]]` |
| 6 | `unresolved-contradiction` | warning | A file in `contradictions/` without a `resolution:` field |
| 7 | `flat-index` | warning | `index.md` > 100 lines without sub-section anchors |
| 8 | `unindexed-page` | warning | An existing page not referenced from `index.md` |

Reference files map 1-to-1 by topic group (and you only need to read the ones you're working on):

- `references/check-missing-citation.md` — what counts as a "factual sentence", how to scan, false-positive patterns (template pages, `_templates/` exclusion).
- `references/check-broken-citation.md` — source-id resolution, heading-slug parsing of raw files, paragraph-anchor fallback.
- `references/check-table-as-prose.md` — the numeric-density heuristic, table-link allowance, when to escalate.
- `references/check-orphans-and-index.md` — wikilink graph, slug-to-page resolution, index-coverage diff.

## Procedure

Each step has a *why* and a *how*.

### Step 1 — Validate target_wiki

- `<target_wiki>` must be an absolute path to an existing directory containing `CLAUDE.md`, `log.md`, `index.md`. Refuse otherwise.
- Skip any subdirectory whose name starts with `_` (e.g. `_templates/`, `_workspace/`, `_lint/`). Those are illustrative, scratch, or lint-output; the wiki contract does not apply to them.
- Do not lint files in `<target_wiki>/raw/`. Raw is immutable and not authored by wiki-skills — different contract.

The early refusal prevents writing a confusing partial report against a wiki that isn't real yet.

### Step 2 — Build the page inventory and the heading-map cache

Use `Glob` to list every `*.md` file under `<target_wiki>` excluding `raw/` and `_*` subdirectories. For each, read the YAML frontmatter and store: `path`, `type` (entity/concept/source/contradiction/comparison/template), `slug`, `edition`, `sources` list.

Then, for each unique source-id referenced anywhere in this wiki, read the corresponding raw file under `<target_wiki>/raw/<source-id>.<ext>` once and build a heading map (`{ heading-slug → line-number }`). Cache this map per source-id — it gets reused across every `broken-citation` and `stale-claim` check.

Doing inventory + heading-maps up front means the actual check loop is a flat scan with no extra file I/O. Slow lints come from re-reading files; this avoids that.

### Step 3 — Run the four critical checks

For each markdown file in the inventory (skip pages with `status: template`):

- **`missing-citation`** — scan sentences. For each sentence containing a "factual signal" (number, date, named entity, direct quote, comparative claim — see `references/check-missing-citation.md`), check that a `^[src:...]` marker appears before the closing punctuation. Emit a finding per offending sentence with file:line and the first ~80 chars of the sentence.

- **`broken-citation`** — for each marker `^[src:X:locator]` in the file, look up `X` in the inventory's `sources/` list and look up `locator` in the source-id's heading-map. If either lookup fails, emit a finding with the failing piece quoted.

- **`stale-claim`** — for each `src:X` in a page's `sources` frontmatter list, compare the page's own `edition` field to the corresponding `sources/X.md`'s `edition` field. If they differ AND the page's `status` is not `stale` already, emit a finding.

- **`table-as-prose`** — see `references/check-table-as-prose.md` for the heuristic. Default: any paragraph or bullet list with ≥3 distinct numeric values and no link to a `data/tables/*.csv` is a candidate. Emit a finding with the offending block quoted.

Why critical: a wiki that violates any of these has lost its truth contract — facts without provenance, citations to nothing, or numbers nobody can verify. These are the same four contracts `wiki-ingest` is told to never produce; lint catches whatever leaks through.

### Step 4 — Run the four warning checks

- **`orphan-page`** — build the inbound-wikilink graph: for each page slug, count how many other pages contain `[[<slug>]]`. Any slug with zero inbound links (excluding pages whose own type makes them roots: `source` pages, `template`) is a candidate. Emit a finding per orphan.

- **`unresolved-contradiction`** — for each file under `<target_wiki>/contradictions/`, read its frontmatter; if `resolution` field is missing or empty, emit a finding.

- **`flat-index`** — `<target_wiki>/index.md`: if line count > 100 AND it has no `<a name="...">` anchors or sub-section `##`/`###` headings, emit a single finding.

- **`unindexed-page`** — for each page in the inventory, check whether its slug or path appears anywhere in `index.md`. If not, emit a finding.

Why warning, not critical: these dilute findability and graph quality but don't poison facts. Worth flagging, not worth blocking.

### Step 5 — Build the report

Use the exact deterministic template below. The format matters because a future `wiki-lint-fix` will parse this report; humans also need to scan it without surprises.

```
# wiki-lint report — <target_wiki>
Run: <YYYY-MM-DD>
Citation coverage: <N>/<total> factual sentences = <pct>%

## Summary
- critical: <count> (<count-by-category-comma-separated>)
- warning: <count> (<count-by-category-comma-separated>)

## Critical findings

### missing-citation (<count>)
- `<relative-path>:<line>` — <fact preview, ≤80 chars>
  evidence: <one-line reason>

(... or "_None._" if zero ...)

### broken-citation (<count>)
- `<relative-path>:<line>` — `^[src:X:Y]` → <X.md not found OR §Y not in raw/X.<ext>>
  evidence: <details>

### stale-claim (<count>)
- `<relative-path>` — page edition `<X>` vs source `<Y>` edition `<Z>`
  evidence: source page <sources/Y.md>

### table-as-prose (<count>)
- `<relative-path>:<line>` — <≤80-char preview of the dense block>
  evidence: <N> numeric values in <block-type>, no link to data/tables/

## Warnings

### orphan-page (<count>)
- `<relative-path>` — slug `<slug>` has 0 inbound wikilinks

### unresolved-contradiction (<count>)
- `<relative-path>` — frontmatter missing `resolution:` field

### flat-index (<count>)
- `<relative-path>:1` — index has <N> lines, no sub-section anchors

### unindexed-page (<count>)
- `<relative-path>` — slug `<slug>` not referenced in index.md

## Per-page summary
| page | critical | warning |
| --- | ---: | ---: |
| sources/<id>.md | 0 | 1 |
| entities/<slug>.md | 2 | 0 |
| ...                |   |   |

## How to act on this
- Critical findings should be fixed before further ingest into this wiki.
- Warnings are append-to-todo, not blockers.
- v0 of this skill is read-only — fixes are the user's responsibility (or a future `wiki-lint-fix` skill).
```

Citation coverage = (factual-sentences-with-marker) / (total-factual-sentences). 100% = zero `missing-citation` findings.

If a section has zero findings, write `_None._` under the heading. The skeleton stays — never delete sections from the report. A consumer parser depends on the section being present.

### Step 6 — Write the report and the log entry

Write the report to `<target_wiki>/_lint/wiki-lint-<YYYY-MM-DD>.md`. (Create the `_lint/` subdirectory if missing — `Write` does this implicitly.)

**Why the filename does NOT match `report-*`.** Discovered on day 3: some subagent harnesses in Claude Code block `Write` calls whose filename matches `report-*.md`, with the message "Subagents should return findings as text, not write report files." The block does not apply to the `_lint/` directory itself, only to that filename pattern. Using `wiki-lint-<date>.md` keeps the path semantically clear and works inside subagent invocations. When the skill is invoked from a parent session (no subagent), either filename would work; the project uses `wiki-lint-<date>.md` uniformly so the convention is portable.

The `_lint/` directory starts with `_` which means subsequent lint runs will exclude it from inventory (per Step 1). That avoids a feedback loop where lint reports appear as lint candidates.

If there are warnings OR critical findings, append one line to `<target_wiki>/log.md`:

```
## [<YYYY-MM-DD>] lint | <N-critical> critical, <M-warning> warning. Report: _lint/wiki-lint-<date>.md
```

(Earlier spec said warnings only. Day-3 first real run found 8 critical and 0 warning, meaning no log line at all — a real lint run left no trace in the wiki. That is wrong. Critical findings are MORE important to surface in the log, not less. The rule is now: append for any non-zero finding count.)

Skip the log line only for a truly clean run (`0 critical, 0 warning`). Critical findings are reported in the report file; the log line just makes their existence discoverable via `grep "^## \[" log.md`.

### Step 7 — Verify and report back to the user

Before claiming success:
- The report exists and has all eight section headings (even if empty).
- The "Per-page summary" table sums match the per-category counts (sanity check).
- If `--severity critical` was passed, the warnings sections still exist with their counts; just no detail rows.

Report to the user:
- Path to the report.
- The Summary block, verbatim.
- A one-line read: "0 critical, N warning" → "wiki is healthy at the contract level"; "K critical → fix before more ingest".

**Important:** when the user asks for the report content (or the orchestrator forwards it to a human reviewer), return the **entire** report, not a summary. The whole point of including warnings is for a human to triage them; collapsing the report to the summary defeats the purpose.

## Edge cases worth knowing

- **Mixed-language wiki.** The numeric-density heuristic for `table-as-prose` does not care about prose language. The factual-sentence detector for `missing-citation` *does* — see `references/check-missing-citation.md` for the multilingual patterns.
- **Source page citing itself.** Allowed and not flagged. A source page summarizes its own content; citations like `^[src:karpathy-llm-wiki-2026:§the-core-idea]` on the source's own page resolve normally.
- **`_templates/` pages.** Excluded from every check (their `status: template` and their `_` prefix both suffice; the exclusion is belt-and-braces).
- **Pages with `status: stale`.** Excluded from `stale-claim` (they're already marked). Still scanned for other invariants.
- **First-ingest wikis.** Will have many orphans (entities not yet cross-linked) and many unindexed pages. Both are warnings, not critical — and a new wiki naturally has them. Don't panic at high warning counts in a fresh wiki.

## What if you can't run the full check

If `Glob` or `Read` fails on a specific file (encoding, permissions), record that file in a `## Skipped` section at the bottom of the report with the reason. Do not abort the whole run for one bad file. Partial reports are useful; aborted runs are not.

## References

- `references/check-missing-citation.md`
- `references/check-broken-citation.md`
- `references/check-table-as-prose.md`
- `references/check-orphans-and-index.md`
- `harness/architecture.md` section 6 — authoritative table of the eight invariants.
- `harness/tools/lint/README.md` — planned deterministic helper scripts for these checks.
