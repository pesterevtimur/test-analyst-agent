# Table extraction

Rules for moving tabular content out of prose and into the structured-data layer.

## Why this is a hard rule

Law #4 of the project: tables are data, never prose. A prose retelling of a table silently drops precision (rounding, dropped rows, transposed columns). The structured copy preserves fidelity; the wiki page links to it.

Breaking this rule is one of the most expensive lint failures because it corrupts the wiki's authority. If a user reads a prose summary and trusts it, but the underlying source has different numbers, the wiki has lied. Keeping the table as data — and forcing pages to link rather than restate — makes this class of error structurally impossible.

## CSV format

- One header row at the top with column names matching `meta.yaml`'s `columns` list.
- One data row per source row.
- Quote any cell containing `,`, `"`, or a newline per RFC 4180.
- UTF-8 encoding (no BOM).
- Use `\n` newlines (not `\r\n`).

Example:

```csv
load_kN,temperature_C,test_duration_h
10.0,20,24
15.5,80,8
"10,5 (revised)",100,4
```

## meta.yaml sidecar format

```yaml
---
source: src:<source-id>
source_location: <locator pointing at where the table appears>
extracted: <YYYY-MM-DD>
table_caption: <text of the table's caption in the source, if any>
columns:
  - name: <column header from CSV>
    type: number | string | date | boolean
    units: <e.g. kN, °C, seconds — when applicable>
    description: <one-line explanation>
  - name: ...
    type: ...
notes: |
  Free-form text. Use for footnotes attached to specific rows or cells,
  caveats from the source, units that didn't fit on a single column row,
  and "the source presented this as percentages but raw counts are also given
  in section §X" pointers.
---
```

## File naming

The CSV filename uses the table's slug, same rules as page slugs (lowercase, kebab-case, unique within `data/tables/`).

To generate the slug:

1. If the source has an explicit table caption — slugify that.
2. Otherwise — slugify the enclosing heading, append `-N` if multiple tables share the heading.

Sidecar filename is `<slug>.meta.yaml` next to `<slug>.csv`.

## Multi-row headers

If the source has a multi-row header (e.g. category row above column-name row), flatten:

- Concatenate parent column with child column, separator `_`.
- Example: parent "Performance" with children "ms" and "throughput" → CSV columns `performance_ms`, `performance_throughput`.
- Document the flattening in `meta.yaml`'s `notes`.

## Merged cells

CSV does not support merged cells. Repeat the value down each merged-cell column:

| Region | Year | Sales |
|---|---|---|
| EU | 2023 | 100 |
|    | 2024 | 110 |

becomes:

```csv
region,year,sales
EU,2023,100
EU,2024,110
```

Document this in `meta.yaml`'s `notes`.

## Footnotes attached to cells

Common in standards and spec documents. Two options, pick one per table:

1. **Inline footnote markers in cells**: prefix the cell with the marker (e.g. `*10.0` for a footnoted value), and put the footnote text in `notes`.
2. **Separate footnotes file**: write `<slug>.notes.md` next to the CSV. Each footnote has a sub-heading matching the inline marker. Reference it from `meta.yaml`'s `notes` field: `Footnotes preserved in <slug>.notes.md`.

Use option 2 when there are more than ~3 footnotes — it scales better.

## Embedded units

If a cell value like `10 kN` mixes number and unit, split:

- Column `load_kN` (numeric).
- Document the unit in `meta.yaml`'s `columns[i].units`.

If a row mixes units within the same column (some `kN`, some `N`), normalize to one unit and document the conversion in `notes`. If normalization is ambiguous, **stop the ingest and ask the user** which canonical unit to use. Better to pause than to silently divide by 1000.

## When the source describes a table in prose instead of laying it out

Sometimes a source says "the values are: A=10, B=20, C=30." If this is the only structured data, treat it as a table:

- Slug it after the surrounding heading.
- CSV columns: `name,value` (or `key,value`).
- Three rows.
- meta.yaml `notes`: "Source presented this as inline prose, not a table; extracted to preserve structure."

Don't restate the values as prose on a wiki page — link to the CSV like any other table.

## Limit for v0

If a single source has more than ~5 tables, extract the first ~5 by relevance to the source's apparent thesis and list the rest as Open questions on the source page. Future ingest passes can pick them up. The reason is the same as the entity cap: bulk-extracting tables makes it more likely you miss a footnote, a unit, or a merge.
