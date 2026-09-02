# Answer synthesis

How to turn the top-ranked, fully-read pages into a deterministic, cited answer.

## The core rule

**Every `^[src:...]` marker in the answer is a marker you saw in a page you read.** Citations are reused, not generated. The marker preserves the link between the answer-sentence and the raw file where the fact was originally extracted.

You do not need to use every marker from the source pages. You may use a subset. But you may not write a citation marker that did not appear on a page you read in this run.

## Prose style

- Direct. Cited. No hedging beyond what the wiki itself hedges.
- One sentence ≈ one fact. Long compound sentences make citation placement ambiguous.
- Citation marker goes immediately before sentence-ending punctuation, same convention as `wiki-ingest`'s output:

  > The LLM Wiki Pattern compiles raw sources into a persistent markdown wiki rather than retrieving at query time ^[src:karpathy-llm-wiki-2026:§the-core-idea].

- If a sentence pulls from two sources, two markers, both before the punctuation:

  > Editions on dependent pages should mirror source-edition, not ingest-date ^[src:karpathy-llm-wiki-2026:§architecture] ^[src:project-architecture-doc:§3-contracts].

## Length

Match the question. Definitional ("what is X") = 1–3 sentences. Procedural ("how does X work") = 1–2 paragraphs. List ("enumerate") = a table or bullets, no prose padding.

Never pad the answer to look "complete". A wiki-grounded answer is allowed to be short. A short answer with one good citation is more useful than a long answer with five hedges.

## Structured-list answers

When the question is "list / enumerate / show all", emit a table or bullets directly under `## Answer`, no leading prose. Columns/columns-per-bullet depend on the question:

- "List entities in this wiki" → `| slug | title | sources |` table, one row per entity page.
- "Show all concepts mentioning X" → bullets `- [[slug]] — <one-line relevance>`.
- "Enumerate the four laws of this project" → bullets, one per law.

Cite per row only when the row contains a factual claim. Pure structural rows (slugs, paths) do not need citations.

## Multi-source synthesis

When ≥2 pages cite the same fact with **the same marker**, the fact is corroborated. Cite the marker once.

When ≥2 pages cite a related fact with **different markers** (e.g. two sources both discuss qmd):

- If the facts agree: cite both markers in the same sentence.
- If the facts disagree: this is a `contradiction`. The answer reflects both positions, cites both, and mentions the disagreement. If a `contradictions/` page exists for this topic, prefer its `resolution:` framing. If no `contradictions/` page exists, flag this in the file-back suggestion: "this answer surfaces a multi-source disagreement; a `contradictions/<topic>.md` page would be the proper place to record the resolution".

## Confidence calibration

`Confidence` reports how strongly the read pages support the specific answer.

- **high**: one canonical page on the topic, exact match to the question, no internal contradictions.
- **medium**: answer required combining ≥2 pages OR the canonical page is `status: draft` (not yet blessed) OR the page has open questions that touch the asked thing.
- **low**: answer required interpretation across pages whose framing isn't perfectly aligned, or `Coverage: partial`, or the source page edition mismatches the dependents.

When low, the one-line explanation under Confidence should name the specific weakness: "answer requires bridging concept page and source-page Summary; no canonical match".

## When the wiki cites itself

Source pages cite the source they summarize: `sources/karpathy-llm-wiki-2026.md` cites `^[src:karpathy-llm-wiki-2026:§the-core-idea]`. That's normal. When your answer leans on the source page's Summary, the marker is valid; reuse it.

Avoid citing the *source page path* as if it were a marker. The marker is `^[src:karpathy-llm-wiki-2026:§...]`, not `^[sources/karpathy-llm-wiki-2026.md]`. The wiki page is in `Sources used`; the marker resolves to the underlying raw file.

## What if I'd answer better off-wiki

You will sometimes know more than the wiki carries. The temptation is to add a paragraph "from memory" to round out the answer. Don't.

Two reasons:
1. The user might be checking the wiki's reach, not asking for the best possible answer. Inflating the answer with off-wiki content hides the wiki's true coverage.
2. The four laws of the project define the wiki as the authoritative answer surface. Mixing off-wiki content into the wiki-cited answer dilutes that.

If you want to add an off-wiki note, put it in a clearly-marked section *below* the cited answer:

```
## (Off-wiki note)

The above is everything the wiki has on this. From general knowledge (not cited): <one paragraph, marked as off-wiki>.
```

That keeps the contract intact and gives the user the extra context if they want it. The `(Off-wiki note)` section is optional and should be brief.

## Anti-pattern checklist

Before you finalize the answer, scan for these:

- ❌ A factual sentence in the answer with no marker.
- ❌ A marker in the answer that did not appear on any page read in this run.
- ❌ The same fact cited twice with different markers in the same sentence without justification.
- ❌ A `Confidence: high` claim on partial coverage.
- ❌ An off-wiki paragraph mixed into the cited answer body (move it to a clearly-marked `(Off-wiki note)`).

If any fire, rewrite the answer before delivering.
