# Idempotency

What to do when the source-id you computed in Step 2 already has a `sources/<source-id>.md` page.

## Decision tree

```
sources/<source-id>.md exists?
├── No  → proceed (fresh ingest, no idempotency concern).
└── Yes → read existing page's frontmatter.
         │
         ├── edition matches what the user gave  → STOP. No-op + warning.
         │   Reason: source already ingested at this edition. Re-running would
         │   either duplicate facts or churn pages without semantic change.
         │
         ├── edition differs (newer or older)    → STOP. v0 does not migrate.
         │   Tell the user exactly what differs and offer two options:
         │
         │   Option A: rename the new file so its filename includes the new
         │   edition (e.g. karpathy-llm-wiki-2026.md → karpathy-llm-wiki-2027.md),
         │   then re-run ingest. Source-id changes → fresh source-id is created.
         │   Old citations keep resolving to the old source-id.
         │
         │   Option B: leave the wiki as-is and wait for a future skill
         │   (`wiki-reconcile` or `wiki-lint --stale-claims`) to handle
         │   edition migration. This is the safer default if the changes are
         │   minor (typo fixes, no number changes).
         │
         └── frontmatter is malformed or missing → STOP. Tell the user the
             page is corrupted; do not auto-repair. Ask them to either fix
             the page manually or delete it and re-run.
```

## What "stop" looks like

A polite, specific message to the user. Two examples:

> The source `karpathy-llm-wiki-2026` is already ingested in `wikis/context-engineering/` at edition `2026`. Skipping. If you intended to refresh after edits to the markdown, either bump the edition in the filename (e.g. `karpathy-llm-wiki-2026-02.md`) and re-run, or delete the existing `sources/karpathy-llm-wiki-2026.md` first.

> The source `karpathy-llm-wiki-2026` already exists in `wikis/context-engineering/` but at edition `2026-01` (current ingest is for edition `2026-02`). v0 does not migrate editions. Recommendation: rename `wikis/context-engineering/raw/karpathy-llm-wiki-2026.md` to `karpathy-llm-wiki-2026-02.md` and re-run; this creates a fresh source-id while preserving the old one's citations.

Always include the path the user needs to act on. Vague stops are nearly as bad as silent overwrites.

## Why not "merge"?

Merging old and new ingests sounds tempting but breaks the citation contract. If the wiki has a fact citing `§operations` from edition `2026-01`, and the new edition restructured the doc so `§operations` no longer exists, the citation marker is now broken — but the wiki page still claims the fact as if it's valid. Better to keep editions as distinct source-ids.

## The log entry when you stop

Still write a log entry, but use the `note` type:

```
## [<YYYY-MM-DD>] note | wiki-ingest skipped <source-id>: <reason>
```

This is important for two reasons:

1. The user knows the skill considered the source and decided not to act, rather than crashed.
2. `wiki-lint` (or a human reviewer) can grep the log for `wiki-ingest skipped` to see what's pending.

## Edge: same file, same edition, but the user explicitly asks to re-ingest

If the user, after reading your warning, insists ("re-run anyway, I want to refresh"), do **not** silently re-ingest. Instead:

1. Move the existing `sources/<source-id>.md` to `sources/<source-id>.bak-<date>.md`.
2. Move affected entity/concept pages to `.bak-<date>.md` copies as well.
3. Run a fresh ingest.
4. In the log, write: `## [<date>] decision | re-ingest of <source-id> at user request; previous pages saved as .bak-<date>.md`.

The reason for the backup: even with the user's explicit consent, recovering from a wrong re-ingest is much cheaper if the old pages are still on disk.

This path is opt-in and rare. Do not advertise it; only use it when the user has read the warning and confirmed.
