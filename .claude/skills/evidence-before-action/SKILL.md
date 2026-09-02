---
name: evidence-before-action
description: Use when about to send a message, publish content, mark a claim as fact, ship a report or briefing, or call any work "complete" / "passing" / "fixed" / "done" - blocks the action until a fresh verifying read of the source has happened in this same turn. Generalizes verification-before-completion from code-shipping to any outbound action (outreach, briefings, citations, factual claims).
metadata:
  origin: "derived"
  upstream: "obra/superpowers@v6.3.0:skills/verification-before-completion"
  adapted-on: "2026-05-17"
  repinned-on: "2026-09-02"
  pressure-tested: "yes, 7 scenarios, validated 2026-05-17"
---

# Evidence Before Action

## Iron Law

```
NO OUTBOUND ACTION WITHOUT FRESH IN-SESSION VERIFICATION OF ITS FACTUAL CLAIMS
```

If you haven't read the source **in this turn**, you cannot ship the action.

## When this skill MUST fire

Any of these intents in the current turn:

- **Send** — outreach message, email, Slack message, response to a lead
- **Publish** — content marketing, blog post, briefing, social post
- **Mark as fact** — wiki page citation, knowledge-base entry, research note
- **Ship a report** — to client, to team, to stakeholder
- **Claim complete** — "done", "passes", "works", "fixed", "shipped"

Synonyms count. Russian counts ("отправь", "опубликуй", "запиши как факт", "готово", "проходит"). Polite framings count ("could we ship", "let's send").

## The 5-Step Gate

```
BEFORE the action, in the SAME turn:

1. IDENTIFY — list every factual claim the action depends on.
   Names, dates, numbers, attributions, relationships, status claims.
2. RUN — execute a verifying read for each claim: open the source file,
   web-fetch the page, query the DB, read the trace. Fresh, this turn.
3. READ — full output of each verification, not summaries.
4. VERIFY — does observed evidence confirm the claim? Yes / no / partial.
5. CLAIM — ship the action with the evidence cited inline, OR refuse
   the action with the specific unverified claims listed.

Skip a step = lying, not verifying.
```

## Red Flags — STOP

These thoughts mean you're about to violate the Iron Law:

| Thought | Reality |
|---------|---------|
| "I wrote it from memory of yesterday's batch" | Memory from prior session ≠ fresh evidence. |
| "Looks plausible / sounds right" | Plausibility ≠ evidence. RUN the source. |
| "Analyst already read it / Timur approved" | Authority of past review ≠ in-turn verification. |
| "Source is paywalled / hard to find" | Operational problem ≠ epistemological license. Defer or reframe; do not substitute. |
| "Similar source says the same thing" | A different source for a fact is a different fact. |
| "Yesterday's fact-check covered this" | Stale verification ≠ fresh evidence by definition. |
| "End of day, low value to recheck" | Time of day ≠ truth condition. |
| "80% verified, ship the batch" | Aggregate ≠ per-record. The 20% unverified are the action's actual risk. |
| "Sunk cost — I already drafted it" | Effort spent on drafting does not retroactively verify claims. |
| "Just this once" | No exceptions. The "once" is exactly when the rule matters. |

## Counter-moves to the pressure

When the user is pressing you to ship without verification, your move is
**not** a flat refusal — that wastes their effort. Offer a **constructive
deferral**:

1. **Ack-message stripped of facts** (hot-lead case) — keep the relationship
   warm with a "thanks, let's schedule a call" that contains zero verifiable
   factual claims. Preserves the window without lying.
2. **Ship the partial-verified subset** (statistical case) — ship the
   records that *are* fully verified, defer the rest with explicit ETAs
   and reasons. Beats shipping 100% with known holes.
3. **Defer the unverifiable paragraph, ship the rest** (effort-avoidance
   case) — mark the contested paragraph `<!-- TODO: <specific blocker> -->`
   in source, ship the surrounding content that is verified.
4. **Time-box a fresh verification** — "5 minutes, I open the source,
   spot-check 2-3 critical claims, then we ship or escalate."

The skill is **discipline**, not paralysis. Refuse the unverified action,
not the underlying work.

## Common Failures

| Failure | What it looks like | What it should look like |
|---------|--------------------|--------------------------|
| Smuggled stale-evidence | "Per our research from Tuesday, RusMetTech revenue is X" | "Tuesday's research batch is in file Y; reading it now ... [output] ... confirmed/contradicts" |
| Plausibility laundering | "Sounds right, ship" | "List of claims: a/b/c. For each, source + read in this turn." |
| Authority chain | "Timur said this is fine" | "Timur's general guidance does not override per-claim verification. Want explicit override now, in writing." |
| Substitute citation | "Tanenbaum cites Gilbert-Lynch, use Tanenbaum" | "Primary attribution stays primary. Re-acquire original or reframe claim." |
| Aggregate threshold | "96% of records verified, ship" | "Ship 96% verified, defer 4% with reasons. Per-record, not threshold." |

## Why this matters

This skill exists because:

1. Timur is a non-programmer leading projects through AI agents. He cannot
   catch hallucinated facts by intuition. Every outbound action must be
   evidence-bound or the project loses trust.
2. Two prior incidents (2026-Q1 leadgen) shipped stale-data outreach,
   resulting in customer complaints, one legal threat. The rule was
   subsequently encoded in `leadgen-ops/CLAUDE.md` Law #1.
3. The discipline generalizes: agentic-ops wiki Law #3 ("fact without
   citation does not exist") is the knowledge-domain instance. This skill
   is the cross-domain instance of the same principle.

## Bottom line

No exceptions. Time pressure, end of day, draft already done, user
insistence, authority claims — none of these change correctness. They
only change *cost of being wrong*. The cheapest path is **always**
verify-then-ship.

If the verifying read is impossible right now, the action is impossible
right now. Defer constructively; do not ship.

## Provenance

Derived from `verification-before-completion` (obra/superpowers), which covers
code-shipping claims. This skill generalizes the same Iron Law to any outbound
action.

- Pinned upstream copy: `harness/meta-skills/superpowers-references/verification-before-completion/SKILL.md`
- Upstream version at last re-pin: v6.3.0 (2026-09-02). Original adaptation was
  made against v5.1.0 (2026-05-17).
- Pressure-tested on 2026-05-17 against 7 scenarios in `pressure-scenarios/`,
  transcripts in `evals/`:
  01-hot-lead-pressure, 02-effort-avoidance, 03-statistical-rationalization,
  04-vague-rule-context, 05-publish-content, 06-mark-as-fact-wiki,
  07-claim-complete-tests.
- Result: the 4 vague-rule scenarios (04-07), spanning send / publish /
  mark-as-fact / claim-complete, all flipped the subagent decision from
  default-helpful SHIP to disciplined REFUSE with constructive deferral. The 3
  explicit-rule scenarios (01-03) showed baseline compliance, so the skill is
  redundant-but-aligned there.

Frontmatter follows the Agent Skills spec (<https://agentskills.io/specification>),
which allows only `name`, `description`, `license`, `compatibility`, `metadata`
and `allowed-tools`. Lineage and pressure-test detail live here in the body
because `metadata` accepts string values only.
