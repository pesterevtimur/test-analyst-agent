# Check 4 — table-as-prose

A paragraph or bullet list that contains tabular data restated as prose violates law #4 of the project. The fix is always the same: extract the data to `<target_wiki>/data/tables/<slug>.csv` and link from the page. This check flags the violations so `wiki-lint-fix` (future) or a human can act.

## The heuristic

A block is a `table-as-prose` candidate iff:

1. It contains **≥3 distinct numeric values** (numbers + optional units).
2. The block is a paragraph, bullet list, or numbered list (not a markdown table).
3. There is no link to `data/tables/*.csv` in the same paragraph or in the surrounding ~3 lines of the block.

If all three hold, emit a finding.

## Why these three rules

- **≥3 numbers** is the threshold where prose stops being a discussion and starts being data. Two numbers can be a comparison sentence ("X is 10% faster than Y"). Three start to look like the same metric across categories or the same category across metrics — i.e. a row or column.
- **Not a markdown table** is obvious; markdown tables are fine (and `wiki-ingest` should still have moved them to CSV, but a markdown table on a wiki page is a separate-but-easier fix).
- **No link to a CSV** is the exit: if the page properly links to the structured copy, we treat the numbers as *recap referencing the canonical source*, which is the right pattern. The actual CSV is the source of truth; the page is allowed to cite specific values *back* to that CSV.

## Number detection

Use a tolerant regex to extract numeric tokens:

```
(?<![\w.])\d+(?:[\.,]\d+)?(?!\w)
```

Then post-filter: a token counts toward the threshold iff it is **not**:
- A date (year `(19|20)\d{2}` or `YYYY-MM-DD` pattern).
- A version (`v\d+\.\d+`).
- A section/list ordinal in the immediately preceding context (`step 1`, `Section 4`).

The reason for post-filtering: dates and versions are common in prose and would inflate the count without being tabular.

## Block boundaries

A "block" is:

- **Paragraph**: lines between two blank lines (or between blank line and EOF/start).
- **Bullet list**: a contiguous run of lines starting with `- ` or `* ` or `+ `.
- **Numbered list**: a contiguous run of lines matching `^\s*\d+\.`.

When checking a list, count numbers across all items combined. Three numbers across three bullets still counts.

## The "link to data/tables" exemption

The exemption recognizes any of:

- An inline link like `[Performance](../data/tables/performance.csv)` in the block.
- A reference link `[Performance][benchmarks]` where `[benchmarks]: ../data/tables/...` lives somewhere in the file.
- A bare path mention like `see data/tables/performance.csv` within ~3 lines of the block.

The exemption is generous on purpose: the goal of this check is to catch *missing* references to the structured copy, not to enforce a specific link format.

## What this check does NOT do

- **Convert prose to a table.** That's the job of `wiki-lint-fix`. v0 only flags.
- **Verify the linked CSV is real.** Broken-link-style checks for the CSV exemption belong to `broken-citation` (or a future `broken-link`). Here we only check that a link is *present*.
- **Catch sparse tabular content.** A paragraph with two numbers is below threshold. That's by design — false-positives at threshold 2 would be unworkable.

## False-positive patterns

The following blocks look table-ish but should NOT trigger this check:

- **YAML frontmatter.** Skipped wholesale.
- **`## Open questions` blocks** containing numbered metrics-to-investigate ("What's the throughput? What's the p99? What's the memory?"). Numbers here are interrogative, not declarative. If the questions actually contain numbers, manually inspect; the heuristic may misfire and that's acceptable — false positives at low rate are cheap.
- **`## Citation format` blocks** on source pages, which often quote section markers like `§1.2`, `§4.5`. These are locators, not data.
- **Code blocks.** Numbers inside `` ``` `` are skipped.

## Finding emission

```
- `<path>:<line>` — <first 80 chars of the offending block>
  evidence: <N> numeric values in <block-type>, no link to data/tables/
```

Where `<block-type>` is `paragraph`, `bullet list`, or `numbered list`.

If a block has multiple offending sub-sequences (e.g. a long bullet list that crosses the threshold midway), emit one finding per block, not per sub-sequence. The block is the actionable unit.

## Threshold tuning

The default threshold `≥3` is chosen to match the master-plan's example "three values like A=10, B=20, C=30". If false-positive rate in real wikis is too high in practice (you'll see this on the first wiki-lint run against context-engineering), the right fix is to raise the threshold to 4 and document the change. Do not loosen the link-exemption — that path leads back to "tables are data, sometimes prose, depending".
