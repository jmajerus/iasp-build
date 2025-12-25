#!/usr/bin/env python3
"""
tag_by_dir.py

Wrap Markdown files with intent-first fenced divs based on their directory.

Instead of emitting EPUB-specific attributes (e.g., {epub:type="chapter"}),
this script now applies Informative Authoring Semantics Profile (IASP) class
names such as `::: {.chapter}` or `::: {.appendix}`. Downstream filters
translate those intent tags into the concrete EPUB/PDF semantics required for
each renderer.

Behavior:
- If a file has no wrapper -> add opening + closing.
- If a file has a wrapper with a different intent -> replace opening.
- If already correct -> leave as-is.
- Always ensures a single closing ':::' as the last non-empty line.

Safe to run on every build (idempotent + migrates semantics on moves).
"""

from pathlib import Path
import shutil
import tempfile
import sys
import re

TOOLING_ROOT = Path(__file__).resolve().parent
ROOT = TOOLING_ROOT.parent

# -------- CONFIG -----------------------------------------------------------

DIR_TAGS = {
    "parts": '::: {.part}',
    "sidebars": '::: {.aside .sidebar-block}',
    "bridges": '::: {.bridge}',
    "bridgeheads": '::: {.bridge}',
    "appendices": '::: {.appendix}',
    "chapters": '::: {.chapter}',
    "subchapters": '::: {.subchapter}',
    "sections": '::: {.section}',
    "subsections": '::: {.subsection}',
    "figures": '::: {.figure}',
    "tables": '::: {.table}',
    "notes": '::: {.footnotes}',
    "glossaries": '::: {.glossary}',
    "indexes": '::: {.index}',
    "bibliographies": '::: {.bibliography}',
    "references": '::: {.references}',
    "epilogues": '::: {.epilogue}',
    "prologues": '::: {.prologue}',
    "introductions": '::: {.introduction}',
    "conclusions": '::: {.conclusion}',
    "forewords": '::: {.foreword}',
    "afterwords": '::: {.afterword}',
    "prefaces": '::: {.preface}',
    "dedications": '::: {.dedication}',
    "acknowledgments": '::: {.acknowledgment}',
    "summaries": '::: {.summary}',
    "abstracts": '::: {.abstract}',
    "contributions": '::: {.contribution}',
    "colophons": '::: {.colophon}',
    "epigraphs": '::: {.epigraph}',
    "errata": '::: {.erratum}'
}

EXTENSIONS = {".md", ".markdown"}

CLOSING = ":::"

# Regex to detect an opening fenced div with any attribute/class payload
OPEN_RE = re.compile(r'^:::\s*(\{[^}]+\}|[.#A-Za-z0-9_-]+)\s*$')


# -------- HELPERS ----------------------------------------------------------

def first_footnote_index(lines):
    """Return the index of the first footnote definition (e.g., [^1]: ...)."""
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("[^") and ":" in stripped:
            return idx
    return None


def has_closing_immediately_before(lines, idx, closing):
    """Check whether the nearest non-empty line before idx is the wrapper closing."""
    j = idx - 1
    while j >= 0 and lines[j].strip() == "":
        j -= 1
    return j >= 0 and lines[j].strip() == closing


def strip_trailing_wrapper_close(lines, closing):
    """Remove a wrapper closing that sits at the physical end of the file."""
    i = len(lines) - 1
    while i >= 0 and lines[i].strip() == "":
        i -= 1
    if i >= 0 and lines[i].strip() == closing:
        del lines[i:]

def semantic_tag_for(path: Path) -> str | None:
    """Return the wrapper line for a file based on its directory."""
    for component in path.parts:
        if component in DIR_TAGS:
            return DIR_TAGS[component]
    return None


def wrap_file(path: Path, desired_open: str) -> None:
    """Ensure file is wrapped with desired_open / ':::'."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Find first and last non-empty lines
    first = next((i for i, l in enumerate(lines) if l.strip()), None)
    last  = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)

    desired_open_stripped = desired_open.strip()
    closing_stripped = CLOSING

    # File is empty / whitespace only
    if first is None:
        new = desired_open_stripped + "\n" + CLOSING + "\n"
        path.write_text(new, encoding="utf-8")
        print(f"++ Wrapped empty file: {path}")
        return

    # See if first non-empty line is an existing semantic wrapper
    existing_first = lines[first].strip()
    m = OPEN_RE.match(existing_first)

    if m:
        # There is an existing semantic wrapper
        if existing_first == desired_open_stripped:
            # Already correct: just ensure closing tag
            pass
        else:
            # Wrong intent tag: replace this line with the desired one
            lines[first] = desired_open_stripped + "\n"
            print(f"** Updated wrapper type for: {path}")
    else:
        # No wrapper: we need to insert one before first non-empty line
        lines.insert(first, desired_open_stripped + "\n")
        # first/last indices are now off, but we only care about closing next

    footnote_idx = first_footnote_index(lines)

    if footnote_idx is not None:
        if not has_closing_immediately_before(lines, footnote_idx, closing_stripped):
            strip_trailing_wrapper_close(lines, closing_stripped)

            insert_block = []
            if footnote_idx > 0 and lines[footnote_idx - 1].strip() != "":
                insert_block.append("\n")
            insert_block.append(CLOSING + "\n")
            if lines[footnote_idx].strip() != "":
                insert_block.append("\n")

            lines[footnote_idx:footnote_idx] = insert_block
    else:
        last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)

        if last is None:
            lines.append(CLOSING + "\n")
        elif lines[last].strip() != closing_stripped:
            if not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(CLOSING + "\n")

    # Safe write
    new_text = "".join(lines)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        tmp.write(new_text)
        tmp_path = Path(tmp.name)

    shutil.move(str(tmp_path), path)
    if existing_first == desired_open_stripped:
        print(f"-- Already correct: {path}")
    else:
        print(f"++ Updated: {path}")


def main() -> None:
    count = 0

    for file in ROOT.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in EXTENSIONS:
            continue

        tag = semantic_tag_for(file)
        if not tag:
            continue

        wrap_file(file, tag)
        count += 1

    print(f"\nDone. Processed {count} file(s).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
