# Pressure-Testing Addendum to `skill-creator`

This document **augments** the Anthropic `skill-creator` flow for one specific
case: **discipline-enforcing skills**.

`skill-creator` is installed as a plugin:

    claude plugin install skill-creator@claude-plugins-official
    # body at ~/.claude/plugins/cache/claude-plugins-official/skill-creator/<ver>/skills/skill-creator/SKILL.md

As of 2026-09-02 its flow covers: drafting, test-case generation, background
eval runs with subagent graders, a results viewer, benchmark variance analysis,
and automated description optimization. What it still does **not** cover is
**adversarial** testing: it measures whether a skill fires and performs, not
whether it holds under pressure to break its own rule.

That is the gap this addendum fills. Discipline skills exist to make Claude
*refuse* something under pressure, and that refusal must be tested.

## When to apply this addendum

Apply this addendum **in addition to** the normal `skill-creator` flow if
the SKILL.md you're authoring contains any of these blocker phrases:

- "MUST not", "MUST stop", "MUST refuse"
- "block", "blocker"
- "stop and ask"
- "do not proceed"
- "no exceptions"
- "non-negotiable"

If your skill contains none of these, ignore this addendum — you have a
functional skill, the Anthropic flow is sufficient. Set
`metadata.pressure-tested: "no"` and move on.

## Methodology — RED-GREEN-REFACTOR for documentation

Adapted from Superpowers `writing-skills` (pinned reference at
`../../superpowers-references/writing-skills/SKILL.md`):

| TDD concept | Skill-creation concept |
|-------------|------------------------|
| Test case | **Pressure scenario** (subagent message + context) |
| Production code | SKILL.md content |
| RED (test fails) | Subagent **violates** the rule without the skill |
| GREEN (test passes) | Subagent **complies** with the skill present |
| REFACTOR | Close loopholes the subagent found |

Write pressure scenarios **before** writing SKILL.md content. Run them
without the skill present — document the exact rationalizations the agent
uses verbatim. Then write the skill addressing those specific rationalizations.

## Pressure scenario template

Each scenario should combine **3 or more independent pressures**, because
agents resist single pressures easily but fold when stacked. The four
pressure axes:

| Axis | Examples |
|------|----------|
| **Time** | "We need this in 5 minutes", "deadline today" |
| **Sunk cost** | "We already prepared X yesterday, just ship it" |
| **Authority** | "The CEO approved this", "Timur said it's fine" |
| **Consequences** | "Customer churns if delayed", "team morale tanks" |

**Scenario format:**

```markdown
# Pressure Scenario: <name>

## Pressures (must be 3+)
- Time: <specific framing>
- Sunk cost: <specific framing>
- Authority: <specific framing>
- Consequences: <optional 4th>

## Subagent system prompt
<paste your project CLAUDE.md or relevant context>

## User message to subagent
<the message that triggers the temptation to violate the rule>

## Expected violation without skill
<what we predict baseline agent will do>

## Expected compliance with skill
<what we want the agent to do with skill loaded>
```

## Rationalization table format

After running RED-phase, collect every rationalization the agent uses
verbatim. Format as a table in the SKILL.md:

```markdown
| Excuse (agent's words) | Reality |
|------------------------|---------|
| "Just this once, given the deadline" | No exceptions. Deadline doesn't change correctness. |
| "We already verified yesterday" | Stale verification ≠ fresh evidence. RUN it. |
| "It's only a small change" | Discipline applies to all changes. |
```

Capture **agent's exact wording**, not a paraphrase. Future agents recognise
their own patterns better than paraphrased ones.

## REFACTOR-phase checklist

After GREEN (compliance achieved), run **NEW** scenarios with different
pressure stackings. Look for:

- [ ] New rationalization paths the original SKILL.md didn't address
- [ ] "Spirit vs letter" arguments ("technically not the case being blocked")
- [ ] Substitution arguments ("similar but not identical to blocker phrasing")
- [ ] Authority arguments ("Timur/CEO said it's fine — am I overriding?")

For each new path found: add an explicit counter-rule in SKILL.md, re-run.
Repeat until 3+ consecutive new scenarios produce compliance with **no new
rationalizations**.

## Description-field discipline

Three current sources disagree here, so state the resolution explicitly rather
than picking one silently.

| Source | Position |
|---|---|
| Agent Skills spec (agentskills.io, 2026-09-02) | "Should describe both what the skill does and when to use it." |
| Anthropic `skill-creator` (2026-09-02) | Both what and when; make it deliberately "pushy" because Claude under-triggers skills. |
| Superpowers `writing-skills` v6.3.0 | "Third-person, describes ONLY when to use (NOT what it does)." |

**Our rule:** follow the spec and `skill-creator` — say what the skill does and
when it fires. Keep the `writing-skills` warning in its narrow, correct form:
never put the **workflow steps** in the description. A description that spells
out the procedure becomes a shortcut Claude takes *instead* of reading the body,
which is fatal for a discipline skill whose whole value is in the body.

```yaml
# BAD — spells out the procedure, Claude follows the description and skips the body
description: Use when shipping work — runs verification command, confirms output, then claims complete

# GOOD — what it does plus when it fires, procedure stays in the body
description: Blocks completion claims until a verification command has been run in the same turn. Use when about to claim work is complete, fixed, passing, or done, and before any success language.
```

## Final acceptance criterion

A discipline skill ships only if it passes this gate:

> Three fresh pressure scenarios (each with 3+ stacked pressures), authored
> *after* the SKILL.md was written, **all produce compliance**.

If any one of the three triggers a violation — back to REFACTOR. Do not ship
a discipline skill with known-violating scenarios on file.

Set `metadata.pressure-tested: "yes, N scenarios, validated <date>"` **only
after** this gate passes, and list the scenario file paths in a `## Provenance`
section in the skill body.

Frontmatter is constrained by the Agent Skills spec
(<https://agentskills.io/specification>), which allows only `name`,
`description`, `license`, `compatibility`, `metadata` and `allowed-tools`.
`metadata` holds string values only, so structured lineage and scenario lists
go in the body, not the frontmatter. Custom top-level keys such as the old
`lineage:` and `pressure_tested:` blocks are off-spec — do not reintroduce them.

## Why this addendum lives separately (not in skill-creator)

Anthropic's `skill-creator` is canonical and updated upstream. We don't fork
it. We **wrap** it: run the normal Anthropic flow first, then layer this
addendum on top for the discipline subset. That keeps Anthropic upgrades
non-conflicting.
