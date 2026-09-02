---
name: wiki-query
description: Answer a question against a bootstrapped LLM Wiki — search the wiki first, synthesize an answer from the matched pages, and carry citation markers from the wiki into the answer verbatim. Use whenever the user asks a substantive question on a topic the project has a wiki for — e.g. "what does the wiki say about three-layer-architecture", "найди в context-engineering вики что-нибудь про qmd", "ask the wiki about prompt injection", "what's in the wiki on Kafka". This is also the right skill when the user asks a general-sounding question (no "wiki" in the prompt) on a topic that has a wiki — project law #2 says "if a wiki exists for the topic, don't answer from memory; go to the wiki". Trigger preemptively. Returns a deterministic, cited answer with explicit `covered | partial | none` coverage. When the wiki has no coverage, says so plainly and points the user at `wiki-ingest` instead of fabricating. Accepts an explicit `target_wiki` absolute path (same signature as `wiki-ingest` v0.1 and `wiki-lint` v0).
---

# Wiki Query (v0)

Answer one question against one bootstrapped LLM Wiki. Search first, read second, synthesize third — carrying the wiki's own citations into the answer.

## What this skill is for and not for

**For:** taking a question and a wiki, finding the pages that bear on the question, reading them, and producing a cited answer that **re-uses the citation markers already in those pages**. The answer is grounded *by construction* because every factual sentence in the answer carries the same marker that already supported the same fact on a wiki page.

**Not for (v0):**
- **Ingesting new sources.** If the wiki lacks coverage on the question, say so and point at `wiki-ingest`. Do not fetch web content to fill the gap.
- **Editing the wiki.** Read-only, like `wiki-lint`. The optional file-back step *suggests* a new page; it does not write one.
- **Cross-wiki queries.** One wiki per invocation.
- **Free-form chat.** If the question is small-talk or off-domain, hand it back to ordinary chat without firing the procedure.

The point of read-only is the same as in `wiki-lint`: the human (or a future `wiki-query-fileback` skill) decides what enters the wiki. The query skill stays cheap to invoke.

## When you should trigger

The description is the trigger; this section is for edge calls.

- Direct asks: "ask the wiki about X", "what does the wiki say about Y", "найди в вики Z". **Always trigger.**
- Topic-matched general questions: "what is three-layer-architecture?" when the project has a `context-engineering` wiki with a `three-layer-architecture.md` concept. **Trigger** — project law #2 says go to the wiki, not memory.
- Questions about a wiki's *own structure*: "how many entities are in the context-engineering wiki?", "what does index.md cover?". **Trigger** — these are answerable from the wiki's metadata pages.
- Questions about wikis the project does NOT have yet: "what does our microservices wiki say about Kafka?" when no `wikis/microservices/` exists. **Trigger anyway** — let the skill stop on Step 1 and report "no such wiki" cleanly.

If the user explicitly asks for an off-wiki answer ("from memory, what's X?"), do **not** trigger. The trigger respects user intent.

## Inputs

- **`<target_wiki>`** — absolute path to the wiki root.
- **`<question>`** — the user's question, as written.
- (Optional) **`--filed-back`** — if present, after answering also generate a draft `<target_wiki>/_queries/query-<date>-<slug>.md` page with the answer, marked `status: draft`. The user can then invoke a future fileback flow to promote it to a real wiki page. Not enabled by default — file-back is a separate step the user opts into.

Refuse if `<target_wiki>/CLAUDE.md` does not exist.

## Procedure

Three logical steps, each with a *why* and a *how*. Reference files give the details when you need them.

### Step 1 — Validate target_wiki and parse the question

- `<target_wiki>` must be an absolute path to a bootstrapped wiki (contains `CLAUDE.md`, `index.md`, `log.md`). If it isn't, **stop and report**: "no wiki at <path>; bootstrap with `wiki-llm-builder` first".
- Parse the question into 3–7 **query-tokens** — the substantive nouns, named entities, and domain-specific phrases that distinguish this question from other questions. Drop function words, generic verbs ("what", "is", "tell"), and pleasantries. Multilingual: keep both Russian and English tokens if the question is mixed. See `references/search-strategy.md` for the tokenization heuristics.
- Note any question type signal: "what is X" → definitional; "how does X work" → procedural; "list / show / enumerate" → structured-list answer; "compare X and Y" → comparison; "where is X discussed" → location/coverage.

Question parsing matters because Step 2's ranking weights tokens — too few tokens loses recall; too many dilutes precision.

### Step 2 — Search and rank candidate pages

Use `Glob` to list every `*.md` file under `<target_wiki>` excluding `raw/` and `_*` subdirectories. Then `Grep` each query-token across that inventory (parallel grep is fine — once per token, all-files).

For each file, count: (a) number of distinct query-tokens that matched, (b) the type of the page (concept / entity / source / contradiction / comparison), (c) whether the matches landed near the top of the page (frontmatter `title`, top-level heading, `## Summary`) vs deeper.

Rank candidates roughly:

1. **Token coverage first.** A page hit by 5 of 5 tokens beats a page hit by 2.
2. **Tie-break by page-type relevance to question type.**
   - Definitional question → `concept` > `entity` > `source`.
   - "Compare X and Y" → `comparison` pages first if they exist, otherwise the two entity/concept pages.
   - "Enumerate" → the `index.md` of the wiki first, then all matching pages in the relevant directory.
   - Otherwise weight equally.
3. **Tie-break by match position.** Matches in `title` / first heading / Summary beat matches in `Open questions` or `Related`.

Read the **top 3–5** ranked pages in full. Stop earlier if you have already found a definitive answer; keep reading if pages are partial or disagree. See `references/search-strategy.md` for ranking edge cases (no matches at all, all matches in `_templates/`, etc.).

### Step 3 — Synthesize the answer with reused citations

This is the step that makes the skill more than a glorified grep.

For each factual claim in your answer, you must **already have seen** that claim on a wiki page in Step 2, with a citation marker on it. Carry that marker into your answer **byte-for-byte**. If two pages cite the same fact with the same marker, use the marker once; if two pages cite the same fact with different markers (different sources), the answer can keep one of them and mention the multi-source nature, but it must not invent a new marker.

**Rule of thumb:** every `^[src:...]` in your final answer comes from a page you read in Step 2. Zero exceptions.

When the matched pages **partially** cover the question — they touch the topic but don't fully answer — mark `Coverage: partial` and explicitly list which sub-questions remain unanswered. Do not fill the gap with memory. The user is better served by knowing what the wiki doesn't know.

When the matched pages have **no** coverage — pages were found by grep but on reading they were tangential, or no pages matched at all — mark `Coverage: none` and follow `references/off-wiki-fallback.md`. The fallback is **not** "answer from memory silently"; it is "explicitly tag the answer as off-wiki, give the memory-based answer with that tag, and recommend the user run `wiki-ingest` to fill the gap properly".

See `references/answer-synthesis.md` for output prose style, structured-list answers, and how to handle multi-source synthesis.

### Step 4 — (Optional) File-back

If `--filed-back` was passed AND the answer is substantive (more than a one-liner, covers material spread across ≥2 pages, introduces a synthesis), write a draft page at `<target_wiki>/_queries/query-<YYYY-MM-DD>-<question-slug>.md` with the full answer, `status: draft`, and a note: "produced by wiki-query on <date>; if this synthesis is page-worthy, promote it to `concepts/<slug>.md` via wiki-ingest-fileback flow (future skill)".

Why `_queries/` and not `concepts/`: leading `_` excludes the directory from `wiki-lint`'s inventory, so file-back drafts don't immediately trigger orphan/unindexed warnings. They are scratch until the user promotes them.

See `references/file-back-loop.md` for when answers are page-worthy.

### Step 5 — Write the answer

Use this template, **verbatim**:

```
# wiki-query answer — <target_wiki>
Question: <question, as the user asked>
Coverage: covered | partial | none

## Answer

<the answer prose, with inline ^[src:<id>:<locator>] markers reused from wiki pages>

(If structured-list answer was requested, use a markdown table or bullet list here.)

## Sources used

- `<relative-path-to-page-1>` — <one-line relevance>
- `<relative-path-to-page-2>` — <one-line relevance>
- ...

## Confidence

high | medium | low — <one-line explanation tied to coverage, agreement across sources, and recency of source editions>

## File-back suggestion

(empty if the answer is small/single-source; otherwise a one-line recommendation)
```

`Coverage` and `Confidence` are not the same:
- `Coverage` is whether the wiki had the material at all.
- `Confidence` is how strongly the material supports the specific answer given.

A wiki can have full `Coverage` but you can still be `medium` confidence if the answer requires interpretation. Inversely, you can have `partial` coverage but `high` confidence on the part that *is* covered.

## How to deliver the answer

Save the templated answer to **two** places when invoked from a subagent context, **one** place when invoked from a parent session:

1. **Always:** return the full answer text in the response message, so the orchestrator can forward it to the user verbatim.
2. **When invoked from a parent session (no subagent harness):** also save to `<target_wiki>/_queries/query-<YYYY-MM-DD>-<question-slug>.md` for retention.

Why two paths: subagent harnesses on this project block `Write` to `report-*.md` and may block `_queries/` writes too; we discovered this on day 3 with `wiki-lint`. Returning the answer as response text always works; persisting to a file is best-effort. The skill's contract is the response content, not the file. (Iteration-2 may revisit this if file persistence becomes contractual.)

## When this skill is the wrong tool

- "Add Kafka to the microservices wiki" → `wiki-ingest`.
- "Audit the wiki" → `wiki-lint`.
- "Start a new wiki on X" → `wiki-llm-builder`.
- "Help me write code" → ordinary chat, possibly with reference to a wiki via this skill, but not framed as a query.

If the user asks something this skill could answer but also wants you to *do* something on the result (fix the wiki, write code, draft a doc), do the query first, then hand off to whichever skill or chat does the doing. Keep the query layer thin.

## Edge cases worth knowing

- **The wiki is empty.** Page-inventory has only `index.md` / `CLAUDE.md` / `log.md`. Return `Coverage: none`, recommend `wiki-ingest`, do not invent an answer.
- **One page has a contradiction inside itself** (two markers disagreeing on the same fact). Reflect the contradiction in the answer prose, cite both markers, and lower confidence to `medium` at most.
- **Citation marker the wiki uses cannot be re-emitted without context loss** (e.g. the marker covers a multi-sentence quote and the answer uses only one sentence). Cite anyway; the marker still locates the fact in `raw/`.
- **The user's question is unanswerable in principle from the wiki** (e.g. "what is the secret to happiness"). Coverage `none`, off-wiki framing, short answer.
- **Multiple wikis would help** (e.g. "compare the answer in the context-engineering wiki and the microservices wiki"). v0 takes one `target_wiki`. Stop and ask the user which wiki to query first; recommend running this skill twice rather than building cross-wiki support into v0.

## References

Load on demand:

- `references/search-strategy.md` — tokenization, multilingual handling, ranking edge cases.
- `references/answer-synthesis.md` — prose style, structured-list answers, multi-source synthesis, citation reuse rules in detail.
- `references/file-back-loop.md` — when an answer is page-worthy, the draft format.
- `references/off-wiki-fallback.md` — explicit off-wiki framing when the wiki doesn't cover the question.

For project context: root `CLAUDE.md` (law #2 is the reason this skill exists) and `harness/architecture.md` section 7 (the end-to-end "query inside the chain" example).
