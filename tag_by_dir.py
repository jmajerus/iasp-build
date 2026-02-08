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
    "notes": '::: {.note}',
    "footnotes": '::: {.footnotes}',
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


def _extract_wrapper_tokens(wrapper_line: str) -> list[str]:
    stripped = wrapper_line.strip()
    if not stripped.startswith(":::"):
        return []

    body = stripped[3:].strip()
    if not body:
        return []

    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1].strip()

    if not body:
        return []

    raw_tokens = body.split()
    normalized: list[str] = []
    for token in raw_tokens:
        normalized.extend(_normalize_shorthand_token(token))
    return normalized


def _normalize_shorthand_token(token: str) -> list[str]:
    """
    Convert shorthand notation to proper class tokens.
    
    Examples:
      'note.scope'  -> ['.note', '.scope']
      'sidebar.warning' -> ['.sidebar', '.warning']
      '.note'       -> ['.note']
      '#my-id'      -> ['#my-id']
      'data-x="y"'  -> ['data-x="y"']
    """
    # Already a proper class, id, or attribute token
    if token.startswith('.') or token.startswith('#') or '=' in token:
        return [token]
    
    # Shorthand like "note.scope" -> [".note", ".scope"]
    # or single word "chapter" -> [".chapter"]
    parts = token.split('.')
    return ['.' + part for part in parts if part]


def _extract_class_tokens(wrapper_line: str) -> list[str]:
    return [token for token in _extract_wrapper_tokens(wrapper_line) if token.startswith(".")]


def _format_wrapper_line(tokens: list[str]) -> str:
    if not tokens:
        return ":::"
    return f"::: {{{' '.join(tokens)}}}"


def _dedupe_preserve_order(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token not in seen:
            ordered.append(token)
            seen.add(token)
    return ordered


STANDARD_CLASS_TOKENS: set[str] = set()
for wrapper in DIR_TAGS.values():
    for token in _extract_class_tokens(wrapper):
        STANDARD_CLASS_TOKENS.add(token)


# -------- HELPERS ----------------------------------------------------------

def _count_fence_markers(lines: list[str]) -> int:
    """Count all fenced div markers (openers and closers) in lines.
    
    Returns the total count of ':::' lines - both standalone closers
    and opening markers like '::: {.note}'. An even count indicates
    properly balanced begin/end pairs.
    """
    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped == CLOSING:
            count += 1
        elif OPEN_RE.match(stripped):
            count += 1
    return count


def _validate_fence_balance(path: Path, lines: list[str]) -> None:
    """Warn if fenced div markers are not balanced (odd count)."""
    count = _count_fence_markers(lines)
    if count % 2 != 0:
        print(f"!! WARNING: Unbalanced fences in {path} (count={count}, expected even)")


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
    desired_tokens = _extract_wrapper_tokens(desired_open_stripped)
    desired_classes = [token for token in desired_tokens if token.startswith('.')]
    desired_nonclass = [token for token in desired_tokens if not token.startswith('.')]
    desired_class_set = set(desired_classes)
    wrapper_status = "unchanged"

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
        existing_tokens = _extract_wrapper_tokens(existing_first)
        existing_classes = [token for token in existing_tokens if token.startswith('.')]
        existing_nonclass = [token for token in existing_tokens if not token.startswith('.')]
        existing_class_set = set(existing_classes)
        has_all_desired = bool(desired_classes) and desired_class_set.issubset(existing_class_set)

        if existing_first == desired_open_stripped or has_all_desired:
            # Already correct or already contains the desired semantic classes.
            pass
        else:
            wrapper_status = "updated"
            preserved_classes: list[str] = []
            for cls in desired_classes:
                if cls not in preserved_classes:
                    preserved_classes.append(cls)
            for cls in existing_classes:
                if cls in desired_class_set:
                    continue
                if cls in STANDARD_CLASS_TOKENS:
                    continue
                if cls not in preserved_classes:
                    preserved_classes.append(cls)

            nonclass_tokens = _dedupe_preserve_order(desired_nonclass + existing_nonclass)
            new_tokens = preserved_classes + nonclass_tokens
            lines[first] = _format_wrapper_line(new_tokens) + "\n"
    else:
        # No wrapper: we need to insert one before first non-empty line
        lines.insert(first, desired_open_stripped + "\n")
        wrapper_status = "updated"
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
    
    # Validate fence balance
    _validate_fence_balance(path, lines)
    
    if wrapper_status == "unchanged":
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
