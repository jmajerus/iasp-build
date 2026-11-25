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

There are two kinds of PDF: digital, for reading on a computer, and print, for KDP.

| Target | Kind | Page |
|--------|------|------|
| `pdf`, `pdf-screen`, `draft-pdf`, `all` | digital | The profile's `pdf_page`: US Letter with 1 in margins unless set |
| `pdf-print` | print | KDP trim, 6.69 × 9.61 in, with the gutter sized for the page count |
| `pdf-debug` | digital | Writes `build/debug.tex` instead of a PDF; `pdf-debug-print` for print |

`pdf` and `pdf-screen` are the same build. Both write `<output_basename>.pdf`. Digital PDFs use page-number footers, no head rule, and coloured links. Print PDFs put the folio in the header and keep the KDP gutter. The kind is passed to `pdf-header.tex` as `pdfmode` (`screen` or `print`).

A profile in `build-profiles.json` chooses the digital page with `pdf_page`:

| `pdf_page` | Page | Margins |
|------------|------|---------|
| `letter` (default) | 8.5 × 11 in | 1 in |
| `a4` | 210 × 297 mm | 1 in |
| `6x9` | 6 × 9 in, the trade paperback shape, for proofing against print | 1.1 in |

A portrait page leaves some border on a landscape monitor when the whole page is shown. Fit-width view fills the screen.

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
