<!--
  TEMPLATE: stamped into wikis/<slug>/log.md by wiki-llm-builder.
  Substitute every {{...}} placeholder before writing.
  Delete this comment after stamping.
-->

# Wiki log — {{DOMAIN_TITLE}}

Append-only journal. One header per event in the format `## [YYYY-MM-DD] <type> | <one-line description>`. Mirrors the root project's `log.md` style so `grep "^## \[" log.md | tail -10` works.

Event types:

- `init` — bootstrap event
- `ingest` — a source was added
- `lint` — a health-check ran
- `decision` — a convention or scope decision was made
- `stale` — a source got a new edition; dependent pages flagged stale
- `note` — general note

---

## [{{CREATED_DATE}}] init | Wiki bootstrapped by wiki-llm-builder. {{INIT_NOTE}}
