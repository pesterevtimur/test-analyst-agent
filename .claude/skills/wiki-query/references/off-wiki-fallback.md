# Off-wiki fallback

What to do when the wiki has no coverage for the question. Spoiler: not "silently answer from memory".

The project's law #2 says: when a wiki exists for a topic, don't answer from memory; use the wiki. The corollary — and the harder rule — is: when the wiki exists but doesn't yet have what the user asked, **say so explicitly**, then either decline or answer with a tag that flags the answer as off-wiki.

This file defines that explicit-tag fallback.

## When this applies

Two cases:

1. **Coverage: none.** Step 2 of the procedure returned zero useful matches (after loosening, per `search-strategy.md`).
2. **Coverage: partial AND the missing part is the main thrust of the question.** The wiki has tangential pages but not the actual answer.

In both cases the fallback procedure below applies. The `Coverage` field in the answer template is set to `none` or `partial` accordingly.

## What the fallback looks like

The answer is structured like a normal answer but with three differences:

### 1. The `## Answer` section opens with an explicit gap notice.

```
## Answer

**The wiki at `<target_wiki>` does not currently cover this question.** No page in `entities/`, `concepts/`, `sources/`, or `contradictions/` discusses <topic-as-the-skill-understood-it>. The closest match was `<closest-page>` which touches <adjacent topic>, not the asked question.
```

### 2. After the gap notice, either decline or off-wiki-answer.

**If the topic is in-scope for the wiki and a future `wiki-ingest` would naturally fill the gap** — recommend `wiki-ingest`:

```
### Recommendation

This topic fits this wiki's scope (per its `CLAUDE.md`: <restate the wiki's domain in one line>). The right action is to find a source on <topic>, place it in `<target_wiki>/raw/`, and run `wiki-ingest`. Then re-run the query.
```

Do not give an off-wiki answer in this case. The user is better served by the right next action than by a temporary off-wiki paragraph.

**If the topic is out-of-scope for the wiki** (e.g. user asks the `context-engineering` wiki about Kafka tuning) — say so and give a one-paragraph off-wiki answer with the off-wiki tag:

```
### Off-wiki answer

This question is out of scope for `<target_wiki>` (which covers <wiki domain>). Answering from general knowledge, not cited:

> <one-paragraph off-wiki answer>

If this becomes a recurring topic, consider a separate wiki via `wiki-llm-builder` (suggested name: `wikis/<slug>/`).
```

The `Off-wiki answer` content has **no citations** — it can't, by definition. That absence is the signal.

### 3. Confidence is at most `medium`.

`Coverage: none` with `Confidence: high` is a contradiction in terms. The most you can claim is `medium`, and only when the off-wiki answer is squarely in the LLM's strong-knowledge domain. Default to `low`.

## Why not just answer from memory and call it done

Three reasons, in order of importance:

1. **The user is implicitly auditing the wiki when they ask.** Hiding a gap by smoothing it over with an LLM answer prevents the user from noticing what to ingest next. The wiki gets worse over time, not better.

2. **Off-wiki content has no provenance.** The four laws of the project hinge on every fact tracing to a source. Mixing in an uncited answer breaks that contract retroactively if the user starts citing the answer back into wiki content. The explicit tag prevents this — the user knows what they got.

3. **Skill triggering depends on legibility.** If `wiki-query` quietly handles "wiki has nothing on this" by going off-wiki, then future invocations look like they used the wiki even when they didn't. Coverage stats lie. Lint stats lie. The whole audit chain weakens.

## Soft case: the user asked for memory

If the user explicitly asked for an off-wiki answer ("just from memory, what's X?" / "ignore the wiki for this one"), then the skill probably shouldn't have triggered at all — but if it did, follow the user's intent. The output template still applies but:

- `Coverage: <still report what it would have been>` so the user can see the gap exists.
- `## Answer` is the off-wiki content with the tag.
- `Confidence` reflects the off-wiki answer's strength.

Always honor a user's explicit request for memory-based answers. Just keep the framing visible.

## What this fallback is NOT

- It is **not** a license to write an LLM-answer paragraph and tack a "wiki doesn't cover this" line on top. The structure above puts the gap notice first and the off-wiki answer in its own framed subsection precisely so the user can't miss the boundary.
- It is **not** a way to skip `wiki-ingest` work. Recommendations to ingest are not optional politeness; they're the right next action when the topic is in-scope.
- It is **not** a way to ingest content yourself. Don't go fetch a paper because the wiki doesn't have one. That's `wiki-ingest`'s job; this skill stays read-only.
