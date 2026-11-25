# PDF Styling

This guide covers LaTeX box environments, color palettes, running headers, and other PDF-specific styling options.

---

## LaTeX Box Environments

Pandoc feeds XeLaTeX via `iasp_tooling/latex/pdf-header.tex`, which includes modular box definitions from `iasp_tooling/latex/box-*.tex` files.

| Shorthand | LaTeX Include | Description |
|-----------|---------------|-------------|
| `::: callout` | `box-callout.tex` | Light annotation frame |
| `::: sidebar` | `box-sidebar.tex` | Full-width pull-out |
| `::: sidebar-inline` | `box-sidebar-inline.tex` | Compact inline aside |
| `::: note` | `box-note.tex` | Note with variant support |
| `::: example` | `box-example.tex` | Blue-accent sample block |
| `::: definition` | `box-definition.tex` | Green-accent glossary block |
| `> blockquote` | `box-blockquote.tex` | Quote environment override |

To adjust styling, edit the corresponding `box-*.tex` file and rebuild.

---

## Badge and Glyph Headers

### Marker Styles

| Class/Attribute | Effect |
|-----------------|--------|
| `.sidebar-badge` / `data-marker="badge"` | SIDEBAR badge row |
| `.sidebar-glyph` / `data-marker="glyph"` | Inline glyph (🗒) |
| `.glyph-top` / `data-glyph="block"` | Glyph on its own line |

### Global Badge Defaults

In `iasp-config.yaml`:

```yaml
layout:
  named_block_badges: true   # Auto-badge callouts, notes, examples, etc.
  named_note_badges: false   # Plain .note blocks get badges
```

Override per-block with `.badge` or `.nobadge` / `.no-badge` / `.badge-off`.

---

## Color Palettes

### Background Palettes

Control glyph/badge chip darkness via named palettes:

```yaml
layout:
  glyph_background_palette: balanced
  badge_background_palette: subtle
```

| Palette | Glyph Offset | Badge Offset | Effect |
|---------|--------------|--------------|--------|
| `contrast` | −0.30 | −0.26 | Darkest, strong separation |
| `balanced` | −0.20 | −0.18 | Mid-dark (default) |
| `subtle` | −0.12 | −0.10 | Gentle tint |
| `neutral` | 0 | 0 | Raw mix color |
| `bright` | +0.08 | +0.10 | Lightest |

Or use manual offsets:

```yaml
layout:
  glyph_background_luma_offset: -0.15
  badge_background_luma_offset: -0.12
```

### Force White Background

```yaml
layout:
  glyph_background_force_white: true
```

---

## Grayscale Mode

For grayscale-only proofs:

```yaml
layout:
  render_grayscale:
    pdf_screen: true
    pdf_print: true
```

Or set top-level `render_grayscale: true` for both modes.

---

## Running Headers

Enable chapter titles in PDF headers:

```yaml
layout:
  running_headers:
    body: true        # Main body chapters
    appendices: true  # Appendix sequence
```

The reference section that citeproc generates (titled by `reference-section-title`) gets its own running head, using that title. Because citeproc builds the section only after the other Lua filters have run, `references_running_head.lua` is added right after `--citeproc` to set it.

---

## Page Layout Classes

| Class | Effect |
|-------|--------|
| `.layout-fullpage` | `\clearpage` before and after |
| `.pre-pagebreak` | Page break before only |
| `.post-pagebreak` | Page break after only |

These can be combined on the same fenced Div.

---

## PDF Modes

The build script supports multiple PDF modes:

| Target | Mode | Page |
|--------|------|------|
| `pdf-screen` | screen | 6 × 9 in, 1.1 in margins |
| `pdf-print` | print | KDP trim, 6.69 × 9.61 in, with the gutter sized for the page count |
| `pdf`, `draft-pdf`, `all`, `pdf-debug` | the profile's `pdf_mode` | US Letter, 1.1 in margins, when the profile sets no `pdf_mode` |

`pdf-debug` writes `build/debug.tex` instead of a PDF. `pdf-debug-screen` and `pdf-debug-print` fix the mode.

The mode is passed via `pdfmode` metadata and controls geometry, headers, and link styling in `pdf-header.tex`. Screen and Letter builds write the same file, `<output_basename>.pdf`, so set `pdf_mode` on a profile (see [Build Profiles](Build%20Pipeline.md#build-profiles)) to give it one page size whichever PDF target builds it:

```json
"annex1": {
  "order_file": "annexes/annex1/book-order.txt",
  "output_basename": "Dehumanization-Frameworks",
  "pdf_mode": "screen"
}
```

---

## File Locations

| Path | Purpose |
|------|---------|
| `iasp_tooling/latex/pdf-header.tex` | Main XeLaTeX preamble |
| `iasp_tooling/latex/box-*.tex` | Individual environment definitions |
| `build/pdf-layout-overrides.tex` | Generated per-build overrides |

### Long bridges

Add the `.unframed` class to a `.bridge` wrapper when a long bridge needs to
flow across PDF pages. The bridge keeps its semantic role in EPUB, and
`.pre-pagebreak` and `.post-pagebreak` still apply.
