# Entity vs concept detection

Heuristics for deciding what gets a page and where it goes.

## Working definitions

- **Entity** — a concrete, nameable thing that you could in principle point at or look up in a registry. Subject-of-a-Wikipedia-page test: would a Wikipedia article exist for this thing, called by this name?
- **Concept** — an abstract pattern, principle, technique, or model. The thing exists in the world of ideas, not in a registry.

Examples:

| Item | Type | Lives in |
| --- | --- | --- |
| Andrej Karpathy | entity | `entities/karpathy.md` |
| Anthropic | entity | `entities/anthropic.md` |
| qmd (the library) | entity | `entities/qmd.md` |
| GOST R 12345-2024 | entity | `entities/gost-r-12345.md` |
| Edition versioning | concept | `concepts/edition-versioning.md` |
| Citation coverage | concept | `concepts/citation-coverage.md` |
| Structured data layer | concept | `concepts/structured-data-layer.md` |
| Lossy compression of context | concept | `concepts/lossy-context-compression.md` |

## Borderline cases

**Technique-named-after-a-person.** E.g. "Karpathy's wiki pattern". This is a concept, not an entity — file under `concepts/karpathy-wiki-pattern.md` (or `concepts/llm-wiki-pattern.md` if the technique has become generic). The entity `entities/karpathy.md` may separately link to the concept page.

**Product vs technique.** Kafka the product is an entity (`entities/kafka.md`). The event-sourcing technique that Kafka enables is a concept (`concepts/event-sourcing.md`).

**Spec/standard.** Usually an entity, because it has a stable identifier. `entities/iso-27001.md`, `entities/anthropic-skills-spec.md`.

**Person mentioned only in passing.** If a person is mentioned once as the author of a quote, don't create an `entities/` page for them. Just cite the source. Pages exist when the wiki has something *about* the thing, not when the thing has been *mentioned*.

## Slug rules

Same as headings:

- Lowercase, kebab-case.
- Strip punctuation; whitespace → `-`.
- Unique within the wiki. If you find a collision (e.g. two libraries both called `foo`), disambiguate: `foo-library`, `foo-project`, or include the org: `acme-foo`.

## When to create vs update

- **No existing page with this slug** → create new page.
- **Existing page with this slug, same entity/concept** → update: add new bullets to Key facts, extend Summary if the new source adds material, append to Related. Never delete existing content from another source.
- **Existing page with this slug, different entity** → disambiguate by renaming the new one (`foo-2`, `foo-library`, etc.). Add a note to the existing page's Related: `[[foo-library]] — different entity, same surface name`.

When updating, **the existing page's citations stay intact**. New facts get new markers pointing at the new source. Mixing sources within one sentence is forbidden — see `citation-extraction.md`.

## Scope cap for v0

For a single ingest, target:

- **≤ ~5 entities** that get pages.
- **≤ ~5 concepts** that get pages.

If the source is dense and clearly has more, write the top ones, then list the rest as "Open questions" or "Related (not yet ingested)" wikilinks on the source page. A future ingest pass (`re-mine` skill, not yet built) will pick them up. The cap exists because citation coverage degrades as page count rises in a single pass.

If you find yourself wanting to exceed the cap, that is a signal that the source deserves multiple smaller wiki pages with focused scopes, not one mega-page per topic.

## How to decide "is this an entity worth a page"

Ask three questions:

1. **Does the source say something specific and citable about this thing?** If the source mentions Anthropic only as "the company Claude is built by", don't make an `anthropic.md` from that alone. Wait for a source that says something substantive.
2. **Is this thing likely to come up again in this wiki?** A library mentioned once may not warrant a page. A library mentioned twice in the same source — yes.
3. **Would `wiki-lint` orphan-check flag this if no other page links to it?** If your only inbound wikilink is the source page itself, the entity is probably premature. Either find a related concept that should link to it, or hold off.

If you're unsure on a specific borderline item, default to **not creating** the page in v0 and adding it to the source page's "Open questions" as a candidate for a future ingest. Premature pages cost more to clean up than missing pages cost to add later.
