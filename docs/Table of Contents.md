# Table of Contents Generation

The `generate_toc.py` script produces a structured markdown Table of Contents from the manuscript's `book-order.txt` file and individual chapter/appendix source files.

## Overview

The TOC generator:

1. Reads the canonical document order from `book-order.txt`
2. Extracts titles, subtitles, and codes from each source file's headings
3. Renders a hierarchical markdown TOC with configurable depth and formatting
4. Optionally includes expanded section outlines within each entry

All configuration lives in `iasp-config.yaml` under the `toc:` section.

---

## Configuration Reference

### Basic Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Master switch for TOC generation |
| `max_depth` | int | `3` | Maximum heading depth (1–6) |
| `include_appendices` | bool | `true` | Include appendices/annexes in TOC |
| `output_path` | string | `"front matter/FRONT MATTER - Table of Contents.md"` | Output file path |

### Labels and Headers

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `heading_title` | string | `"TABLE OF CONTENTS"` | H1 title at top of TOC |
| `heading_subtitle` | string | `null` | Optional subtitle below title |
| `running_header_label` | string | `null` | Running header for PDF output |
| `frontmatter_label` | string | `"Front Matter"` | Section label for front matter |
| `appendices_label` | string | `"Appendices"` | Section label for appendices |
| `annexes_label` | string | `"Annexes"` | Section label for annexes |
| `epilogue_label` | string | `"Epilogue"` | Section label for epilogue |

### Sidebar Collection

Sidebars can be collected and displayed in the TOC under their respective series/part or in a dedicated appendix sidebars section.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `collect_sidebars` | string | `"bookorder"` | Sidebar collection mode (see below) |
| `appendix_sidebar_section` | bool | `true` | Show separate section for appendix sidebars |
| `appendix_sidebar_label` | string | `"Appendix Sidebars"` | Label for appendix sidebar section |

#### Collection Modes

The `collect_sidebars` option is cumulative—each level includes the previous:

| Mode | What it collects |
|------|------------------|
| `none` | No sidebars displayed in TOC |
| `bookorder` | Only sidebars listed in `book-order.txt` (default) |
| `include` | bookorder + sidebars referenced via `.include` directives in chapter/appendix files |
| `inline` | include + inline `::: {.sidebar}` fenced blocks with H1-H6 headings |

**Note:** Only sidebars with actual Markdown headings (`#` through `######`) are collected. Standalone bold text (`**Title**`) without heading markers is not considered a title.

Example:
```yaml
toc:
  collect_sidebars: include  # book-order.txt + .include directives
  appendix_sidebar_section: true
  appendix_sidebar_label: "Appendix Sidebars"
```

#### Appendix Sidebar Section

When `appendix_sidebar_section: true` (default), sidebars appearing after the first appendix in `book-order.txt` are collected into a separate "Appendix Sidebars" section rather than being grouped with the last series. Set to `false` to suppress this section.

### Note Collection

Notes can be collected and displayed in the TOC in the same manner as sidebars. This is useful for titled notes that provide important context or methodological guidance.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `collect_notes` | string | `"none"` | Note collection mode (see below) |
| `appendix_note_section` | bool | `true` | Show separate section for appendix notes |
| `appendix_note_label` | string | `"Appendix Notes"` | Label for appendix note section |

#### Collection Modes

The `collect_notes` option is cumulative—each level includes the previous:

| Mode | What it collects |
|------|------------------|
| `none` | No notes displayed in TOC (default) |
| `bookorder` | Only notes listed in `book-order.txt` with `# TOC:note` annotations |
| `include` | bookorder + notes referenced via `.include path="notes/..."` directives |
| `inline` | include + inline `::: {.note}` fenced blocks with H1-H6 headings |

**Note:** Only notes with actual Markdown headings (`#` through `######`) are collected. Standalone bold text (`**Title**`) without heading markers is not considered a title. This means callout boxes like `::: note.insight` with only bold text are not included in the TOC.

Example:
```yaml
toc:
  collect_notes: inline     # All notes: book-order, includes, and inline
  appendix_note_section: true
  appendix_note_label: "Notes"
```

#### Book-Order Annotations

To include a note from `notes/` in the TOC when using `bookorder` mode:
```
notes/Methodological Note.md
# TOC:note notes/Methodological Note.md = Methodological Note
```

### Epilogue Detection

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `epilogue_paths` | list | `[]` | Relative paths to epilogue files |
| `epilogue_filenames` | list | `[]` | Filenames that indicate epilogue content |

---

## Part/Series Naming Configuration

Different manuscripts use different naming conventions for major divisions: "Series A", "Part One", "Part 1", "Part I", "Book One", etc. The TOC generator is fully configurable to support any scheme.

Configure under `toc.parts`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `fallback_label` | string | `"Part {part_id}"` | Template when no explicit title. Use `{part_id}` placeholder. |
| `id_from_filename_pattern` | regex | `"SERIES\\s+([A-D])"` | Pattern to extract part ID from filename |
| `code_pattern` | regex | see below | Pattern to parse chapter codes like "A1. Title" |
| `header_pattern` | regex | see below | Pattern matching part header lines (e.g., "SERIES A — PART 1") |

### Example Configurations

**This manuscript** (Series A–D):
```yaml
parts:
  fallback_label: "Series {part_id}"
  id_from_filename_pattern: "SERIES\\s+([A-D])"
  header_pattern: "^SERIES\\s+[A-D]\\s*[—\\-]\\s*PART\\s+\\d+"
```

**Numeric parts** (Part 1, Part 2):
```yaml
parts:
  fallback_label: "Part {part_id}"
  id_from_filename_pattern: "PART\\s+(\\d+)"
  header_pattern: "^PART\\s+\\d+"
```

**Roman numeral parts** (Part I, Part II):
```yaml
parts:
  fallback_label: "Part {part_id}"
  id_from_filename_pattern: "PART\\s+([IVXLCDM]+)"
  header_pattern: "^PART\\s+[IVXLCDM]+"
```

---

## Expanded Section Outlines

When enabled, each chapter/appendix entry can include a nested outline of its internal headings.

Configure under `toc.expanded_sections`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Enable expanded outlines |
| `max_nesting_level` | int | `2` | Depth of nested headings to include (1–3) |
| `appendix_max_nesting_level` | int | same as above | Separate nesting limit for appendices |
| `include_unnumbered` | bool | `false` | Include unnumbered H2+ headings |
| `skip_single_letter` | bool | `false` | Skip single-letter headings (e.g., A–Z glossary) |
| `number_suffix` | string | `null` | Suffix for numbered entries: `"."`, `")"`, etc. |
| `promote_orphaned_headings` | bool | `false` | Promote H3+ if no H2 since last H1 |
| `unnumbered_style` | string | `"list"` | How to render unnumbered: `"list"` or `"plain"` |
| `separator_before_block_prefix` | bool | `false` | Blank line before block headings (Sidebar/Note) |
| `roman_end_marker` | string | `""` | Marker after final Roman numeral item |

### Per-File TOC Overrides

You can customize TOC behavior for individual chapters or appendices by adding special classes to the outer div wrapper.

#### Nesting Level Override (`.toc-nesting-N`)

Override the global `max_nesting_level` for a specific file:

```markdown
::: {.appendix .toc-nesting-0}

# **Appendix DF-ACS — Applied Case Studies**

# DF-ACS-1 — Historical Public Health Case

## 1. Context & Setting

...

# DF-ACS-2 — Historical Political Case

:::
```

**Valid values:**

| Class | Effect |
|-------|--------|
| `.toc-nesting-0` | Only H1 headings (after the title) appear in the outline |
| `.toc-nesting-1` | H2 headings (depth 1) and above |
| `.toc-nesting-2` | H3 headings (depth 2) and above |
| `.toc-nesting-3` | H4 headings (depth 3) and above |

In the example above with `.toc-nesting-0`, only the case titles (H1 headings like "DF-ACS-1", "DF-ACS-2") would appear in the TOC, not their internal sections.

#### Subtitle Suppression (`.no-subtitle`)

Suppress the subtitle from appearing in the TOC for a specific file:

```markdown
::: {.appendix .toc-nesting-0 .no-subtitle}

# **Appendix DF-EX — Exemplars & Test Cases**

### *Case Identifier*

...

:::
```

With `.no-subtitle`, the subtitle ("Case Identifier") will not appear in the TOC entry, even if it exists in the document.

#### Combining Overrides

Multiple overrides can be combined:

```markdown
::: {.appendix .toc-nesting-0 .no-subtitle}
```

This is useful for:
- Appendices with multiple major sections that share repetitive subsection structures
- Case study collections where each case has the same internal template
- Documents where the subtitle is descriptive but not needed in the TOC

### Profile-Conditional Headings

`generate_toc.py` is run with the active build profile (`build_book.py` passes `--profile`; run by hand, it falls back to `$BUILD_PROFILE`, then `default`). Headings inside `.profile-only` / `.standalone-only` blocks hidden for that profile are left out of every TOC written during the run: the front-matter TOC and the annex TOCs (`annexN-toc.md`). Each build regenerates these files, so a main-book build drops headings that only an annex build shows. See *Build Pipeline → Profile-Conditional Content* for the markup.

### Block Heading Prefixes

For headings inside sidebars or notes:

```yaml
expanded_sections:
  block_heading_prefixes:
    sidebar: "Sidebar: "
    note: "Note: "
```

### Note Variants

Custom labels for different note types:

```yaml
expanded_sections:
  note_variants:
    usage: "Usage"
    warning: "Warning"
```

---

## Entry Rendering

All TOC entries (chapters, appendices, annexes, bridges) are rendered through a unified `render_single_entry()` function, ensuring consistent formatting:

### Entry Structure

Each entry consists of:

1. **Label line** — Bold title, with trailing markdown line break (`  `)
2. **Subtitle line** (optional) — Italicized, on its own line
3. **Outline** (optional) — Nested list of section headings

### Formatting Rules

- **Label + Title**: For part headers, the label (e.g., "SERIES A, PART 1") is combined with the chapter title on a single line, both in bold
- **Subtitles**: Rendered in italics on a separate line below the title
- **Trailing spaces**: All lines end with `  ` (two spaces) for proper markdown line breaks
- **Blank lines**: Inserted between entries for visual separation

### Chapter Entry Example

```markdown
**SERIES A, PART 1 — Predatory Design**  
*How Simple Interfaces Exploit Human Trust*  
  **The Spectrum of Predatory Design**  
  **Predatory Design Is Not "Bad UX." It's a Moral Failure.**  
```

### Appendix Entry Example

```markdown
**APPENDIX A — Confirmed Facts, References, and Case Documentation**  
*Source Notes and Evidentiary Grounding for Series A–D*  

  - A.1 Documented Cases of AI Manipulation and Erroneous Outputs
  - A.2 Confirmed Military Uses of Autonomous Systems
```

---

## Title/Subtitle Extraction

The generator infers metadata from each document's headings:

### Priority Order

1. **Explicit attributes**: `toc-title`, `toc-subtitle`, `toc-code` on elements
2. **Semantic tokens**: Classes like `.toc-title`, `.toc-subtitle`
3. **Heuristic inference**: First H1/H2 as title, following lower-level heading as subtitle

### Part Header Detection

For chapters with part headers (e.g., "SERIES A — PART 1" above the title):

- The first heading matching `header_pattern` is captured as the **label**
- The next same-level heading becomes the **title**
- The next lower-level heading becomes the **subtitle**

This allows the TOC to display:
```
**SERIES A, PART 1 — Predatory Design**
*How Simple Interfaces Exploit Human Trust*
```

Rather than treating the part header as the title itself.

---

## Annex Configuration

Annexes (supplementary document collections) have additional configuration under the `annexes:` section:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `toc_mode` | string | `"embedded"` | `"embedded"`, `"external"`, or `"none"` |
| `position_after_appendices` | bool | `true` | Place annexes after appendices |
| `toc_output_pattern` | string | see below | Path pattern for external annex TOCs |
| `toc_heading_title` | string | `"ANNEX TABLE OF CONTENTS"` | Heading for annex TOC |

### TOC Modes

- **`embedded`**: Annex entries appear in the main TOC
- **`external`**: Each annex gets its own TOC file
- **`none`**: No annex TOC generation

---

## Running the Generator

```bash
python3 iasp_tooling/scripts/generate_toc.py
```

The script:
1. Loads configuration from `iasp-config.yaml`
2. Parses `book-order.txt` for document order
3. Extracts metadata from each source file
4. Generates the TOC markdown
5. Writes to the configured output path
6. Updates semantic wrappers via `tag_by_dir.py`

---

## Troubleshooting

### Subtitles appearing on same line as title

Ensure the source file has the subtitle as a separate, lower-level heading:

```markdown
# APPENDIX A — Title Here

### *Subtitle appears on H3*
```

Not embedded in the title itself.

### Part headers duplicated in outline

The generator automatically prunes the label, title, and subtitle from expanded outlines. If duplicates still appear, verify the `header_pattern` regex matches your part header format.

### Entries running together without gaps

All entries should have blank lines between them. If not, check that the entry has either a subtitle or an expanded outline—the generator adds trailing spaces and blank lines appropriately for both cases.
