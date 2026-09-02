# File-back loop

When a query answer is worth saving back into the wiki as a new artifact, vs when it's ephemeral chat output.

The loop is mentioned in the project's `harness/architecture.md` §7 and in Karpathy's original "LLM Wiki" gist (§operations / §query): good answers to good questions can themselves become wiki content. The wiki compounds when answers are filed back; it stays inert when they aren't.

But not every answer is page-worthy. Filing back every one-liner would flood the wiki with restated content the source pages already had.

## When the answer is page-worthy

Heuristic — file-back when **all three** are true:

1. **Synthesis across ≥2 source pages.** A simple lookup ("what does qmd do") that's fully answered by `entities/qmd.md` is not page-worthy as a separate artifact — the user can read `entities/qmd.md` directly. A synthesis that draws on `concepts/llm-wiki-pattern.md` + `entities/qmd.md` + `concepts/three-layer-architecture.md` to explain *why* qmd matters within the pattern — that's page-worthy.

2. **The synthesis introduces a new framing or relationship not stated in any single source page.** "Page X says A; page Y says B; therefore the wiki implies C" — where C wasn't written on either page. If the synthesis is just a faithful concatenation of A and B, it's not page-worthy; it's a query reading the user could do themselves.

3. **The question is likely to recur.** "What's the connection between qmd and the three-layer architecture" is a question someone might ask again next month. "What's in section 3 of the karpathy source" is a one-off — skip file-back.

If only 2 of 3 are true, mention file-back as *optional* in the suggestion field. If only 1 of 3, leave the suggestion blank.

## When the answer is NOT page-worthy

- Coverage is `none` → there's no synthesis to file back; the right action is `wiki-ingest`, not file-back.
- Coverage is `partial` and the question's main thrust isn't covered → filing back a partial answer creates a half-real page.
- The answer is a structured list directly derivable from frontmatter (e.g. "list all entities" → just enumerates `entities/*.md`). That's not knowledge; it's filesystem state.
- The user asked a clarifying question that won't recur: "what does the section §note in karpathy mean" — answer it, don't file it.

## The file-back format (when `--filed-back` is passed)

Write `<target_wiki>/_queries/query-<YYYY-MM-DD>-<slug>.md`:

```yaml
---
type: query-draft
slug: query-<YYYY-MM-DD>-<question-slug>
title: <question, condensed to a noun phrase>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
status: draft
edition: <today, year-month>
sources:
  - src:<source-id-1>
  - src:<source-id-2>
question: <full original question>
---

# <Title from question>

> **Draft.** This page was produced by `wiki-query` on <date> in response to the question above. It synthesizes across <N> wiki pages and may be page-worthy as `concepts/<some-slug>.md` after review. Promote (or discard) via a future `wiki-query-fileback` skill or manually with care.

## Answer

<the full cited answer body, same content as the response message>

## Pages drawn from

- `<path>` — <one-line relevance>
- ...

## Suggested promotion target

`concepts/<slug>.md` (or `entities/<slug>.md`, or `comparisons/<slug>.md` — pick the type that fits)

## Why this might be page-worthy

<one paragraph: the synthesis it introduces, why the question is likely to recur, what the proposed page slug should be>
```

The leading `_queries/` directory means:

- `wiki-lint` (per Step 1 of its SKILL.md) ignores it — drafts don't trigger orphan/unindexed warnings.
- A future fileback skill knows where to find candidates.
- The user can `ls _queries/` to see all pending promotions.

## What file-back does NOT do

- It does NOT promote to a real wiki page. Only a future `wiki-query-fileback` skill (or careful manual hand) does that. The skill's contract is: leave a high-quality draft in `_queries/`; the human (or fileback skill) decides whether to ingest-style integrate it.
- It does NOT update `index.md` or `log.md`. Drafts are off the books until promoted.

## The suggestion field in the answer

Even without `--filed-back` passed, the answer's `## File-back suggestion` field surfaces page-worthiness to the user:

| Condition | Suggestion field |
|---|---|
| Page-worthy (3/3 heuristic met) | "this answer is page-worthy: synthesizes across <N> pages with a new framing. Re-run with `--filed-back` to save a draft." |
| Maybe page-worthy (2/3) | "this answer may be page-worthy if the same question recurs; revisit if so." |
| Not page-worthy (≤1/3) | leave empty |

The skill is gentle on this — file-back is a user-driven curation step, not a default behavior. Volunteering suggestions on every answer would train the user to ignore them.
