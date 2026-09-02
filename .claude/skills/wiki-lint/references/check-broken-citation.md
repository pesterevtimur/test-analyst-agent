# Check 2 — broken-citation

A citation marker `^[src:X:Y]` is **broken** if either:

- `X` (the source-id) does not correspond to a real source page in this wiki, OR
- `Y` (the locator) does not resolve inside the raw file for `X`.

A wiki page with broken citations is worse than a page with missing ones — the page *looks* trustworthy (it has markers) but the references resolve to nothing. This is critical.

## Resolving the source-id

The source-id `X` is valid in this wiki iff `<target_wiki>/sources/<X>.md` exists AND its frontmatter `slug` field equals `X`.

The slug-match check matters: if someone renames a source file but not its `slug` field, you get a phantom source — file exists, but it isn't really the source the citation refers to.

Edge: the source page itself may cite its own source-id (`sources/karpathy-llm-wiki-2026.md` may contain `^[src:karpathy-llm-wiki-2026:...]`). This is the canonical self-cite pattern. Allowed.

## Resolving the locator

Locator format varies by source type. The source page's `## Citation format` section declares the format used. Common locator schemes:

| Form | What it points at | How to resolve |
|---|---|---|
| `§<heading-slug>` | A markdown heading in the raw file | Find a heading line in the raw whose slugified text equals `<heading-slug>` |
| `¶<n>` | The n-th paragraph from the start of the doc (or from nearest prior heading) | Count paragraphs in the raw file |
| `p<N>` | Page N of a PDF | Out of v0 scope — flag as `unsupported-locator` (treated as warning) |
| `<HH:MM:SS>` | A timestamp in a transcript | Out of v0 scope — same |
| `§<section-number>` | A numbered section in a spec doc | Find heading text matching `<section-number>` (regex `^#+\s+<num>(\.|\s)`) |

For v0, **markdown raw files only**. The locator is treated as `§<slug>` unless it starts with `¶` (then paragraph anchor).

## Heading-slug rules (must match what wiki-ingest used)

- Lowercase.
- Whitespace and punctuation → `-`.
- Strip leading/trailing `-`; collapse repeated `-`.
- Non-ASCII letters kept as-is (or transliterated — whichever wiki-ingest decided; lint must use the same rule).

Build the heading map by reading the raw file line-by-line, finding lines starting with `#`, extracting the heading text after the hash run, and slugifying. Cache the resulting `{ slug → line-number }` map per source-id.

## Detection

For each `^[src:X:Y]` marker in any non-raw, non-template page:

1. **X-lookup.** If `<target_wiki>/sources/<X>.md` not in the inventory, emit:
   ```
   - `<path>:<line>` — `^[src:<X>:<Y>]` → sources/<X>.md not found
     evidence: source page does not exist in this wiki
   ```
2. **Y-lookup.** Use the raw file pointed at by the source page (typically `<target_wiki>/raw/<X>.<ext>`). If the locator is `§<slug>` and `<slug>` is not in the heading map, emit:
   ```
   - `<path>:<line>` — `^[src:<X>:§<slug>]` → §<slug> not in raw/<X>.<ext>
     evidence: heading-map has <N> headings; nearest is "<closest-by-edit-distance>"
   ```
   For `¶<n>` locators, if `<n>` exceeds the paragraph count of the raw, emit similarly.

3. **Unsupported-locator.** For locators starting with `p` or matching `\d{2}:\d{2}:\d{2}`, emit a finding with severity-note `unsupported in v0`. This is technically a critical finding, but mark it clearly — the user may have legitimately ingested a PDF and wiki-lint v0 doesn't know how to verify.

## Suggesting the nearest correct slug

When a `§<slug>` doesn't resolve, find the closest match in the heading map by token Jaccard or simple Levenshtein and include it in the evidence line. This makes the report immediately actionable — usually the right answer is "you wrote `§indexing-logging` but the heading slug is `indexing-and-logging`".

## What if the raw file is missing

If a source page exists in `<target_wiki>/sources/<X>.md` but the corresponding raw file (e.g. `raw/<X>.md`) does not exist, treat every citation referencing `X` as broken with evidence:

```
evidence: raw file raw/<X>.md not found; cannot verify any locator under this source
```

Emit one finding per affected citation (not one rolled-up finding). The reason: each affected citation may have a different surrounding context, and the future `wiki-lint-fix` will need them individually.

## Order

Findings within `broken-citation` are ordered first by source-id, then by relative-path, then by line. This makes the report skim-friendly (all citations to one source cluster together).
