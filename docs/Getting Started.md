# Getting Started

This guide covers prerequisites and your first build. For daily workflow, see [Build Pipeline](Build%20Pipeline.md).

---

## Prerequisites

### 1. Install Pandoc

Download from <https://pandoc.org/installing.html> and ensure `pandoc` is on your PATH.

```bash
pandoc --version
```

### 2. Python 3.10+

The build scripts require Python 3.10 or later with PyYAML:

```bash
python3 --version
pip install pyyaml
```

### 3. XeLaTeX (for PDF output)

Install a TeX distribution with XeLaTeX:

- **Linux**: `sudo apt install texlive-xetex texlive-fonts-extra`
- **macOS**: MacTeX from <https://tug.org/mactex/>
- **Windows**: MiKTeX or TeX Live

---

## First Build

1. Clone the repository and open it in VS Code.
2. Run the default build task:

```bash
python3 build_book.py pdf
```

Or use VS Code's **Run Task** (`Ctrl+Shift+P` → "Run Task" → "Build EPUB+PDF (full)").

Artifacts appear under `build/`:

```
build/
├── The-Struggle-Against-Dehumanization.epub
├── The-Struggle-Against-Dehumanization.pdf
├── The-Struggle-Against-Dehumanization.docx
└── The-Struggle-Against-Dehumanization.rtf
```

---

## Build Targets

| Command | Output |
|---------|--------|
| `python3 build_book.py epub` | EPUB only |
| `python3 build_book.py pdf` | Screen-optimized PDF |
| `python3 build_book.py pdf-print` | Print-ready PDF (mirrored margins) |
| `python3 build_book.py docx` | Word document |
| `python3 build_book.py rtf` | Rich Text Format |
| `python3 build_book.py all` | EPUB + PDF + DOCX + RTF |

Draft variants (`draft-epub`, `draft-pdf`, `draft-all`) show `.draft` blocks and hide `.final` blocks.

---

## Key Files

| File | Purpose |
|------|---------|
| `book-order.txt` | Document ordering (front matter → series → appendices) |
| `metadata.yaml` | Publication metadata (title, author, version) |
| `iasp-config.yaml` | Build configuration (layout, TOC, profiles) |
| `build-profiles.json` | Named build profiles for annexes/alternate outputs |

---

## Next Steps

- [Build Pipeline](Build%20Pipeline.md) — Profiles, tasks, scripts
- [Authoring Quick Start](Authoring%20Quick%20Start.md) — Semantic wrapper syntax
- [Include Directives](Include%20Directives.md) — Modular content includes
