# Search strategy

How to turn a question into 3–7 search tokens and rank the matched pages. The skill's quality is bounded by how well this step picks the right pages to read.

## Tokenization

Goal: distinguish this question from other questions in this wiki. Drop generic English/Russian function words; keep substantive nouns, named entities, and domain-specific phrases.

### Drop list (function/filler)

English: `what`, `is`, `are`, `the`, `a`, `an`, `tell`, `me`, `about`, `wiki`, `does`, `say`, `please`, `can`, `you`, `briefly`, `quickly`, `from`, `of`, `for`, `to`, `in`, `on`, `at`, `by`.

Russian: `что`, `такое`, `какие`, `какой`, `как`, `у`, `в`, `на`, `с`, `по`, `про`, `мне`, `нам`, `скажи`, `пожалуйста`, `быстро`, `коротко`, `из`, `этой`, `этого`, `этом`, `вики`.

These are not exhaustive — keep judgment, not a rigid drop-list.

### Keep list (signal types)

- **Named entities** (capitalized in English, multi-letter Cyrillic words that aren't sentence-start): `Kafka`, `Karpathy`, `qmd`, `Anthropic`, `Obsidian`.
- **Domain-specific compounds**: `three-layer-architecture`, `prompt-injection`, `context-engineering`, `LLM Wiki`.
- **Verbs that carry meaning in this domain**: `ingest`, `lint`, `extract`, `cite`, `rank`.
- **Numbers / versions** when they look like facts: `v4.2`, `2024`, `1000`.

### Multilingual

If the question mixes Russian and English, keep tokens in both languages. Wiki search hits will reflect whichever the wiki uses. Russian-only questions on English-content wikis: try transliterations or English equivalents as additional tokens (e.g. user asks "что такое Карпати говорит про qmd" → also search for `Karpathy`).

### Cap at ~7

More than 7 tokens almost always means: (a) you didn't drop function words, or (b) the question is actually two questions stitched together. In case (b) consider answering the questions separately; if the user clearly wants one answer, weight the most specific tokens.

## Searching

Use `Glob` for the file inventory (per the SKILL.md exclusions) and `Grep` per token, case-insensitive (`-i`).

For each token, the Grep result gives you `(file:line-number, matched-text)`. Build a per-file count of distinct tokens hit, plus a list of line numbers per token per file.

## Ranking

Score each candidate file with three signals; sort descending:

1. **Token coverage** — number of distinct query-tokens that matched. Coverage 5/5 beats 2/5. Weight: dominant.
2. **Page-type relevance to question type:**
   | Question type | Preferred page type |
   |---|---|
   | "what is X" definitional | `concept` > `entity` > `source` |
   | "list / enumerate" | `index.md` > directory listings |
   | "compare X and Y" | `comparison` > both `entity`/`concept` pages |
   | "how does X work" | `concept` (procedural framing) > `source` (long-form) |
   | "where in the wiki is X discussed" | the actual page where X is the main subject — usually `entities/X.md` or `concepts/X.md` |
   Weight: tie-break.
3. **Match position** — does the token appear in:
   - YAML `title:` field or `slug:` field — strongest (this page is *about* the token)
   - top-level `# heading` — strong
   - `## Summary` section — strong
   - `## Key facts` — medium
   - `## Related` or `## Open questions` — weak (page knows of the token, isn't about it)
   Weight: secondary tie-break.

## Read budget

Top 3–5 pages, full read. Stop earlier if a `concept` page with full token coverage hits — that's almost always the canonical page for the question. Read all 5 only if pages partially cover or disagree.

Do NOT read all matching pages. Long-tail matches dilute the synthesis budget and rarely add anything beyond the top-ranked.

## Edge: zero matches

If Grep across all tokens returns zero hits in any wiki page (excluding `_*` and `raw/`):

1. Try **looser tokens** — drop the most specific token and re-grep. Repeat until at least one match or until you've reduced to one token.
2. If still zero: declare `Coverage: none` and follow `off-wiki-fallback.md`.

Do NOT read `raw/` files for query coverage. Raw is the substrate; the wiki is the interface. If the wiki doesn't surface a fact, the answer's wiki coverage is none — even if the fact is in raw.

## Edge: all matches in `_templates/`

The `_*` exclusion in the inventory rule already prevents this in practice (`_templates/` is skipped). If a Grep run somehow surfaces `_templates/` results because of a non-standard wiki layout, ignore them. Templates are illustrative.

## Edge: matches in wiki-meta files only

If the only matches are in `CLAUDE.md`, `log.md`, `index.md` — the wiki has *mentioned* the topic in its bookkeeping but has no content page on it. This is `Coverage: partial` at best. The answer says "the wiki references this topic in its index/log, but has no dedicated page on it yet — consider `wiki-ingest`".
