# IASP Tooling Documentation

This directory contains documentation for the **Informative Authoring Semantics Profile (IASP)** framework and its Pandoc-based build pipeline. These docs are intended for developers and collaborators working on the authoring environment itself—not for prose authoring guidance.

---

## Quick Reference

| Document | Purpose |
|----------|---------|
| [Getting Started](Getting%20Started.md) | Prerequisites, first build, environment setup |
| [Build Pipeline](Build%20Pipeline.md) | Scripts, tasks, profiles, and output formats |
| [Authoring Quick Start](Authoring%20Quick%20Start.md) | Wrapper syntax cheat sheet for semantic blocks |
| [Semantic Vocabulary](Semantic%20Vocabulary.md) | IASP delivery roles and modifiers |
| [Include Directives](Include%20Directives.md) | External Markdown includes, banners, glyphs |
| [PDF Styling](PDF%20Styling.md) | LaTeX box environments, palettes, running headers |
| [Table of Contents](Table%20of%20Contents.md) | TOC generation config and expanded outlines |
| [Part Naming](Part%20Naming.md) | Configurable part/series naming schemes |

---

## Architecture Overview

```
iasp_tooling/
├── latex/             ← XeLaTeX preamble and box-*.tex environments
├── lib/               ← Python library modules (config, order_sources, etc.)
├── lua/               ← Pandoc Lua filters (iasp-semantics.lua, etc.)
├── preprocess/        ← Catalog/slot preprocessor (preview.py, expand.py)
├── scripts/           ← Build automation (generate_toc.py, generate_metadata_json.py, etc.)
└── styles/            ← CSS for EPUB/HTML output
```

---

## Conceptual Layers

1. **Semantic Vocabulary** — IASP defines author-intent terms (delivery roles like `sidebar`, `note`, `bridge` and modifiers like `insight`, `warning`, `example`) that are format-agnostic.

2. **Pandoc Filters** — The Lua filters translate IASP classes into `epub:type`, ARIA roles, and LaTeX environments during the build.

3. **Build Pipeline** — Python scripts orchestrate Pandoc, manage metadata, and generate TOCs.

4. **Output Formats** — EPUB, PDF (screen/print), DOCX, RTF, and standalone articles.

---

## Technical Reference

| Document | Purpose |
|----------|---------|
| [Technical/Structured Data](Technical/STRUCTURED_DATA_TECHNICAL.md) | JSON-LD schema for catalog/metadata feeds |
| [vocab/iasp.ttl](../iasp_tooling/vocab/iasp.ttl) | IASP vocabulary as a SKOS concept scheme (importable into terminology-mcp) |

---

## Files in a manuscript project

- `iasp-config.yaml` — Central configuration for layout, TOC, annexes, Drive sync
- `build-profiles.json` — Named build profiles (default, annexes, test)
- `book-order.txt` — Canonical document ordering
- `metadata.yaml` — Publication metadata (title, author, version)
- `preprocessor/README.md` — Catalog preprocessor deep-dive
- `articles/README.md` — Article pipeline details, Ghost Markdown export, AI disclosure sidecar schema
