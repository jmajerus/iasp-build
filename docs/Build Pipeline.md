# Build Pipeline

This guide covers the Python scripts, VS Code tasks, build profiles, and output formats that make the IASP build system work.

---

## Output Formats

| Target | Command | Description |
|--------|---------|-------------|
| EPUB | `python3 build_book.py epub` | Standard EPUB with Lua filters |
| PDF (screen) | `python3 build_book.py pdf` | Screen-optimized XeLaTeX |
| PDF (print) | `python3 build_book.py pdf-print` | Mirrored margins + binding offset |
| DOCX | `python3 build_book.py docx` | Word-friendly proof copy |
| RTF | `python3 build_book.py rtf` | Plain RTF for legacy workflows |
| All | `python3 build_book.py all` | EPUB + PDF + DOCX + RTF |

Draft variants (`draft-epub`, `draft-pdf`, `draft-all`) show `.draft` blocks and hide `.final` blocks.

---

## VS Code Tasks

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

### Switching Profiles

- **CLI**: `python3 build_book.py --profile annex-1 epub`
- **Environment**: `BUILD_PROFILE=annex-1 python3 build_book.py epub`
- **VS Code**: Run "Toggle Build Profile" task

Profile state is stored in `.vscode/current-profile.json`.

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

### `iasp_tooling/scripts/sync_builds_to_drive.py`

Syncs artifacts to Google Drive:
- Copies EPUB/PDF/DOCX/RTF to mounted folder
- Mirrors `build/articles/` and `build/annexes/`
- Auto-bumps patch version after successful sync
- Flags: `--skip-missing`, `--no-version-bump`

### `iasp_tooling/scripts/bump_patch_version.py`

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
- Outputs to `build/articles/`
- Suppresses book front/back matter by default

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
| `iasp-semantics.lua` | Semantic processing, includes, visibility |
| `iasp-toc.lua` | Lightweight TOC parsing |

---

## Related Documentation

- [Getting Started](Getting%20Started.md) — Prerequisites and first build
- [Include Directives](Include%20Directives.md) — External Markdown includes
- [PDF Styling](PDF%20Styling.md) — LaTeX environments and palettes
- [Table of Contents](Table%20of%20Contents.md) — TOC configuration
- [Technical/Structured Data](Technical/STRUCTURED_DATA_TECHNICAL.md) — JSON-LD schema
