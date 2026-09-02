# Check 1 — missing-citation

A factual sentence on a wiki page must end with at least one citation marker `^[src:<source-id>:<locator>]` before its closing punctuation. A sentence with a factual signal but no marker is a `missing-citation` finding.

## What counts as a "factual signal"

Match any of these in the sentence; the first match is enough to call the sentence factual.

1. **Number** — any standalone digit sequence, optionally with units or decimals.
   - Triggers: `10`, `42 papers`, `v4.2`, `2024`, `3 hours`, `1.5 ms`, `1,000,000`.
   - Does NOT trigger: enumerations of structural lists (`step 1`, `step 2`) when those numbers are followed by a colon and a list of named items (these are typographic, not facts). Use the colon-and-list heuristic to exclude.
2. **Date** — explicit dates or relative-date phrases.
   - Triggers: `2024`, `March 2024`, `2024-03-15`, `Q4 2025`, `since the GPT-3 paper`, `с октября 2025`.
3. **Named entity** — a capitalized multi-letter token (not at sentence start) that is *the subject of a claim*, not a generic reference.
   - Triggers: `Anthropic released X`, `Karpathy wrote that ...`, `Apache Kafka is ...`.
   - Does NOT trigger: `the company released X` (anonymized), `someone said` (no entity).
4. **Direct quote** — text wrapped in `"..."` or `«...»`, length ≥ 3 words.
5. **Causal / comparative claim** — `X causes Y`, `X is faster than Y`, `because of Z`, `X enables Y`.
   - Match on keywords: `causes`, `enables`, `because`, `due to`, `faster than`, `slower than`, `more than`, `less than`, `превосходит`, `быстрее чем`, `из-за`.
6. **Specific procedural detail** — a fact that would be wrong if misremembered.
   - Triggers: `the algorithm runs in 3 passes`, `the config file lives at /etc/foo`, `the default port is 8443`.

## How to scan

Two-pass strategy per file:

1. **Sentence-split.** Split the body (everything below the first `## ` heading, ignoring YAML frontmatter) on `[.!?]` followed by whitespace or end-of-line. Keep markdown formatting tokens with their sentence. Track each sentence's starting line for the report.
2. **Per-sentence classify.** Match each sentence against the six signals above. If any matches AND the sentence does not already end with `^[src:...]` before its closing punctuation, emit a finding.

Marker match regex (Python-ish):

```
^\[src:[a-z0-9-]+:[^\]]+\]\s*[.!?]\s*$
```

(The marker is before the closing punctuation, the closing punctuation may be followed by whitespace or EOL.)

Multiple markers per sentence count as present (one marker before closing punctuation is enough). Markers attached mid-sentence to specific facts are also fine — see citation-extraction in `wiki-ingest` for the format.

## False-positive patterns (do NOT flag these)

- **Template/example pages.** Skip if `status: template` in frontmatter or path matches `_templates/**`.
- **YAML frontmatter values.** Do not parse `created: 2024-05-12` as a factual sentence; this is metadata.
- **Code blocks.** Skip everything between `` ``` `` fences. Numbers/quotes inside code are not facts.
- **Quoted source text in a `## Citation format` block.** Common on source pages. Skip a block titled `## Citation format` entirely.
- **`Open questions` sections.** Questions are speculative by definition; flag only if the question contains a *claim*, not just an interrogative ("What is the throughput limit?" — not factual; "Throughput limits at 1000 req/s — verify" — factual).
- **Internal-link descriptions.** A `[label](path)` whose `label` happens to contain a number ("Section 4.2") is not by itself factual unless the sentence containing it is.

## Multilingual handling

Russian, English, mixed are the cases this project actually sees. Detection rules:

- Numbers and dates: language-agnostic.
- Named entities: same regex (Latin or Cyrillic capitals).
- Causal/comparative keywords: include both English and Russian lists above.
- Sentence splitting: `[.!?]` works for both; also include `…` (`U+2026`).

If a sentence is a single full-line direct quote (`> «...»`), treat the whole quote as one sentence — markers go after the closing punctuation of the quote, before any trailing attribution.

## Finding emission

For each violating sentence:

```
- `<relative-path>:<line>` — <first 80 chars of sentence>
  evidence: matched <signal-type> — "<the matched piece>"
```

Order findings within the category by path then line.

## What counts toward "citation coverage"

The skill emits `citation coverage: <N>/<total> = <pct>%` where:

- **total** = number of factual sentences detected across all non-template, non-source-self-citing pages.
- **N** = total minus the number of `missing-citation` findings.

Source pages citing themselves count toward both (one factual sentence, one marker pointing at the source itself).

A wiki with zero factual sentences (e.g. fresh bootstrap) reports `0/0 = N/A` rather than `0/0 = 100%`. Pretty 100% on a void is misleading.
