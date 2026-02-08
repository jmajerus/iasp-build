# Authoring Quick Start

A one-page reference for adding semantic wrappers (sidebars, callouts, notes, etc.) without wading through the full **PANDOC-WORKFLOW.md**. Use this when you just need to drop a block into the manuscript, double-check the syntax, and run a build.

------

## 1. Everyday Workflow

1. **Edit the Markdown source** (chapters, appendices, sidebars, etc.). Keep changes inside fenced wrappers so the Lua filter can map them into EPUB, PDF, DOCX, and RTF automatically.
2. **Run a build**: `python3 build_book.py pdf` (or `epub`, `rtf`, `docx`, `articles`) whenever you want fresh output.
3. **Review + repeat**. Markdown stays the single source of truth.

------

## 2. Wrapper Cheat Sheet

Pick whichever syntax feels natural. The brace form is the canonical one, while the shorthand works for the whitelisted bases below.

| Purpose | Shorthand opener / closer | Brace opener / closer | Defaults & quick toggles |
| --- | --- | --- | --- |
| Full sidebar (badge header, full width) | `::: sidebar.sidebar-block` … `:::` | `::: {.sidebar .sidebar-block}` … `:::` | Badge header and full-width layout. Add `.sidebar-glyph` or `data-marker="glyph"` to swap to the inline glyph style. |
| Inline sidebar (sits inside prose) | `::: sidebar-inline` … `:::` | `::: {.sidebar-inline}` … `:::` | Glyph appears on the first line. Add `.glyph-top` or `data-glyph="block"` to stack the glyph on its own line; add `.sidebar-badge` (or `data-marker="badge"`) for a badge header inside the inline box. |
| Callout / margin note | `::: callout` … `:::` | `::: {.callout}` … `:::` | Light border-left treatment for short asides. No additional options. |
| Notes (variants) | `::: note.<variant>` | `::: {.note .<variant>}` | See the full variant list below. |
| Example block | `::: example` … `:::` | `::: {.example}` … `:::` | Blue accent frame. |
| Definition block | `::: definition` … `:::` | `::: {.definition}` … `:::` | Green glossary frame. |
| Include external Markdown | `::: include path="sidebars/name.md"` … `:::` | `::: {.include path="…"}` … `:::` | Accepts `path`, `dir`, `mode`, `banner`, `glyph`, `list`, and `separator` attributes exactly as documented in **PANDOC-WORKFLOW.md**. |

**Note variants**: standard and framework palettes are listed together so you only have to scan one list.

- `.note.idea` – inline 💡 glyph.
- `.note.insight` – asterism row.
- `.note.insight.major` – badge strip.
- `.note.warning` – warning badge.
- `.note.breadcrumb` – directional chevron (pair with `.badge` for the `BREADCRUMB` label).
- `.note.transition` – inline ⇥ glyph for handoff moments, scene shifts, or narrative pivots.
- `.note.usage` – steel-blue ⚙ badge for “how to apply this” or usage guidance.
- `.note.integration` – teal ∞ badge for integration or synthesis-across-frameworks guidance.
- `.note.responsibility` – amber ⚖ badge for responsibility or accountability framing.
- `.note.reflexive` – slate ⟲ badge for reflexive cautions or self-scrutiny.
- `.note.synthesis` – green ⊕ badge for synthesis blocks that integrate multiple strands into a single takeaway.
- `.note.disclosure` – violet ◊ badge for transparency notes (assumptions, limits, or what is being disclosed).
- `.note.orientation` – teal badge with ⇢, meant for “Reader Navigation” breadcrumbs and orientation guides.
- `.note.navigation` – teal badge with ⇢, meant for “Reader Navigation” breadcrumbs and orientation guides.
- `.note.bridge` – lavender badge mirroring the Series bridge palette when stitching concepts together inside a chapter/appendix.
- `.note.contrast` – inline ⇆ glyph for short “compare/contrast” clarifications between frameworks.
- `.note.misuse` – red badge with ✕ whenever you’re flagging common misreadings or “don’t weaponize this” cautions.
- `.note.diagnostic` – blue badge with 🔍 for pattern-recognition checklists and “diagnostic note” callouts.
- `.note.closing` – muted ∎ badge reserved for “closing note” / endcap reflections.
- `.note.methodology` – indigo ⊢ badge for methodological notes explaining *how* analysis is conducted.
- `.note.context` – warm slate ◉ badge for contextual framing that sets the scene or establishes background.
- `.note.scope` – warm copper ◎ badge for scope notes that delimit boundaries, applicability, or evidentiary thresholds.
- `.note.checklist` – teal ☐ badge for indicative checklists, verification criteria, or structured evidence markers.

**Full-page layout**: add `.layout-fullpage` to any top-level fenced block (bridge, table wrapper, jumbo callout, etc.) when it needs the entire spread. The Lua filter forces a break before *and* after the block in PDF/DOCX/RTF builds, so wide tables start at the top of a page and the following content resumes on a fresh page even if the table itself spills beyond one page. Tables can also auto-promote to full-page when they reach a configured row threshold (see `layout.table_fullpage_min_rows` in iasp-config.yaml). Auto-promoted tables receive a `.table-fullpage` class you can style.

**Table appearance options**: table wrappers accept `.table-compact` (reduced font size + tighter cell padding), `.table-striped` (alternating row tint), and `.table-bordered` (cell borders). Tables can auto-compact based on column count via `layout.table_compact_min_cols` in iasp-config.yaml.

**Bridge pagination control**: still available when you need finer control—add `.pre-pagebreak` or `.post-pagebreak` to the same `::: {.bridge}` fence (optionally alongside `.layout-fullpage`) to request one-sided breaks. EPUB ignores the hints; PDF/DOCX/RTF honor them without requiring nested fences.

**Tip:** Need multi-line attributes, stage guards, or anything beyond classes? Use the brace form.

------

## 3. Common Options

  - Badge: add `.sidebar-badge` *or* `data-marker="badge"` to any `sidebar`/`sidebar-inline` block.
  - Glyph: add `.sidebar-glyph` *or* `data-marker="glyph"` (default for inline sidebars).
- **Named block badges**: set `layout.named_block_badges: true` in `iasp-config.yaml` to auto-badge callouts, notes, examples, definitions, and bridges. Add `.badge` (or `data-marker="badge"`) to force one when the global default is off. Use `.nobadge` / `.no-badge` / `.badge-off`, or supply a local glyph (`glyph="✶"`, `section-glyph="✶"`, `.sidebar-glyph`, `data-marker="glyph"`, etc.), to suppress the badge even when the global switch is on so glyph and badge rows never stack on the same block.
- **Note badges**: note variants such as `.note.insight`, `.note.insight.major`, `.note.warning`, or `.note.breadcrumb` keep their glyph/asterism headers by default. They only receive badges when you explicitly add `.badge`, and the injected label matches the qualifier (e.g., `INSIGHT`, `BREADCRUMB`). Flip `layout.named_note_badges: true` if you want plain `.note` blocks (those without a variant class) to inherit the global badge default.
- **IDs for cross-links**: end the opener with `{#callout-algorithms}` (brace form) or include `id="callout-algorithms"` after the shorthand base to create explicit anchors.

------

## 4. Sanity Check Before Build

- **Does every `:::` opener have a matching closer?** Missing closers are the #1 cause of mangled output.
- **Running attributes line too long?** Break the brace form across lines:
  ```markdown
  ::: {
    .sidebar-inline
    .glyph-top
    data-marker="badge"
  }
  …
  :::
  ```
- **Need a quick preview?** Convert a single file to HTML: `pandoc appendices/APPENDIX\ AB - Foundations\ &\ Further\ Reading.md -o /tmp/test.html` and open it in a browser.

------

## 5. Where to Look Next

- **PANDOC-WORKFLOW.md** – full semantics, Lua filter behavior, build architecture.
- **docs/Authoring/** – deeper dives on footnotes, appendices, anti-pattern indexes, etc.
- **sidebar-test.md** – tiny playground you can edit and rebuild to see how wrappers render without touching main content.

Keep this cheat sheet handy when authoring; everything else can stay hidden until you need it.
