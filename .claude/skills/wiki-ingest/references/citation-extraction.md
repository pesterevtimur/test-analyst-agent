# Citation extraction

Rules for emitting citation markers `^[src:<source-id>:<locator>]` as you write wiki pages.

## Marker format

`^[src:<source-id>:<locator>]`

- `<source-id>` — fixed per ingest; computed in Step 2 of the main procedure.
- `<locator>` — depends on the source type. See sections below.

## Locator format by source type

### Markdown sources (v0 default)

`§<heading-slug>` — where `<heading-slug>` is the kebab-case slug of the closest heading **at or above** the cited fact.

Heading-slug rules (mirror Step 3 of the main procedure):

- Lowercase.
- Whitespace and punctuation → `-`.
- Strip leading/trailing `-`; collapse repeated `-`.
- Non-ASCII letters → transliterate when reasonable; otherwise keep as-is (URL-encoded if needed).

Examples:

| Heading | Slug |
| --- | --- |
| `# Introduction` | `introduction` |
| `## Operations → Ingest` | `operations-ingest` |
| `### What is qmd?` | `what-is-qmd` |
| `#### Edge cases & caveats` | `edge-cases-caveats` |

### Paragraph-anchor fallback

When the source is a flat document (no headings), use `¶<n>` where `<n>` is the 1-based paragraph index from the start of the document. A "paragraph" is a block of consecutive non-empty lines separated from neighbors by a blank line.

When a fact sits **between** two headings (i.e. under the previous heading), still use the previous heading. The paragraph-anchor is the fallback only when no heading precedes the fact.

### PDF sources (out of scope for v0; documented for forward compat)

`p<N>` — page number. Optionally `p<N>:§<heading-slug>` if the PDF has structured headings.

### Video/audio transcripts (out of scope for v0)

`<HH:MM:SS>` — timestamp at the start of the speech the fact came from.

### Spec/standard documents with numbered sections

`§<section-number>` — use the source's own section numbering. E.g. `§4.2`, `§A.1.3`.

This locator type is allowed for markdown sources too if the source uses explicit section numbering in its headings. Pick the form that is unambiguous when read in isolation.

## What counts as a factual sentence

You must place a marker before the closing punctuation of any sentence that contains:

- A **number** other than purely decorative ones — `10 kN`, `version 4.2`, `42 papers`. Not: "step one", "first", "a few".
- A **date or time period** — `2024`, `Q4 2025`, `since the GPT-3 paper`.
- A **named entity** mentioned as a fact, not a generic reference — `Anthropic released X`, `Karpathy wrote Y`. Not: `the company released X` (anonymized).
- A **direct quote** of any length.
- A **causal or comparative claim** — `X causes Y`, `X is faster than Y`, `because of Z`.
- A **specific procedural detail** that could be wrong if mis-remembered — `the algorithm runs in 3 passes`, `the config file lives at /etc/foo`.

You do **not** need a marker on:

- Section-structure prose ("The next section covers...").
- Pure opinion sentences ("This approach feels promising.") — but flag them with status `draft` to give `wiki-lint` something to grab.
- Restatements of the page's own purpose ("This page documents X.").

## When a sentence combines facts from two sections

Use both markers in the sentence — one before each fact's closing context. Example:

> The library was originally published in 2024 ^[src:karpathy-llm-wiki-2026:§history], and it now powers three production deployments ^[src:karpathy-llm-wiki-2026:§adoption].

When two facts in a single clause come from two sections, put both markers at the end:

> The library is fast and well-adopted ^[src:karpathy-llm-wiki-2026:§perf] ^[src:karpathy-llm-wiki-2026:§adoption].

## Cross-source citations (when ≥ 2 sources are ingested)

v0 doesn't ingest across sources, but the pages it writes will eventually be amended by later ingests. Keep that future in mind: don't combine facts from multiple imaginary sources into one sentence. One sentence = one provenance.

## Self-check before reporting success

After writing each page, scan it for these failure modes:

1. **Bare numbers/dates without markers.** Regex-friendly: `\b\d{1,4}\b` not followed by `^[src:`.
2. **Marker pointing at a section slug that does not exist in your heading map.** Common cause: typo or stale slug from an earlier source.
3. **Multiple markers for the same fact** — pick one. (Two markers for two facts in one sentence is OK; two markers for the same fact is noise.)

If any of these fire, fix before claiming the ingest complete.
