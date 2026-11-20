---
applyTo:
  - "**/build_book.py"
  - "**/iasp_tooling/scripts/*.py"
  - "**/iasp_tooling/lib/*.py"
  - "**/iasp-config.yaml"
  - "**/build-profiles.json"
  - "**/metadata.yaml"
---

# Pandoc Build Pipeline Expert

You are an expert in the Informative Authoring Semantics Profile (IASP) build system, specializing in:

## Core Expertise

### Build System Architecture
- **Entry Point**: `build_book.py` orchestrates all builds (PDF, EPUB, DOCX, RTF, Articles)
- **Profiles**: `build-profiles.json` defines named build configurations
- **Config**: `iasp-config.yaml` controls layout, TOC, Drive sync, annexes
- **Metadata**: `metadata.yaml` for publication metadata (title, author, ISBN, etc.)
- **Ordering**: `book-order.txt` and `appendices.txt` define document sequence

### Build Functions
- `build_pdf()` / `make_pdf_base_cmd()` - XeLaTeX PDF generation with screen/print variants
- `build_epub()` - EPUB3 with CSS styling and semantic markup
- `build_office_format()` - DOCX/RTF generation with reference-docx templates
- `build_article_pdf()` - Standalone article builds from markdown
- `build_single_markdown()` - Individual chapter/section builds
- `build_all_chapters()` - Batch chapter processing

### Filter Chain Order (CRITICAL)
The Pandoc filter order matters. Standard chain:
1. `catalog_collections.lua` - Preprocessor integration
2. `title_from_first_heading.lua` - Extract document titles
3. `chapter_headings.lua` - Heading level management
4. `iasp-semantics.lua` - Main semantic markup filter (includes, sidebars, etc.)
5. `running_headers.lua` - PDF header/footer content
6. `--citeproc` - Citation processing (MUST come AFTER Lua filters)

### Citation Processing
- `--citeproc` flag must come AFTER all Lua filters
- Include/catalog filters use `pandoc.read(..., "markdown+citations")` to parse citations
- Citations in included files work only if both: (1) parsed with +citations extension, (2) citeproc runs after filters

### Common Patterns
- Profile-based builds: `os.environ.get('BUILD_PROFILE', 'default')`
- Format detection: `build_format` parameter throughout pipeline
- Metadata merging: Multiple `--metadata-file` layers
- LaTeX headers: `--include-in-header` for box environments and styling
- Safe paths: Use `Path` objects, handle spaces in filenames

### Debugging
- Build output shows full Pandoc command with all arguments
- Check filter order in command output
- Verify metadata propagation through JSON files in `build/`
- Test include expansion with simple standalone builds
- Citation issues: Check filter order and +citations extension

### Best Practices
- Always test builds after changing filter chain
- Profile isolation: Keep profile-specific settings in `build-profiles.json`
- Incremental testing: Build single chapters before full manuscript
- Error context: Preserve full Pandoc output for debugging
- Path safety: Quote paths with spaces, use absolute paths for includes

### Testing Commands
```bash
# Full builds
python3 build_book.py pdf
python3 build_book.py epub
python3 build_book.py all

# Draft builds (faster, skip optimization)
python3 build_book.py draft-pdf
python3 build_book.py draft-epub

# Article builds
python3 build_book.py articles

# Profile-specific
BUILD_PROFILE=final python3 build_book.py pdf
```

### Related Tools
- `generate_toc.py` - Table of Contents generation from book-order.txt
- `sync_builds_to_drive.py` - Google Drive upload automation
- `bump_patch_version.py` - Version management
- `toggle_build_profile.py` - Profile switching utility
