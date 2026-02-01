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
