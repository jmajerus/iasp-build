# Pandoc Workflow for The Struggle Against Dehumanization

This project now has a VS Code–driven Pandoc workflow so you can build
EPUB/DOCX/RTF directly from the Markdown sources, without going through
Scrivener.

## Quick Start (TL;DR)

1. Install [Pandoc](https://pandoc.org/installing.html) so the `pandoc` CLI is on your PATH.
2. Clone this repo (or pull latest) and open it in VS Code with Python 3.10+ available.
3. Run `python3 build_book.py pdf` (or the default `Build EPUB+PDF (full)` task) to produce fresh artifacts under `build/`.

Everything else in this document is optional. The remaining sections dive into advanced
profiles, annex builds, catalog helpers, Drive sync, etc. Skim them only when you want to
turn on the extra features.

## 1. Prerequisite: Install Pandoc

1. Download the Windows installer from <https://pandoc.org/installing.html>.
2. Run the installer (accept defaults so `pandoc` is added to your PATH).
3. In a VS Code terminal, verify:

```powershell
pandoc --version
```

You should see version info, not an error.

## 2. Book order and metadata

### `book-order.txt` {#book-order-txt}

`book-order.txt` in the repo root lists all Markdown files, in the
intended reading order (front matter → series → appendices). This file
is the single source of truth for how Pandoc assembles the book.

- Edit `book-order.txt` to add/remove/reorder files as the structure
  evolves.
- Paths are relative to the workspace root and use Windows-style
  separators (e.g. `front matter\PREFACE.md`).

Every build now emits a read-only, Markdown-formatted outline at
`build/book-order.generated.md` (annex profiles land under
`build/annexes/<profile>/book-order.generated.md`). The snapshot keeps
the canonical numbering, preserves indentation by directory, and
expands every `.include` directive it finds (directory includes, banner
wrappers, literal/code inserts, list-only indexes, etc.) so Appendix W
and similar pattern catalogs render all of their nested content in
place. Use it whenever you want an at-a-glance, expanded view of the
current order without scrolling through the raw text list. To
regenerate it without running a full build, call:

```bash
python3 iasp_tooling/scripts/generate_order_snapshot.py --order book-order.txt --max-depth 2
```

Raise/lower `--max-depth` to control how many include layers the
snapshot traverses (defaults to `2`, which covers Appendix W’s
directory-of-directories pattern without descending forever).

### `metadata.json` {#metadata-json}

`metadata.json` in the repo root contains the core book metadata used
for EPUB/DOCX/RTF (title, author, description, etc.). You never edit it
directly anymore—`python3 iasp_tooling/scripts/generate_metadata_json.py`
reads `metadata.yaml`, mirrors every field into JSON, and the build
pipeline invokes it automatically whenever a build runs. Update
`metadata.yaml`, save, and the next build (or an explicit run of
`python3 scripts/generate_metadata_json.py`) regenerates
`metadata.json` for you.

### Build profiles via `build-profiles.json` {#build-profiles}

`build-profiles.json` lets you bundle per-output settings (book order,
static metadata stack, cover image, and base file name) under a short
profile name. The default entry ships with the repo and mirrors the
legacy behavior:

```json
{
  "default": {
    "order_file": "book-order.txt",
    "metadata": ["metadata.json", "metadata.yaml"],
    "cover": "cover.jpg",
    "output_basename": "The-Struggle-Against-Dehumanization"
  }
}
```

Add new siblings (e.g. `"annex-1"`) whenever you need a standalone
annex/companion build. Each profile supports these keys:

- `order_file` – required path to the profile’s `book-order` list.
- `metadata` – string or array of metadata files to feed Pandoc (in
  addition to the dynamic build metadata).
- `cover` – optional EPUB/PDF cover image.
- `output_basename` – base file name for EPUB/PDF/DOCX/RTF artifacts
  (defaults to the main title when omitted).
- `pdf_page` – page for digital PDFs: `letter` (default), `a4`, or `6x9`.
  Print PDFs always use the KDP trim size.

The repo ships with a `build-pipeline-annex` profile that assembles the
“Build Pipeline Technical Annex” booklet (workflow docs + automation
source listings) using `annexes/build-pipeline-annex-order.txt` and its
own lightweight metadata file. Use it as a template for future annexes.

Invoke a profile with `python3 build_book.py --profile annex-1 epub` (or
set `BUILD_PROFILE=annex-1` in the environment). All VS Code tasks pick
up the env var automatically, so you can flip between the main book and
annex outputs without editing scripts.

Annex builds are designed to work both standalone and when embedded in
the full manuscript:

- **Standalone annexes** use their annex metadata file and will default
  to the main bibliography if no bibliography is specified, so citations
  resolve without extra busywork.
- **Embedded annexes** inherit the main manuscript’s references output,
  while the annex content is inserted at the configured location.
- **TOC behavior** is pre-coordinated via `layout.annexes.toc_mode` in
  `iasp-config.yaml` (embedded | external | none). In external mode the
  main TOC shows an Annexes heading + annex titles, and each annex gets
  its own TOC file.

### Build metadata & numbering

Every invocation of `python3 build_book.py …` increments a persistent
build counter stored in `.build-info.json` (ignored by git). The script
also writes `build/build-metadata.json` on each run and feeds it to
Pandoc alongside `metadata.json`/`metadata.yaml`, which exposes these
dynamic fields:

- `build-number` – monotonically increasing integer
- `build-date` / `build-time` – local date + clock snapshot
- `build-timestamp` – ISO 8601 UTC stamp (with a matching `…-local`)
- `version-with-build` – convenience string such as `0.33-preproof (build 42)`
- `last-commit-date` – ISO 8601 timestamp of the most recent git commit
- `last-commit-comment` – the corresponding commit subject/comment line

Delete `.build-info.json` if you ever need to reset the counter on your
local machine; the next build will recreate it starting from `1`.

### `parts_meta.json` {#parts-meta-json}

`parts_meta.json` is now auto-generated from the headings that live in
each `parts/…` Markdown wrapper. Edit the Markdown files directly—the
next build (or a run of `python3 iasp_tooling/scripts/generate_toc.py`) will parse their
headings, regenerate the JSON, and use that data for the Table of
Contents. No more manual JSON editing and no formatting script needed.

- Update the `parts/` Markdown files to rename a part (or series),
  tweak its title, or adjust the subtitle.
- Ensure the files remain listed (and ordered) inside `book-order.txt`
  so the generator knows which structural parts exist.
- Treat `parts_meta.json` as an artifact; if it drifts, rerun
  `python3 iasp_tooling/scripts/generate_toc.py` or a full build to refresh it.

Need a more detailed Table of Contents? Flip `toc.expanded_sections.enabled`
to `true` inside `iasp-config.yaml`. The same generator will scan every
chapter and appendix for headings like `2.1 Subsection Title` or
`DF1-1.2 Objectification` and nest them under their parent entry. Control how
deep the outline goes with `toc.expanded_sections.max_nesting_level` (e.g., `2`
for sections and subsections, `3` to include sub-subsections). Only headings
whose leading tokens contain digits (plain decimal or alphanumeric prefixes)
are included, so narrative H2s without a structured prefix stay out of the TOC.

### Catalog & slot preprocessor (optional)

Appendix W’s pattern catalog (and any future indexes) rides on a
declarative preprocessor:

- `preprocessor/preprocess.yaml` lists collections/items, maps them to
  slot names, and chooses renderers. Leave it alone for the default
  catalog, or add new sections/insertions to spin up alternate views.
- `iasp_tooling/lua/catalog_collections.lua` ships the shared renderers
  (`collection_sections`, `collection_index`, `include_sequence`). Extend
  it when you want bespoke layouts—builds automatically pick up any new
  renderer you add.
- Preview helpers are optional: `python3 iasp_tooling/preprocess/preview.py`
  dumps rendered slots to stdout, while `python3 iasp_tooling/preprocess/expand.py`
  writes `.build/<file>-expanded.md` snapshots with change detection so you
  can review catalog output without a full build.
- The dedicated `preprocessor/README.md` documents vocabulary overrides,
  renderer options, and sample configs if you want to go deeper.

If you never touch the preprocessor files, nothing breaks; the Lua filter
reads the shipping config at build time and fills every slot for you. When
you do want richer catalogs, you only edit YAML/Lua, no pipeline surgery.

## 3. VS Code tasks

Every build, sync, and patch-prep command is wrapped in
`.vscode/tasks.json`, so you can use **Run Task** (`Ctrl+Shift+P`) instead
of memorizing CLI invocations. The tasks break down into four groups.

### Per-file Markdown → RTF helpers

These Pandoc one-offs create RTFs for a single file or structural band—handy
when exporting chapters to Scrivener without touching the full book order:

- `MD → RTF: current file`
- `MD → RTF: appendices`
- `MD → RTF: series`
- `MD → RTF: front matter`

### Full-book builds (default task: `Build EPUB+PDF (full)`)

All of these call `python3 build_book.py <target>` using `book-order.txt` and the
generated metadata stack:

| Task | Target | Notes |
| --- | --- | --- |
| `Build EPUB (full)` | `epub` | Standard EPUB pipeline with Lua filters |
| `Build PDF (full)` | `pdf` | Screen-optimized XeLaTeX build |
| `Build DOCX (full)` | `docx` | Word-friendly proof copy |
| `Build RTF (full)` | `rtf` | Plain RTF for legacy reviewers |
| `Build EPUB (draft)` | `draft-epub` | Full EPUB build flagged as *draft* (`.draft` blocks render, `.final` blocks hide) |
| `Build PDF (draft)` | `draft-pdf` | Draft-stage XeLaTeX build (shows `.draft`, omits `.final`) |
| `Build EPUB+PDF (full)` | `all` | Default task: EPUB + screen-PDF |
| `Build EPUB+PDF (draft)` | `draft-all` | Draft-stage EPUB + PDF bundle for marginalia-heavy review |

### PDF variants and diagnostics

When you need specific page profiles, run the dedicated PDF modes:

- `Build PDF (screen)` → `pdf-screen`, the digital PDF (same as `pdf`): the
  profile's `pdf_page`, US Letter with 1 in margins by default
- `Build PDF (print)` → `pdf-print` (KDP trim size and gutter)
- `Build PDF (debug)` → `pdf-debug` (injects layout sentinels/notes)

These use the same XeLaTeX header but set `pdfmode` (`screen` or `print`)
to tune geometry, header/footer, and link styling. See
[PDF Styling](PDF%20Styling.md#pdf-modes) for the page sizes.

### Operational tasks

- `Drive sync (latest build)` runs `iasp_tooling/scripts/sync_builds_to_drive.py`, copying the
  EPUB/PDF/print-PDF/DOCX/RTF artifacts into your mounted Google Drive folder.
  After a successful copy it automatically increments the patch version so the
  *next* build starts with the new number. Pass `--skip-missing` or
  `--no-version-bump` via the command palette options when needed.
- `Prepare next patch version` calls `iasp_tooling/scripts/bump_patch_version.py` directly.
  Use it when you want to stage the upcoming version without syncing.

All tasks inherit `cwd=${workspaceFolder}`, so relative paths match the repo
root whether you invoke them from the palette or the command bar.

### Command-line builds via `build_book.py`

All VS Code tasks ultimately call `python3 build_book.py <target>` using
the currently selected build profile (defaults to `default`, as defined
in `build-profiles.json`). When you are away from VS Code (or scripting
CI), invoke the same targets directly:

```bash
python3 build_book.py epub   # generate build/The-Struggle-Against-Dehumanization.epub
python3 build_book.py pdf    # XeLaTeX pipeline
python3 build_book.py docx   # Word-friendly proofing copy
python3 build_book.py rtf    # Plain RTF for legacy workflows
python3 build_book.py all    # EPUB + PDF + DOCX + RTF in one run
```

Draft variants (`draft-epub`, `draft-pdf`, `draft-all`) now publish with
`build-stage: draft`, so inline/block elements tagged with `.draft`
render while `.final` wrappers stay hidden. The CLI keeps the
metadata/tag regeneration steps identical to the task runner, so every
format stays in sync even when you’re circulating margin-only drafts.

To switch to an alternate profile (for example, an annex build), pass
`--profile annex-1` on the command line or set `BUILD_PROFILE=annex-1`
before running the script. All build formats then inherit that profile’s
order file, metadata stack, cover, and output names automatically.

### Choosing the right pipeline

- **Main book pipeline** – stick with the default profile +
  `book-order.txt` whenever you’re producing the full manuscript (front
  matter, series, appendices). Every format/task simply reflects the
  current canonical order.
- **Annex pipeline** – when a standalone scholarly paper, companion
  booklet, or complex chapter needs its own build order, metadata, or
  assets, create an annex profile under `annexes/` and run it via
  `python3 build_book.py --profile <slug> …`. Annex builds can reference
  multiple files, include local figures/data, and ship with their own
  front/back matter without touching the flagship book artifacts.
- **Article pipeline** – reserve `python3 build_book.py article <slug>`
  (or the `Build Articles` VS Code task) for truly single-file essays.
  Articles live as flat Markdown files under `articles/`, emit to
  `build/articles/`, suppress book front/back matter by default, and
  only render bibliographies when you opt in. The `articles` target
  batch-builds every file in that directory whose PDF is missing or
  older than the source.

#### Note to beginners

Treat the three pipelines as a ladder you can climb at your own pace:

- Start in the **article pipeline** whenever you need to share a single
  Markdown essay. Drop the file directly under `articles/`, run
  `python3 build_book.py article <slug>` (or the Build Articles task),
  and you get a clean PDF with no inherited front/back matter and no
  bibliography unless you request it with `--with-bibliography`. This is
  the safest sandbox because it avoids `book-order.txt`, cover staging,
  and profile juggling.
- Graduate to the **annex pipeline** once a piece spans multiple files
  or needs its own figures, appendices, or metadata. Copy the example
  profile under `annexes/`, edit its order list, and invoke
  `python3 build_book.py --profile <slug> …`. Annex builds behave exactly
  like miniature books, so you can learn how profiles, metadata stacks,
  and Drive sync behave without risking the flagship manuscript.
- Tackle the **main book pipeline** after you’re comfortable editing
  `book-order.txt` and regenerating metadata. At this level every build
  task reads the canonical ordering, tags directories, and outputs the
  full EPUB/PDF/DOCX/RTF set, so double-check your changes before
  running the default tasks.

Following that progression mirrors the learning path we use on the
project: quick wins with articles, structured experiments with annexes,
then the full manuscript once you trust the tooling.

### Standalone article/doc builds

Reader-facing essays live as single Markdown files directly under
`articles/` (slug derived from the file name). The directory must remain
flat—if a piece needs assets or extra Markdown sources, move it into the
annex pipeline instead of keeping it here.

```bash
# Build via explicit path
python3 build_book.py article "articles/IASP Core.md"

# ...or just reference the slug
python3 build_book.py article iasp-core
```

Pandoc renders the file as-is (still honoring IASP classes and the
shared Lua filter). Articles land in `build/articles/iasp-core.pdf`.
Book-level front/back matter and the global bibliography are suppressed
by default so you only get the manuscript text. Pass an optional second
argument to override the destination file or directory when needed, and
append `--with-bibliography` if you truly need a references section for
a given article:

```bash
python3 build_book.py article iasp-core build/annexes/custom/iasp.pdf
python3 build_book.py article iasp-core --with-bibliography

# Build every article whose PDF is missing/outdated
python3 build_book.py articles
```

The helper skips book-order assembly, TOC regeneration, and cover
staging, making it ideal for technical briefs and annex explainer docs.
The `articles` target walks the flat `articles/` directory and only
rebuilds PDFs whose sources are newer (or missing), so rerunning it is
cheap.
It also suppresses any blocks/headings tagged `.frontmatter` or
`.backmatter` so you can reuse the same source file without the
dedication, copyright, or appendix scaffolding leaking into the article
PDF. Metadata gains `article-slug` so downstream automation can track
provenance unambiguously.

#### Toggling build profiles inside VS Code

- `.vscode/current-profile.json` stores the last profile selection. A
  lightweight Command Variable input reads this file before each task run
  and exports `BUILD_PROFILE`, so every build task automatically targets the
  active profile without editing arguments.
- Trigger **Toggle Build Profile** (new VS Code task + Task Button) to cycle
  through the profiles listed in `build-profiles.json`. The helper script
  updates `current-profile.json` and rewrites the Task Button label so the
  status indicator always shows the live profile (e.g., `$(sync) Profile:
  build-pipeline-annex`).
- The toggle task simply prints the new profile name; if you prefer the CLI,
  run `python3 iasp_tooling/scripts/toggle_build_profile.py` from the repo root to achieve
  the same effect.
- Outputs for non-default profiles are now written to `build/annexes/`, keeping
  the flagship book artifacts at the root of `build/`. The Drive sync task
  mirrors this layout so Google Drive always contains an `annexes/` folder with
  every alternate build.
- The repository ships with a `test-annex` profile (see `annexes/test-annex-*`)
  that exercises the pipeline with a tiny Markdown fixture. Run
  `python3 build_book.py --profile test-annex all` any time you want a quick
  smoke test without touching production manuscripts.

### Preparing the next patch version

The Drive sync workflow (next section) automatically bumps the patch version
after copying the latest build artifacts, so you never have to remember this
step manually. If you ever need to stage the next patch *without* syncing, run
the **Prepare next patch version** task (or execute
`python3 iasp_tooling/scripts/bump_patch_version.py`). The helper increments the patch
component of `version` inside `metadata.yaml` (e.g. `0.3.3 → 0.3.4`) and
immediately regenerates `metadata.json`. Use `--dry-run` to preview the new
number without editing files.

### Syncing build artifacts to Google Drive

When the Drive mount is available via GVFS, run the **Drive sync (latest build)**
VS Code task (or execute `python3 iasp_tooling/scripts/sync_builds_to_drive.py`) to copy the
latest EPUB, PDF, DOCX, and RTF files from `build/` into the mounted folder.
The script also mirrors `build/articles/` to `<Drive>/articles/` and the entire
`build/annexes/` tree (if present) to `<Drive>/annexes/`, so the lightweight
article drops and the richer annex builds stay in lockstep automatically.

- By default the script targets `/run/user/1000/gvfs/google-drive:host=gmail.com,user=skyanchor/0AI3PRVVN3WXRUk9PVA/1MgQaE_TLTrlVIvZNBg9isynjr4ZWo3W_`.
- Override the destination by passing a path argument or setting the
  `DRIVE_SYNC_TARGET` environment variable before invoking the script/task.
- Use `--skip-missing` to allow partial uploads (otherwise the script exits if
  any artifact has not been built yet).
- After a successful copy, the script automatically bumps the patch version via
  `iasp_tooling/scripts/bump_patch_version.py` so the *next* build starts with the new number.
  Pass `--no-version-bump` if you need to skip this once (for example, when
  re-sending an earlier build).

This keeps the proofreader-facing Google Drive folder synchronized without
manually copying the files after every `build_book.py` run.

## 4. Iterating on structure and content

- Adjust chapter/section order by editing `book-order.txt`.
- Refine metadata (title, author, description, rights) by editing the
  dict inside `iasp_tooling/scripts/generate_metadata_json.py`, then rerun the script
  so `metadata.json` picks up the changes.
- Continue to author and edit in Markdown under `front matter/`,
  `chapters/`, and `appendices/`.
- Re-run a build task any time you want a fresh EPUB/DOCX/RTF for
  reading, review, or downstream formatting.

This keeps Markdown as the single source of truth for the book while
providing a one-command path to reader-ready formats.

## 5. Author-intent tags (IASP)

Every structural wrapper now uses Informative Authoring Semantics
Profile (IASP) class names rather than hard-coding `{epub:type="…"}`
attributes. The directory tagger (`python3 tag_by_dir.py`) inserts
openers like `::: {.chapter}` or `::: {.appendix}` automatically, and the
Pandoc Lua filters translate those author-intent classes into
`epub:type`, ARIA, and PDF environments during the build.

When you need local semantic wrappers (callouts, sidebars, inline
epigraphs, etc.) stick to Pandoc’s class shorthand:

```markdown
::: {.callout}
Important margin note.
:::

## A brief detour {.sidebar}
```

The build filter maps these classes to the matching EPUB semantics, so
both CSS and LaTeX receive consistent signals. Current aliases include:

`callout`, `sidebar`, `sidebar-inline`, `epigraph`, `epigraph-inline`,
`bridge`, `part`, `chapter`, `appendix`, `frontmatter`, `backmatter`,
`toc`, `dedication`, `preface`, `introduction`, `conclusion`,
`epilogue`, `prologue`, `acknowledgments`, `summary`, `abstract`,
`footnotes`, and `glossary`.

Legacy `{epub:type="…"}` syntax still works, but the shorthand is now
the canonical authoring form and keeps intent decoupled from any single
output format.

Need a bridge, table, or other full-width block to claim the entire page? Add `.layout-fullpage` to the same fenced Div and the Lua filter will drop a `\clearpage` (or DOCX/RTF equivalent) before and after it while keeping EPUB output untouched. When you only need a one-sided break on a bridge head, keep using `.pre-pagebreak` or `.post-pagebreak` (they can stack with `.layout-fullpage`), and the filter will honor just the requested side.

## 6. PDF box styles live under `iasp_tooling/latex/`

Pandoc feeds XeLaTeX via `iasp_tooling/latex/pdf-header.tex`, which now pulls each framed
environment (sidebars, callouts, notes, examples, definitions, block
quotes) from `iasp_tooling/latex/*.tex` include files. This mirrors the earlier
`blockquote-style.tex` experiment but keeps everything in a single,
discoverable directory.

- Every `iasp_tooling/latex/box-*.tex` file owns exactly one environment definition
  and any helper macros it needs. For example, `iasp_tooling/latex/box-note.tex`
  defines the note frame and the `\notevariant{idea}` banner that the
  Lua filter injects for `::: note.idea` blocks.
- `iasp_tooling/latex/pdf-header.tex` still declares the shared colors (`sidebarbg`,
  `exampleboxline`, etc.) before it executes the `\input{iasp_tooling/latex/...}`
  statements, so cross-cutting tweaks stay centralized.
- `latex/box-blockquote.tex` contains the `quote` environment override
  used everywhere, including the `quote-playground` test target.
- To adjust padding/line widths/margins for a specific block type, edit
  the corresponding file under `iasp_tooling/latex/` and rebuild (e.g.
  `python3 build_book.py quote-playground` for a fast sanity check).

Keeping the LaTeX snippets compartmentalized makes it obvious where to
change a style without hunting through the larger header, while the
build script automatically includes everything so there is nothing extra
to configure.

| Shorthand fence / `epub:type` | LaTeX include | Notes |
| --- | --- | --- |
| `::: callout` (`callout`) | `iasp_tooling/latex/box-callout.tex` | Light annotation frame |
| `::: sidebar` (`sidebar`) | `iasp_tooling/latex/box-sidebar.tex` | Full-width pull-out; also defines `sidebarblock` |
| `::: sidebar-inline` (`sidebar-inline`) | `iasp_tooling/latex/box-sidebar-inline.tex` | Compact variant for inline asides |
| `::: note` (+variants like `.idea`) | `iasp_tooling/latex/box-note.tex` | Includes `\notevariant{...}` helper and note colors |
| `::: example` (`example`) | `iasp_tooling/latex/box-example.tex` | Blue-accent sample blocks |
| `::: definition` (`definition`) | `iasp_tooling/latex/box-definition.tex` | Green-accent glossary-style blocks |
| `> ...` block quotes | `iasp_tooling/latex/box-blockquote.tex` | Overrides LaTeX `quote` environment (shares `quote-playground`) |

Need the inline sidebar glyph on its own line (so the first bullet or paragraph stays aligned)? Add `.glyph-top` (aliases: `.glyph-line`, `.glyph-block`) or set `data-glyph="block"` (value aliases like `stacked`) on the same `::: sidebar-inline` fence. EPUB/HTML will insert a dedicated glyph line, and the PDF build calls `\sidebarinlineglyphline` so both formats stay in sync.

Badge vs. glyph header styles are now independent of layout: add `.sidebar-badge` (or `data-marker="badge"`) to force the SIDEBAR badge row, or `.sidebar-glyph` / `data-marker="glyph"` to keep the inline glyph even on `.sidebar-block` entries. `.sidebar-block` still controls width/margins, while the marker choice only affects the header treatment.

If you want callouts, notes, examples, definitions, and bridge heads to show a badge row automatically, flip `layout.named_block_badges` to `true` inside `iasp-config.yaml`. That switch sets a project-wide default that the Lua filter reads from build metadata. Authors can still override it: add `.badge` or `data-marker="badge"` on any individual block to force the label, or `.nobadge` / `.no-badge` / `.badge-off` when you want to suppress the badge even though the global default is on. Any explicit glyph hint (`glyph="✶"`, `section-glyph="✶"`, `.sidebar-glyph`, `data-marker="glyph"`, etc.) is treated the same as `.nobadge` so glyph-heavy blocks never receive both treatments. Plain `.note` blocks can opt into the global behavior via `layout.named_note_badges`; variant notes such as `.note.insight`, `.note.warning`, `.note.breadcrumb`, `.note.contrast`, `.note.transition`, `.note.navigation`, `.note.bridge`, `.note.usage`, `.note.integration`, `.note.responsibility`, `.note.reflexive`, `.note.synthesis`, `.note.disclosure`, `.note.misuse`, `.note.diagnostic`, or `.note.closing` skip auto-badging unless you add `.badge`, in which case the badge label reflects the qualifier (e.g., `INSIGHT`, `BREADCRUMB`, `DIAGNOSTIC`).

When you need the badge or glyph backgrounds to skew lighter/darker globally, start with the discrete palettes exposed via `layout.glyph_background_palette` and `layout.badge_background_palette`. Valid names (`balanced`, `subtle`, `contrast`, `bright`, `neutral`) map to vetted luma offsets so you can jump between predictable looks without hand-tuning decimals. Leave the palette blank if you prefer manual control—`layout.glyph_background_luma_offset` and `layout.badge_background_luma_offset` still accept floats (or percents) roughly between `-0.2` (darker) and `+0.2` (brighter). The PDF build now resolves those offsets in Python, emitting literal color mixes for each badge/glyph variant instead of doing runtime math in XeLaTeX, so the chips stay tied to their source accent colors with no surprise gray clamps. EPUB/HTML continue to receive the resolved offsets via generated CSS custom properties so themes can implement their own guard rails if needed.
Need a harsher change? Toggle `layout.glyph_background_force_white` to bypass the mix entirely and render those glyph chips on a neutral white backdrop across EPUB/HTML and the PDF badge headers.

When a reviewer or printer requires grayscale-only proofs, flip `layout.render_grayscale.pdf_screen` or `.pdf_print` to `true`. The build tooling now writes those flags into `pdf-layout-overrides.tex`, and `pdf-header.tex` responds by selecting xcolor’s gray color model whenever the active PDF mode matches (`pdf`/`pdf-screen`/articles for screen; `pdf-print` for print). Every accent—including note badges, bridges, link colors, and background fills—lands on the grayscale ramp automatically while EPUB/HTML continue using the full palette. Set the top-level `layout.render_grayscale` value to `true` if you want both modes to convert without repeating yourself.

Prefer traditional running heads for navigation? Opt in via `layout.running_headers`. Set `layout.running_headers.body` to `true` when you want the main body’s chapter titles to appear in the header, and flip `layout.running_headers.appendices` separately if the appendix sequence should receive the same treatment. Those booleans feed into the generated `pdf-layout-overrides.tex`, which toggles the FancyHDR setup inside `iasp_tooling/latex/pdf-header.tex`. Screen PDFs remain head-rule-free but will still print the chapter label when enabled, while print PDFs retain their classic layout unless you leave both switches off.

### Palette Continuum

contrast → darkest option; pushes roughly −0.30 (glyph) / −0.26 (badge) toward black for strong separation.
balanced → mid-dark; about −0.20 / −0.18, matching the old manual defaults you were using.
subtle → gentle dip; around −0.12 / −0.10, just enough to read as tinted without feeling heavy.
neutral → zero offset; leaves the raw mix color untouched.
bright → lightest; applies a small positive lift (+0.08 / +0.10) so the chips slide toward white.

-Think of it as a slider from “contrast” (bold, dark chips) through “balanced” and “subtle” to “neutral,” ending at “bright” for the palest treatment.

### Including external Markdown inline

When an appendix or chapter needs to pull in reusable fragments (e.g., subchapter files, shared sidebars), drop an `include` fenced div where the content should appear:

````markdown
::: {.include path="subchapters/w1-background.md"}
:::

::: {.include data-dir="subchapters/w-series"}
:::
````

- The `path`/`file`/`src` attribute accepts a project-root–relative path (absolute paths work too). Add `mode="dir"` or use the `dir` attribute to sequentially include every `.md/.markdown` file in a folder (alphabetical order).
- The Lua filter reads the referenced Markdown, parses it, and splices the resulting blocks into the document before any other semantic processing. That means wrappers like `::: sidebar` inside the included file behave exactly as if they were written inline.
- Recursive includes are blocked, and missing files raise a readable warning in the build log.
- Directory includes now drop a horizontal rule between each file to make the seams visible while we iterate on formatting. Set `separator="none"` (or `sep="none"`) on the include block if you need a seamless merge.
- Set `glyph="✶"` (or any string) to prepend that glyph to every heading inside the included fragments. EPUB/HTML renders it via a `.section-heading-glyph` span you can restyle; PDF sends it through `\sectionheadingglyph{…}` so it hangs slightly in the margin.
- Add `list="names"` (aliases: `list="filenames"`, `list="basename"`) to emit an ordered or unordered list of the matched files instead of their contents. The emitted names keep the directory order, strip the `.md/.markdown` suffix, and respect `list-style="ordered"` for numbered lists. This is handy when an appendix needs to summarize available fragments without duplicating their prose.
- Provide `banner="Case Study – Internal Memos"` (aliases: `page-banner`, `running-head`) to draw a gray bar across the top margin of every PDF page touched by the included content. EPUB/HTML output wraps the blocks in a `.include-banner` div with a `data-banner-text` attribute so you can simulate the banner via CSS if desired. Use the shorthand `banner="filename"` (also `file`, `basename`, or `auto`) to reuse the include path’s final component (file name without extension, or directory name) as the banner text automatically.
- Always keep the `{.include ...}` braces on the opener so Pandoc parses the block as a nested Div. The legacy `::: include …` shorthand only works at the top level because Pandoc otherwise grabs the closing fence for the surrounding wrapper.

Use this for Appendix W-style modularity or to inject sidebars stored in `sidebars/` without adding dozens of entries to `book-order.txt`.

### Referencing global metadata inside Markdown

Any inline `{{meta:key}}` placeholder is replaced with the corresponding value from `metadata.yaml` (or other metadata files supplied via `--metadata-file`). For example, `{{meta:version}}` expands to the book’s current version string, keeping the Half-Title page synchronized without editing multiple files. The new build metadata makes `{{meta:build-number}}`, `{{meta:build-date}}`, `{{meta:build-timestamp}}`, `{{meta:version-with-build}}`, `{{meta:last-commit-date}}`, and `{{meta:last-commit-comment}}` available everywhere you need them. Placeholders fall back to the original text if the key is missing, so you can add them incrementally.

## 7. Build infrastructure reference

The project relies on a handful of helper scripts, Lua filters, and LaTeX includes.
Keep these paths in mind when troubleshooting or extending the pipeline:

### Python orchestration

  metadata refresh, and Pandoc invocations for every format.
  metadata dictionary.
  `front matter/FRONT MATTER - Table of Contents.md`, and writes
  `parts_meta.json`.
  structure.
  Google Drive folder and auto-bumps the patch version.
  `metadata.yaml` and refreshes `metadata.json` (used standalone or by the sync
  helper).

### Lua filters

  handles `.include` blocks (literal/code/dir modes), injects glyph wrappers,
  manages sidebar/callout mappings, and enforces `.draft`/`.final`
  visibility for in-progress material.

### LaTeX and PDF styling

  environment overrides, and hyperref behavior (switches modes using
  `pdfmode`).
  `box-callout`, `box-note`, `box-example`, `box-definition`, etc.).
  footnotes inside block quotes.

### Other assets

  track build numbers, timestamps, and git metadata.
  backing the TOC.
  layers applied to article, annex, and book builds (shared semantics + reader-specific tweaks).

All of these files live under version control; when introducing new automation
or formats, try to hook into the existing helpers instead of creating parallel
pipelines.

## Further Reading & Reference Docs

If this workflow guide is the only file someone finds, make sure they
know the rest of the ecosystem exists:

- `preprocessor/README.md` – deep dive on the catalog/preprocessor
  schema, vocabulary overrides, and renderer options.
- `iasp_tooling/README.md` – architectural overview of the Python
  tooling, module layout, and plans for packaging the CLI.
- `annexes/Build Pipeline Technical Annex.md` – prose explanation of the
  automation stack plus embedded source listings for every helper
  script.

Skim those when you need to customize the catalog, extend the tooling, or
describe the build system to collaborators.
