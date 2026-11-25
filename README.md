# IASP Build

IASP Build uses Pandoc to build Markdown manuscripts with the Informative Authoring Semantics Profile. It includes the Lua filters, LaTeX templates, stylesheets, and vocabulary used by the manuscript builder.

## Choose a tool

| Your aim | Tool |
| --- | --- |
| Build a manuscript from a repository with an ordered set of chapters, annexes, and named output profiles | **iasp-build**, a Python CLI for local builds and build automation |
| Give an MCP client authoring guidance, validate IASP markup, check quotations, or render a draft for review | **iasp-mcp**, an authoring server with a web interface and quote and bibliography integrations. [iasp-mcp repository](https://github.com/jmajerus/iasp-mcp) |

Both tools use IASP markup and can render documents.

## Use both for a book

Install `iasp-build` in the manuscript’s Python environment and connect your authoring client to `iasp-mcp`. Keep the Markdown sources and build configuration in the manuscript repository. [Set up iasp-mcp](https://github.com/jmajerus/iasp-mcp#quick-start)

1. **Draft and review a chapter.** Ask `iasp-mcp` for help choosing IASP markup, then run `validate_markdown` to catch markup problems and check marked quotations when the quote service is configured. Use `render_document` for a draft preview. Pass Markdown directly for a self-contained draft. For chapters with includes, give the server access to the chapter and its included files.
2. **Carry the sources into the book.** Apply accepted edits to the chapter’s source Markdown. Use the same citation keys in the draft and the manuscript’s `references.bib`. A preview can look up missing bibliography entries through the configured library integrations, so make sure those entries are in the book’s bibliography before the full build.
3. **Assemble the manuscript.** Add the chapter to `book-order.txt` or the order file for its annex. Run a manuscript build with `iasp-build`, such as `iasp-build epub` for the book or `iasp-build --profile annex1 pdf-screen` for a named annex. Review that output for issues that only show up when chapters are assembled, such as cross-references and pagination.

See the [iasp-mcp tool reference](https://github.com/jmajerus/iasp-mcp/blob/main/docs/tools.md) for validation and render options.

## Install

Each release on GitHub has a wheel attached. To make builds repeatable, pin a release in the manuscript's `requirements-build.txt`:

```text
iasp-build[kdp] @ https://github.com/jmajerus/iasp-build/releases/download/v0.1.4/iasp_build-0.1.4-py3-none-any.whl
```

Then install it into the virtual environment used by your manuscript with `python3 -m pip install -r requirements-build.txt`. To try unreleased changes, install from a checkout instead: `python3 -m pip install -e '/path/to/iasp-build'`.

The `kdp` extra adds Pillow for cover generation. Install Pandoc separately. PDF builds require XeLaTeX and its LaTeX packages. The builder can also use EPUBCheck for EPUB validation and qpdf for PDF optimization.

From a manuscript directory:

```sh
iasp-build epub
iasp-build --profile annex1 pdf-screen
iasp-build article-md articles/example.md
```

From elsewhere, pass `--project-root /path/to/manuscript`. A minimal manuscript needs `metadata.yaml`, `book-order.txt` listing its Markdown files, and `iasp-config.yaml` with `toc.enabled: false` if it has no generated table of contents. Named profiles in `build-profiles.json` can select an order file, additional metadata, cover artwork, and an output basename. Outputs go into the manuscript’s `build/` directory.

See the [pipeline guide](docs/Build%20Pipeline.md) and [semantic vocabulary](docs/Semantic%20Vocabulary.md) for details. Some examples use files from the original manuscript checkout.

## Build the technical annex

The IASP Framework Technical Annex bundles the version of the documentation
in this checkout. From the repository root with `iasp-build` installed, run:

```sh
iasp-build --project-root docs --profile iasp-framework epub
iasp-build --project-root docs --profile iasp-framework pdf-screen
```

Use the same command with `docx` for a Word edition. The files are written
to `docs/build/annexes/`.

## Tests

To run the tests, install the `test` extra and run `python3 -m pytest`. The detached-manuscript integration test uses Pandoc.

CI runs the tests on every pull request and on each push to `main`.

## Releasing

Releases are published by the [Release workflow](.github/workflows/release.yml). To cut one, go to **Actions → Release → Run workflow** and choose `patch`, `minor` or `major`. The workflow bumps the version in `pyproject.toml`, runs the tests, commits `Release X.Y.Z` to `main`, and publishes a GitHub Release tagged `vX.Y.Z` with the wheel and sdist attached. If you bump the version yourself in a pull request, merging it to `main` starts the same release.

Manuscripts that pin a release can pick up new ones on their own. A scheduled workflow in the manuscript repository checks for a newer release and opens a pull request that updates the pin.
