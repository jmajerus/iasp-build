# Pipeline Tooling (Preview)

This document captures the reusable build/publishing stack that powers *The Struggle
Against Dehumanization*. Treat it as the seed for a standalone "pipeline-tooling"
subproject. Once the code is extracted into its own repo, this README can ship as
`README.md` at the root with only minor tweaks.

------

## Why this exists

The main manuscript now depends on a repeatable toolchain that:

- Tags every Markdown file with IASP semantics.
- Generates structural metadata (TOC parts, build counters, git provenance).
- Invokes Pandoc + XeLaTeX + EPUB filters consistently across dozens of targets.
- Offers three distinct author experiences (articles → annexes → full book).
- Pushes fresh artifacts to Google Drive and bumps semantic versions.

Splitting that logic into a focused project keeps the book repo smaller and makes
it easier to reuse the workflow for future long-form works, annex collections, or
client deliverables.

------

## High-level architecture

```
(tooling)
├─ build_book.py            # master orchestrator (entry point for every task)
├─ tag_by_dir.py            # inserts IASP class wrappers by directory
├─ scripts/
│  ├─ generate_metadata_json.py  # exports canonical metadata.json
│  ├─ bump_patch_version.py      # increments metadata.yaml version + regenerates JSON
│  ├─ sync_builds_to_drive.py    # copies build artifacts + optional version bump
│  └─ toggle_build_profile.py    # cycles VS Code/CLI profile selection
├─ lua/
│  └─ iasp-semantics.lua    # Pandoc filter for semantics + include blocks
├─ latex/
│  └─ box-*.tex             # Reusable PDF environments styled per semantic class
├─ styles/
│  ├─ styles.css            # EPUB baseline
│  └─ styles-epub.css       # Reader-specific tweaks
└─ metadata/
   ├─ metadata.yaml         # human-authored primary metadata
   └─ build-profiles.json   # profile definitions (default + annex profiles)
```

> **Note**: Python, Lua, LaTeX, and CSS assets now live under `iasp_tooling/`. Metadata
> still resides at the repository root while the book remains the canonical source;
> mirror the directory names above when you extract the tooling so imports stay
> predictable.

------

## Supported build surfaces

The orchestrator exposes cohesive targets instead of ad-hoc commands:

| Target | Description |
| ------ | ----------- |
| `epub`, `pdf`, `docx`, `rtf` | Canonical book builds (respect profile order + metadata).
| `draft-epub`, `draft-pdf`, `draft-all` | Draft stage builds (renders `.draft`, hides `.final`).
| `pdf-screen`, `pdf-print`, `pdf-debug` | Margin-specific PDF variants.
| `all` | EPUB + PDF + DOCX + RTF bundle for the active profile.
| `article <slug>` | Single-file PDF from `articles/<slug>.md`, no front/back matter by default.
| `articles` | Incremental sweep that rebuilds every article whose source changed.

All VS Code tasks and CI hooks call `python3 build_book.py <target>` so authors only
need one mental model.

------

## Profiles + build metadata

`build-profiles.json` lets you define reusable bundles per deliverable:

- `order_file` – book-order list (or annex-specific order).
- `metadata` – extra metadata files layered on top of the dynamic build metadata.
- `cover` – optional cover art injected into EPUB/PDF builds.
- `output_basename` – base filename for exported artifacts.

At runtime the script writes `build/build-metadata.json` with the current build
number, timestamps (UTC + local), git commit info, and a `version-with-build`
string so downstream systems can stamp provenance inside the manuscript. The same
metadata feeds Pandoc placeholders (`{{meta:build-number}}`, etc.) so Markdown can
reference the fresh values without manual edits.

------

## Three-tier pipeline (author experience)

1. **Articles** – Flat Markdown files under `articles/`. Use
   `python3 build_book.py article <slug>` or the "Build Articles" VS Code task.
   - Output lands in `build/articles/<slug>.pdf`.
   - Front/back matter and bibliographies stay suppressed unless `--with-bibliography`
     is passed.
   - Ideal for quick public essays or release notes.
2. **Annexes** – Mini-books with their own order list, metadata, and cover art.
   - Define a profile (e.g., `build-pipeline-annex`) pointing at `annexes/<slug>-order.txt`.
   - Run `python3 build_book.py --profile <slug> all` to emit EPUB/PDF/DOCX/RTF sets.
   - Great for technical supplements or multi-file explainers that should stay in
     lockstep with the main toolchain while remaining portable.
3. **Main book** – Default profile wired to `book-order.txt` and the flagship metadata.
   - Every format target respects the canonical ordering, IASP tagging, parts metadata,
     and LaTeX/CSS theming.
   - Use when you want the full manuscript with front matter, appendices, and TOC.

This ladder lets contributors ramp up safely: start with articles, graduate to annex
profiles, and only touch the main build once comfortable with the workflow.

------

## Drive sync + version bumps

`iasp_tooling/scripts/sync_builds_to_drive.py` mirrors fresh artifacts to a mounted Google Drive
folder, ensuring editors always see the latest EPUB/PDF/DOCX/RTF plus the article and
annex directories. After a successful copy it calls `iasp_tooling/scripts/bump_patch_version.py`
so the next build increments `metadata.yaml`'s patch number automatically. Flags allow skipping the
upload or version bump for special cases.

------

## Extending the tooling

- **Add a new profile**: drop a JSON object into `build-profiles.json`, create the
  matching order file + metadata stub, and optionally ship a VS Code task that forces
  `BUILD_PROFILE`.
- **Add a new PDF style**: create `iasp_tooling/latex/box-<name>.tex`, define the environment, and
  map a Pandoc class in `iasp_tooling/lua/iasp-semantics.lua`.
- **Augment metadata**: update `iasp_tooling/scripts/generate_metadata_json.py` and regenerate
  `metadata.json`; the orchestrator will automatically load the new fields.
- **Automate CI**: call `python3 build_book.py <target>` from your runner, then archive
  the contents of `build/<profile>`.

------

## Roadmap for the extraction

1. **Stabilize asset boundary** – keep reader-facing content (chapters, metadata, cover art)
  in the manuscript repo while ensuring every reusable asset (Python, Lua, LaTeX, CSS,
  stock configs) already lives under `iasp_tooling/`. This preserves the “tooling package +
  user data as inputs” philosophy.
2. **Package CLI** – convert `build_book.py` into a module (`pip install -e .`) with an
  entry point such as `iasp-build` so downstream projects can install the toolchain as a
  dependency instead of copying scripts.
3. **Template repo** – publish a starter kit that includes this README, a minimal
  `content/` tree (placeholders only), and GitHub Actions to prove the workflow functions
  out of the box once pointed at real manuscripts.
4. **Configurability layer** – document/env-vars for overriding paths (order file,
  metadata YAML, cover art) without editing the installed package. Provide a
  `custom/` overlay folder so users can shadow default LaTeX/CSS snippets safely.
5. **Documentation polish** – expand this README with diagrams, task screenshots, and a
  migration guide once the code is split. Add per-target HOWTOs plus VS Code setup notes.

------

## Extraction playbook (draft)

1. **Repo skeleton**
  - `src/iasp_iasp_tooling/` – Python package containing the orchestrator, helpers, and
    path-discovery logic.
  - `tooling-assets/` – shipped Lua filters, LaTeX partials, CSS defaults, and step
    templates (copied from this repo’s `iasp_tooling/` tree).
  - `templates/sample-project/` – empty manuscript scaffold with `book-order.txt`,
    `metadata.yaml.example`, and VS Code tasks that point back to the installed tooling.
  - `docs/` – quick-start plus customization guide.
2. **Packaging + distribution**
  - Wire up `pyproject.toml` with a console script (`iasp-build`).
  - Include a `post_install.py` (or CLI flag) that can copy the sample project into a
    user-provided directory to accelerate onboarding.
3. **Backwards compatibility**
  - Keep thin wrappers in existing manuscripts (e.g., `build_book.py` that just imports
    `iasp_tooling.cli`).
  - Maintain env-var fallbacks (`BUILD_PROFILE`, `CONTENT_ROOT`) so older VS Code tasks
    keep working until authors opt into the standalone repo fully.
4. **Release + maintenance**
  - Publish to GitHub Packages (and optionally PyPI) with semantic releases that mirror
    the manuscript’s existing versioning scheme.
  - Document the migration path: `pip install iasp-tooling`, copy the sample project, and
    move manuscript sources into the new structure while keeping user data outside the
    package itself.

Until the extraction happens, keep this file in sync with the tooling behavior so the
future repo launches with accurate documentation.
