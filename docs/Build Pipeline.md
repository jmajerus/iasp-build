# Build Pipeline

This guide covers the Python scripts, VS Code tasks, build profiles, and output formats that make the IASP build system work.

---

## Output Formats

| Target | Command | Description |
|--------|---------|-------------|
| EPUB | `python3 build_book.py epub` | Standard EPUB with Lua filters |
| PDF (screen) | `python3 build_book.py pdf` | Screen-optimized XeLaTeX |
| PDF (print) | `python3 build_book.py pdf-print` | KDP-optimized (6.69×9.61", 9pt, auto gutter) |
| DOCX | `python3 build_book.py docx` | Word-friendly proof copy |
| RTF | `python3 build_book.py rtf` | Plain RTF for legacy workflows |
| All | `python3 build_book.py all` | EPUB + PDF + DOCX + RTF |

Draft variants (`draft-epub`, `draft-pdf`, `draft-all`) show `.draft` blocks and hide `.final` blocks.

### Build a manuscript in a separate directory

With `iasp_tooling` on the Python import path, run the CLI against a
manuscript directory:

```bash
iasp-build --project-root /path/to/manuscript epub
```

The CLI defaults to the current directory. The repository's `build_book.py`
wrapper defaults to the checkout that contains it. The builder reads project
files such as `iasp-config.yaml`, `book-order.txt`, and `metadata.yaml` from
the selected manuscript directory and writes results to its `build/`
directory. Lua filters, LaTeX headers, and stylesheets come from the tooling
package. For a manuscript without a generated table of contents, set
`toc.enabled: false` in `iasp-config.yaml`.

Automatic VS Code task generation applies to manuscripts with a compatible
`build_book.py` wrapper. Other projects can define their own tasks using the
CLI above.

---

## KDP Print Optimization: Intelligent Margin Calculation

The `pdf-print` target uses a **predictive heuristic** to automatically calculate KDP-compliant margins, solving the classic "chicken-and-egg" problem: we need page count to determine required gutter margins, but page count depends on the margins we use.

### The Problem

Amazon KDP has **page-count-based gutter requirements** for perfect binding:

| Page Count | Minimum Gutter (Inside Margin) |
|------------|--------------------------------|
| 24-150 pages | 0.375" |
| 151-300 pages | 0.5" |
| 301-500 pages | 0.625" |
| 501-700 pages | 0.75" |
| 701-828 pages | 0.875" |

**The circular dependency**: To build the PDF, we need to know which gutter to use. But the gutter depends on the final page count, which we don't know until after building.

**Naive approach**: Build repeatedly until margins stabilize (inefficient, requires manual rebuilds when crossing tier boundaries).

### The Solution: Text Area Ratio Heuristic

Page count scales **inversely** with text area. If you reduce text area by 10%, you need ~10% more pages to fit the same content. We use this relationship to **predict** the stable gutter margin in a single build pass.

**Algorithm**:
1. Read previous build's page count (e.g., 734 pages)
2. Infer the gutter used in that build (0.875" for 701-828 tier)
3. Test each possible gutter tier (0.375", 0.5", 0.625", 0.75", 0.875"):
   - Calculate predicted page count: `old_pages × (old_text_area / new_text_area)`
   - Check if prediction is **stable**: Does `get_kdp_gutter_margin(predicted)` equal the tested gutter?
4. Choose the **most conservative** stable option (largest gutter for maximum headroom below 828 limit)
5. Build **once** with that gutter
6. Verify prediction accuracy and warn if tier boundary crossed

### Example

Starting from 734-page build with 0.875" gutter, testing all candidates:

```
Testing gutter candidates:
  0.375" → predicts 668 pages → requires 0.75"   [unstable]
  0.5"   → predicts 683 pages → requires 0.75"   [unstable]
  0.625" → predicts 699 pages → requires 0.75"   [unstable]
  0.75"  → predicts 716 pages → requires 0.875"  [unstable]
  0.875" → predicts 734 pages → requires 0.875"  ✓ STABLE

→ Predicted 734 pages with 0.875" gutter
✓ Build completes: 734 pages, 0.875" gutter required
```

**Result**: Single build, no iteration needed. System automatically adjusts as manuscript grows.

### Benefits

- ✅ **Single-build convergence**: No manual rebuilds when crossing tier boundaries
- ✅ **Automatic adaptation**: Handles manuscript growth seamlessly
- ✅ **Conservative margins**: Maximizes quality and headroom under 828-page limit
- ✅ **Self-correcting**: Validates predictions and warns if tier changes
- ✅ **Transparent**: Clear diagnostic output shows prediction logic

### Build Output

```bash
$ python3 build_book.py pdf-print

→ Predicted 734 pages with 0.875" gutter (based on 734-page previous build)
✓ KDP print PDF: 734 pages, 0.875" gutter required
```

If the prediction is slightly off and crosses a tier boundary, the system warns:

```
⚠ MARGIN CHANGE NEEDED: Page count changed from 724 → 734
  Gutter requirement: 0.75" → 0.875"
  Recommendation: Rebuild for optimal margins
```

The next build will automatically use the correct tier, converging in typically 1-2 passes.

### Technical Details

**Prediction formula**:
```python
predicted_pages = old_page_count × (old_text_area / new_text_area)

where:
    old_text_area = (trim_width - old_gutter - outside) × (trim_height - top - bottom)
    new_text_area = (trim_width - new_gutter - outside) × (trim_height - top - bottom)
```

**Stable solution**: A gutter `G` is stable when:
```python
get_kdp_gutter_margin(predicted_pages_with_G) == G
```

For most manuscripts, there are 1-2 stable solutions. We choose the most conservative (largest gutter) to maximize readability and minimize risk of exceeding the 828-page limit.

**Fallback**: First build without previous PDF uses 0.875" (most conservative), suitable for thick books.

---

## VS Code Tasks

Set `tasks.use_workspace_venv: true` in `iasp-config.yaml` to have generated
tasks run the manuscript’s `.venv` interpreter directly. Install
`iasp-build` in that environment before running a task.

All build commands are wrapped in `.vscode/tasks.json`:

| Task | Target | Notes |
|------|--------|-------|
| Build EPUB (full) | `epub` | Standard EPUB |
| Build PDF (full) | `pdf` | Screen PDF |
| Build PDF (print) | `pdf-print` | Print-ready PDF |
| Build EPUB+PDF (full) | `all` | **Default task** |
| Build EPUB (draft) | `draft-epub` | Draft stage |
| Build PDF (draft) | `draft-pdf` | Draft stage |
| Drive sync (latest build) | — | Sync to Google Drive |
| Prepare next patch version | — | Bump version number |
| Toggle Build Profile | — | Switch active profile |

---

## Build Profiles

`build-profiles.json` bundles per-output settings under named profiles:

```json
{
  "default": {
    "order_file": "book-order.txt",
    "metadata": ["metadata.json", "metadata.yaml"],
    "cover": "cover.jpg",
    "output_basename": "The-Struggle-Against-Dehumanization"
  },
  "build-pipeline-annex": {
    "order_file": "annexes/build-pipeline-annex-order.txt",
    "metadata": ["annexes/build-pipeline-annex-metadata.yaml"],
    "output_basename": "Build-Pipeline-Technical-Annex"
  }
}
```

A profile can also set `pdf_page` to choose the page for digital PDFs: `"letter"` (the default, 1 in margins), `"a4"`, or `"6x9"`. See [PDF Styling](PDF%20Styling.md#pdf-modes).

### Switching Profiles

- **CLI**: `python3 build_book.py --profile annex-1 epub`
- **Environment**: `BUILD_PROFILE=annex-1 python3 build_book.py epub`
- **VS Code**: Run "Toggle Build Profile" task

Profile state is stored in `.vscode/current-profile.json`.

The active profile name is written to `build/build-metadata.json` as `build-profile`. The profile called `default` is the main book; every other profile is treated as a standalone (annex) edition. If `build-profiles.json` has no `default` entry, the first profile listed is used when none is requested. Its name is then not `default`, so `.standalone-only` content shows in that build.

### Profile-Conditional Content

When annexes are pulled into the main book (`@annexes` in `book-order.txt`), the same Markdown files feed both the main book and each standalone annex build. To include content in only some of those builds, wrap it in a fenced div (or use the classes on a heading or span):

```markdown
::: {.license .profile-only profiles="annex1 annex2 annex3"}
This annex is licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
:::

::: {.license .standalone-only}
Shown in every build except the main book (`build-profile` is not `default`).
:::

## Edition Notes {.standalone-only}

Text with an [annex-only aside]{.profile-only profiles="annex2"}.
```

| Class | Renders when |
|-------|--------------|
| `.profile-only` + `profiles="…"` | The active profile is in the list. Separate names with spaces or commas; list `default` to include the main book. |
| `.standalone-only` | The active profile is anything other than `default`. |

- If content is allowed, the control classes and the `profiles` attribute are removed and other classes (such as `.license`) are kept for styling. If it is hidden, the whole element is dropped.
- `.profile-only` without a `profiles` attribute renders everywhere, and the build prints a warning.
- `profile_visibility.lua` runs before every other filter. `iasp-semantics.lua` applies the same rule to content brought in by `.include` directives.
- `generate_toc.py` receives the active profile (`--profile`, or `$BUILD_PROFILE`), so headings in hidden blocks don't appear in the front-matter TOC or the annex TOCs (`annexN-toc.md`) written during that build.
- Documents without these classes are unaffected.

### Title-Page Notice

`titlepage-notice` adds a short notice, such as a licence statement, to the generated title page. Set it in a profile's metadata file (for example `annexes/annex2/annex2-metadata.yaml`) so it appears only in that build:

```yaml
titlepage-notice: |
  This work is licensed under a
  [Creative Commons Attribution-NonCommercial 4.0 International License](https://creativecommons.org/licenses/by-nc/4.0/).
```

The value is Markdown. Links are live in both PDF and EPUB, and several paragraphs are allowed.

| Value | Effect |
|-------|--------|
| *(key absent)* | No change |
| Markdown text | Rendered as the notice |
| `rights` or `true` | Reuse the `rights` metadata value |
| `false` | No notice, even if `titlepage-rights` is set |

`titlepage-rights: true` is a shorthand for `titlepage-notice: rights` and only applies when `titlepage-notice` is absent.

- **PDF**: the notice is printed in small type, centered, below the title, author and date on the `\maketitle` page. The builder writes `build/titlepage-notice.tex` and includes it with `--include-in-header`. The notice is appended to the typeset date block when the document begins, so the document's `date` metadata is untouched. To change the look, define `\iasptitlepagenoticefont` (default `\small`) or `\iasptitlepagenoticeskip` (default `2\baselineskip`) with `\newcommand` in a header included earlier (such as the PDF layout overrides), or with `\renewcommand` inside `\AtBeginDocument`.
- **EPUB**: the notice is inserted as `<div class="titlepage-notice">` at the end of the title-page section in `title_page.xhtml`. It is styled in `styles-epub.css`. pandoc's EPUB title page already prints `rights`, so when the notice is just the `rights` value it is not added a second time.
- DOCX/RTF outputs are unchanged.

---

## Key Scripts

### `build_book.py`

Main orchestrator for all outputs. Handles:
- Metadata refresh and staging
- Pandoc invocations with appropriate filters
- Annex and article compilation profiles

### `iasp_tooling/scripts/generate_toc.py`

Generates Table of Contents from `book-order.txt`:
- Parses headings and semantic tokens
- Writes `front matter/FRONT MATTER - Table of Contents.md`
- Generates `parts_meta.json`

### `iasp_tooling/scripts/generate_metadata_json.py`

Converts `metadata.yaml` → `metadata.json` for Lua filters.

### `scripts/sync_builds_to_drive.py` in the original manuscript

Syncs artifacts to Google Drive:
- Copies EPUB/PDF/DOCX/RTF to mounted folder
- Mirrors `build/articles/` and `build/annexes/`
- Auto-bumps patch version after successful sync
- Flags: `--skip-missing`, `--no-version-bump`

### `scripts/bump_patch_version.py` in the original manuscript

Increments patch version in `metadata.yaml` (e.g., `0.3.3` → `0.3.4`).

---

## Build Metadata

Each build writes dynamic metadata to `build/build-metadata.json`:

| Field | Description |
|-------|-------------|
| `build-number` | Monotonically increasing counter |
| `build-date` / `build-time` | Local timestamp |
| `build-timestamp` | ISO 8601 UTC |
| `version-with-build` | e.g., `0.33-preproof (build 42)` |
| `last-commit-date` | Most recent git commit |
| `last-commit-comment` | Commit subject line |
| `build-stage` | `draft` or `final` (controls `.draft` / `.final` blocks) |
| `build-profile` | Active build profile (controls `.profile-only` / `.standalone-only` blocks) |

Counter persists in `.build-info.json` (git-ignored).

---

## Pipelines

### Main Book Pipeline

Default profile + `book-order.txt` for the full manuscript.

### Annex Pipeline

Standalone scholarly papers or companion booklets:
- Create profile under `annexes/`
- Use `python3 build_book.py --profile <slug> epub`
- Outputs to `build/annexes/<slug>/`

### Article Pipeline

Single-file essays under `articles/`:
- `python3 build_book.py article <slug>` — Single article
- `python3 build_book.py articles` — Batch rebuild all
- `python3 build_book.py article-md <slug-or-path>` — Expanded Markdown for Ghost/CMS
- `python3 build_book.py articles-md` — Batch expanded Markdown build
- Outputs to `build/articles/`
- Suppresses book front/back matter by default

Expanded Markdown artifacts are written to `build/ghost/` and resolve include
directives inline.

### Article AI Disclosure Metadata

Per-article AI disclosure metadata can be stored in a sidecar file next to the
article source:

- `articles/<Article Name>.ai.json`

Supported fields:

- `turns`: exact integer turn count
- `turns_fuzzy_min`, `turns_fuzzy_max`: optional fuzzy range bounds
- `turns_bucket_override`: optional fixed linguistic label (for example, `several`)
- `ai_disclosure`: disclosure template line
- `technical_note`: technical template line

Template placeholders available during export:

- `{turns}` or `{turns_exact}`
- `{turns_fuzzy}`
- `{turns_display}`
- `{turns_bucket}`
- `{turns_bucket_phrase}`

When `turns_bucket_override` is present, it is used for `{turns_bucket}` and
`{turns_bucket_phrase}` instead of automatic bucketing.

Use `update_ai_turns.py` to edit article disclosure metadata and the
`article-md` target to export an article. The external `iasp-mcp` service provides authoring tools.

---

## Build-Time Validation

The build pipeline includes automatic validation checks to catch common authoring issues:

### tag_by_dir.py Validations

When wrapping files with semantic divs, `tag_by_dir.py` runs two validations:

1. **Fence Balance Check** — Warns if fenced div markers (`::: {.class}` and `:::`) are not balanced (odd count indicates missing opener or closer)
   ```
   !! WARNING: Unbalanced fences in path/to/file.md (count=3, expected even)
   ```

2. **Sidebar Header Level Check** — Warns if level 1 headers (`#`) are used inside sidebar blocks
   ```
   !! WARNING: Level 1 header on line 5 inside sidebar block (started line 1) in sidebars/Example.md
      Sidebars should use level 2+ headers (##). Level 1 headers cause badge rendering issues.
   ```
   
   **Why this matters**: In PDF output, level 1 headers map to `\section` commands which have special spacing/layout properties that interfere with the mdframed sidebar box environment, causing badge sections to render after the sidebar bottom edge instead of at the top.

### EPUB Validation

After building EPUB, `epubcheck` automatically validates the output:
- Checks NCX/NAV structure
- Validates XHTML/CSS syntax
- Confirms EPUB 3.0 compliance

Set `SKIP_EPUBCHECK=1` to disable.

### PDF Optimization

**Enabled by default.** PDFs are automatically linearized after generation to ensure compatibility with Adobe Document Cloud (used by Google Drive) and other online viewers.

#### During Build (Default Behavior)

All PDF builds are automatically optimized unless disabled:

```bash
# Normal builds (optimized by default)
python3 build_book.py pdf
python3 build_book.py article "articles/example.md"

# Disable optimization (for debugging or speed)
OPTIMIZE_PDF=0 python3 build_book.py pdf
```

When enabled (default), qpdf re-processes each generated PDF to:
- **Linearize for Fast Web View** (required for Adobe Document Cloud)
- Enable object stream compression
- Preserve all PDF metadata (title, author, keywords, etc.)
- Replace the original file with the optimized version

#### After Build (Standalone Script)

For optimizing existing PDFs without rebuilding:

```bash
# Single file (in-place)
python3 iasp_tooling/scripts/optimize_pdf.py build/articles/example.pdf

# Save to different file
python3 iasp_tooling/scripts/optimize_pdf.py input.pdf output-optimized.pdf

# Batch optimize all articles
python3 iasp_tooling/scripts/optimize_pdf.py build/articles/*.pdf
```

**Note**: Requires qpdf to be installed. Silently skips if unavailable.

**Why it's enabled by default**:
- Required for Adobe Document Cloud (Google Drive PDF viewer)
- Ensures PDFs work in all online viewers and browsers
- Standard best practice for web-distributed PDFs

**When to disable** (set `OPTIMIZE_PDF=0`):
- Debugging LaTeX output (optimization may obscure formatting issues)
- Build speed is critical (adds ~1-2 seconds per PDF)
- You're only viewing PDFs locally and don't need web compatibility

---

## Configuration Files

| File | Purpose |
|------|---------|
| `book-order.txt` | Document ordering |
| `metadata.yaml` | Publication metadata |
| `iasp-config.yaml` | Layout, TOC, Drive sync settings |
| `build-profiles.json` | Named build profiles |

---

## Lua Filters

| Filter | Purpose |
|--------|---------|
| `profile_visibility.lua` | Drops `.profile-only` / `.standalone-only` content hidden for the active profile (runs first) |
| `iasp-semantics.lua` | Semantic processing, includes, visibility |
| `iasp-toc.lua` | Lightweight TOC parsing (profile-aware) |
| `titlepage_notice.lua` | Renders `titlepage-notice` for the PDF and EPUB title pages (run by the builder in a separate pandoc call) |

---

## Related Documentation

- [Getting Started](Getting%20Started.md) — Prerequisites and first build
- [Include Directives](Include%20Directives.md) — External Markdown includes
- [PDF Styling](PDF%20Styling.md) — LaTeX environments and palettes
- [Table of Contents](Table%20of%20Contents.md) — TOC configuration
- [Technical/Structured Data](Technical/STRUCTURED_DATA_TECHNICAL.md) — JSON-LD schema
