"""generate_toc.py

Derive the semantic Table of Contents from the canonical Markdown
sources. Titles and subtitles are inferred from the first headings in
each file, with optional overrides supplied through existing
intent markup (class tokens or legacy `epub:type`) or explicit `toc-*`
attributes.

Priority order for any section:

1. Explicit `# TOC:` directives in `book-order.txt` (back-compat)
2. Element attributes (`toc-title`, `toc-subtitle`, `toc-code`, `toc-series`)
3. Intent tokens applied via classes or `epub:type` (`toc-title`, `toc-subtitle`)
4. Heuristics based on the first two heading blocks

This keeps the source of truth inside the Markdown files while
honouring the existing semantic markup pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, replace as dataclass_replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iasp_tooling.paths import TOOLING_ROOT, project_root

ROOT = project_root()

from iasp_tooling.lib import config as iasp_config
from iasp_tooling.lib.order_sources import normalize_path

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except ModuleNotFoundError:
    yaml = None  # type: ignore

BOOK_ORDER = ROOT / "book-order.txt"
DEFAULT_TOC_OUTPUT = "front matter/FRONT MATTER - Table of Contents.md"
TOC_OUTPUT_PATH = None
TOC_PATH = None
PART_META_PATH = ROOT / "parts_meta.json"
TAGGER = TOOLING_ROOT / "tag_by_dir.py"
PANDOC_MARKDOWN_FORMAT = "markdown+fenced_divs+header_attributes+link_attributes+smart"
TOC_LUA_FILTER = TOOLING_ROOT / "lua" / "iasp-toc.lua"

# Active build profile. Headings inside `.profile-only` / `.standalone-only`
# blocks that are hidden for this profile are left out of every generated TOC.
# build_book passes --profile; BUILD_PROFILE in the environment is the fallback.
DEFAULT_BUILD_PROFILE = "default"
BUILD_PROFILE = (os.environ.get("BUILD_PROFILE") or "").strip() or DEFAULT_BUILD_PROFILE

EPIGRAPH_TYPES = {"epigraph", "epigraph-inline"}


def _config_section(name: str) -> dict[str, Any]:
    value = CONFIG.get(name)
    return value if isinstance(value, dict) else {}


def _config_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, bool):
        return value
    return default


def _config_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _config_str(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    return default


def _config_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []


def _load_annex_toc_overrides(annex_dir: Path) -> dict[str, Any]:
    config_path = annex_dir / "annex-config.yaml"
    if not config_path.exists():
        return {}
    if yaml is None:
        print(f"-- Warning: PyYAML unavailable; skipping annex config at {config_path}")
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        print(f"-- Warning: unable to read annex config at {config_path}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


CONFIG = iasp_config.load_config()
TOC_SETTINGS = _config_section("toc")
ANNEX_SETTINGS_TOP = _config_section("annexes")
TOC_ENABLED = _config_bool(TOC_SETTINGS.get("enabled"), True)
TOC_INCLUDE_APPENDICES = _config_bool(TOC_SETTINGS.get("include_appendices"), True)
TOC_MAX_DEPTH = _config_int(TOC_SETTINGS.get("max_depth"), 3, minimum=1, maximum=6)
TOC_EXPANDED_SETTINGS = (
    TOC_SETTINGS.get("expanded_sections") if isinstance(TOC_SETTINGS.get("expanded_sections"), dict) else {}
)
TOC_EXPANDED_ENABLED = _config_bool(TOC_EXPANDED_SETTINGS.get("enabled"), False)
TOC_EXPANDED_INCLUDE_UNNUMBERED = _config_bool(
    TOC_EXPANDED_SETTINGS.get("include_unnumbered"),
    False,
)
TOC_EXPANDED_SKIP_SINGLE_LETTER = _config_bool(
    TOC_EXPANDED_SETTINGS.get("skip_single_letter"),
    False,
)
TOC_EXPANDED_NUMBER_SUFFIX = _config_str(
    TOC_EXPANDED_SETTINGS.get("number_suffix"),
    None,
)
TOC_EXPANDED_PROMOTE_ORPHANED = _config_bool(
    TOC_EXPANDED_SETTINGS.get("promote_orphaned_headings"),
    False,
)
TOC_EXPANDED_BLOCK_PREFIXES = (
    TOC_EXPANDED_SETTINGS.get("block_heading_prefixes")
    if isinstance(TOC_EXPANDED_SETTINGS.get("block_heading_prefixes"), dict)
    else {}
)
TOC_EXPANDED_SEPARATOR_BEFORE_BLOCK = _config_bool(
    TOC_EXPANDED_SETTINGS.get("separator_before_block_prefix"),
    False,
)
TOC_EXPANDED_UNNUMBERED_STYLE = _config_str(
    TOC_EXPANDED_SETTINGS.get("unnumbered_style"),
    "list",
)
TOC_EXPANDED_ROMAN_END_MARKER = _config_str(
    TOC_EXPANDED_SETTINGS.get("roman_end_marker"),
    "",
)
TOC_EXPANDED_NOTE_VARIANTS = (
    TOC_EXPANDED_SETTINGS.get("note_variants")
    if isinstance(TOC_EXPANDED_SETTINGS.get("note_variants"), dict)
    else {}
)
TOC_EXPANDED_MAX_NESTING = _config_int(
    TOC_EXPANDED_SETTINGS.get("max_nesting_level"), 2, minimum=1, maximum=3
)
TOC_EXPANDED_APPENDIX_MAX_NESTING = _config_int(
    TOC_EXPANDED_SETTINGS.get("appendix_max_nesting_level"),
    TOC_EXPANDED_MAX_NESTING,
    minimum=1,
    maximum=6,
)
TOC_RUNNING_HEADER_LABEL = _config_str(TOC_SETTINGS.get("running_header_label"), None)
TOC_OUTPUT_PATH = _config_str(TOC_SETTINGS.get("output_path"), DEFAULT_TOC_OUTPUT) or DEFAULT_TOC_OUTPUT
TOC_PATH = ROOT / TOC_OUTPUT_PATH
TOC_HEADING_TITLE = _config_str(TOC_SETTINGS.get("heading_title"), "TABLE OF CONTENTS")
TOC_HEADING_SUBTITLE = _config_str(TOC_SETTINGS.get("heading_subtitle"), None)
TOC_FRONTMATTER_LABEL = _config_str(TOC_SETTINGS.get("frontmatter_label"), "Front Matter")
TOC_APPENDICES_LABEL = _config_str(TOC_SETTINGS.get("appendices_label"), "Appendices")
TOC_APPENDIX_SIDEBAR_SECTION = _config_bool(TOC_SETTINGS.get("appendix_sidebar_section"), True)
TOC_APPENDIX_SIDEBAR_LABEL = _config_str(TOC_SETTINGS.get("appendix_sidebar_label"), "Appendix Sidebars")
TOC_APPENDIX_NOTE_SECTION = _config_bool(TOC_SETTINGS.get("appendix_note_section"), True)
TOC_APPENDIX_NOTE_LABEL = _config_str(TOC_SETTINGS.get("appendix_note_label"), "Appendix Notes")

# Sidebar collection mode: none, bookorder, include, inline (cumulative)
# - none: no sidebars displayed
# - bookorder: only sidebars from book-order.txt (default)
# - include: bookorder + sidebars referenced via .include directives
# - inline: bookorder + include + inline ::: {.sidebar} fenced blocks
_TOC_COLLECT_SIDEBARS_RAW = _config_str(TOC_SETTINGS.get("collect_sidebars"), "bookorder").lower().strip()
TOC_COLLECT_SIDEBARS = _TOC_COLLECT_SIDEBARS_RAW if _TOC_COLLECT_SIDEBARS_RAW in ("none", "bookorder", "include", "inline") else "bookorder"

# Note collection mode: none, bookorder, include, inline (cumulative)
# - none: no notes displayed
# - bookorder: only notes from book-order.txt (default)
# - include: bookorder + notes referenced via .include directives
# - inline: bookorder + include + inline ::: {.note} fenced blocks
_TOC_COLLECT_NOTES_RAW = _config_str(TOC_SETTINGS.get("collect_notes"), "none").lower().strip()
TOC_COLLECT_NOTES = _TOC_COLLECT_NOTES_RAW if _TOC_COLLECT_NOTES_RAW in ("none", "bookorder", "include", "inline") else "none"

TOC_EPILOGUE_LABEL = _config_str(TOC_SETTINGS.get("epilogue_label"), "Epilogue")
TOC_EPILOGUE_PATHS = set(_config_list(TOC_SETTINGS.get("epilogue_paths")))
TOC_EPILOGUE_FILENAMES = set(_config_list(TOC_SETTINGS.get("epilogue_filenames")))
TOC_SELF_REL_PATH = str(TOC_PATH.relative_to(ROOT)) if TOC_PATH.is_absolute() else str(TOC_PATH)

# Part/series naming scheme configuration
# Different manuscripts use different conventions: "Series A", "Part One", "Part I", etc.
# The regex patterns and fallback label are all configurable via iasp-config.yaml.
PARTS_SETTINGS = TOC_SETTINGS.get("parts") if isinstance(TOC_SETTINGS.get("parts"), dict) else {}
PART_FALLBACK_TEMPLATE = _config_str(PARTS_SETTINGS.get("fallback_label"), "Part {part_id}")


def _resolve_annex_settings() -> dict[str, Any]:
    layout = _config_section("layout")
    layout_annex = layout.get("annexes") if isinstance(layout.get("annexes"), dict) else {}
    settings = dict(layout_annex)
    settings.update(ANNEX_SETTINGS_TOP)
    return settings


ANNEX_SETTINGS = _resolve_annex_settings()
ANNEX_IDS = _config_list(ANNEX_SETTINGS.get("annex_ids"))
ANNEX_INCLUDE_INSIDE = _config_bool(ANNEX_SETTINGS.get("include_inside_manuscript"), False)
ANNEX_POSITION_AFTER_APPENDICES = _config_bool(ANNEX_SETTINGS.get("position_after_appendices"), True)
ANNEX_TOC_OUTPUT_PATTERN = _config_str(
    ANNEX_SETTINGS.get("toc_output_pattern"),
    "annexes/{annex_id}/{annex_id}-toc.md",
)
ANNEX_TOC_HEADING_TITLE = _config_str(
    ANNEX_SETTINGS.get("toc_heading_title"),
    "ANNEX TABLE OF CONTENTS",
)
ANNEX_TOC_RUNNING_HEADER = _config_str(
    ANNEX_SETTINGS.get("toc_running_header"),
    "Annex Table of Contents",
)
TOC_ANNEXES_LABEL = _config_str(TOC_SETTINGS.get("annexes_label"), "Annexes")


def _normalize_annex_toc_mode(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"embedded", "external", "none"}:
        return lowered
    return None


ANNEX_TOC_MODE = _normalize_annex_toc_mode(_config_str(ANNEX_SETTINGS.get("toc_mode"), None))
if ANNEX_TOC_MODE is None:
    ANNEX_TOC_MODE = "embedded"

ANNEX_TOC_LINE_ITEM = ANNEX_TOC_MODE == "external"


def _discover_annex_orders() -> list[tuple[str, Path]]:
    annex_root = ROOT / "annexes"
    if not annex_root.exists():
        return []
    candidates = sorted(annex_root.glob("*/book-order.txt"))
    results: list[tuple[str, Path]] = []
    for path in candidates:
        if not path.is_file():
            continue
        annex_id = path.parent.name
        results.append((annex_id, path.resolve()))
    return results


@dataclass
class TocMeta:
    title: str | None = None
    subtitle: str | None = None
    code: str | None = None
    series: str | None = None
    label: str | None = None  # Part header label (e.g., "SERIES A — PART 1")


@dataclass
class NumberedHeading:
    depth: int
    number: str
    title: str


@dataclass
class ExpandedTocOptions:
    enabled: bool
    include_unnumbered: bool
    skip_single_letter: bool
    number_suffix: str | None
    promote_orphaned_headings: bool
    separator_before_block: bool
    unnumbered_style: str
    roman_end_marker: str | None
    max_nesting_level: int
    include_level1: bool
    render_depth0_as_heading: bool


@dataclass
class TocEntryConfig:
    """Configuration for a single TOC entry (appendix, annex, etc.)."""

    label: str
    subtitle: str | None
    path: str | None
    number_style: str = "ordered"  # "ordered", "appendix", "plain"
    number_prefix: str | None = None
    filter_empty_outline_lines: bool = False
    italicize_subtitle: bool = True  # Wrap subtitle in *italics*
    render_depth0_as_list: bool | None = None  # Override: render depth=0 as list items
    suppress_subtitle: bool = False  # Override: suppress subtitle display (.no-subtitle)


def _line_is_list_item(line: str) -> bool:
    """Check if a line starts a markdown list item."""
    return bool(re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", line))


def _ensure_list_separation(lines: list[str]) -> None:
    """Ensure proper blank line separation when transitioning from list to non-list."""
    if lines and _line_is_list_item(lines[-1]):
        lines.append("")


def _append_list_item(lines: list[str], indent: str, label: str) -> None:
    """Append a list item with consistent formatting."""
    lines.append(f"{indent}- {label}")


def render_single_entry(
    config: "TocEntryConfig",
    *,
    lines: list[str],
    heading_map: dict[str, list["NumberedHeading"]],
    expanded_options: "ExpandedTocOptions",
    extend_outline: callable,
    prune_extra_texts: list[str] | None = None,
) -> None:
    """Render a single TOC entry (label, subtitle, outline) with consistent formatting.

    This is the single source of truth for entry rendering, used by both
    the main chapter loop and render_entry_section() for appendices/annexes.

    Args:
        config: Entry configuration with label, subtitle, path, etc.
        lines: Output lines list to append to
        heading_map: Map of file paths to their numbered headings
        expanded_options: TOC expansion options
        extend_outline: Callable to extend lines with outline content
        prune_extra_texts: Additional texts to prune from outline (e.g., original label before formatting)
    """
    has_outline = expanded_options.enabled and heading_map.get(config.path)

    # Check if subtitle should be displayed
    show_subtitle = config.subtitle and not config.suppress_subtitle
    
    if show_subtitle:
        # Label line with trailing spaces, followed by subtitle on next line
        lines.append(f"**{config.label}**  ")
        subtitle_line = config.subtitle
        if config.italicize_subtitle:
            subtitle_line = f"*{subtitle_line}*"
        # Add trailing spaces for markdown line break
        subtitle_line += "  "
        lines.append(subtitle_line)
    else:
        # No subtitle - always add trailing spaces for proper line break
        lines.append(f"**{config.label}**  ")

    if not expanded_options.enabled:
        return

    outline = heading_map.get(config.path)
    if not outline:
        return

    # Prune duplicates: label, subtitle, and any extra texts
    prune_texts = [config.label, config.subtitle]
    if prune_extra_texts:
        prune_texts.extend(prune_extra_texts)
    outline = prune_outline_duplicates(outline, prune_texts)

    # Determine render_depth0_as_heading: can be overridden per-entry
    # If render_depth0_as_list is True, depth=0 entries are rendered as list items
    render_depth0 = expanded_options.render_depth0_as_heading
    if config.render_depth0_as_list is True:
        render_depth0 = False

    formatted = format_heading_outline(
        outline,
        separator_before_block=expanded_options.separator_before_block,
        unnumbered_style=expanded_options.unnumbered_style,
        roman_end_marker=expanded_options.roman_end_marker or "",
        number_suffix=expanded_options.number_suffix,
        number_style=config.number_style,
        number_prefix=config.number_prefix,
        render_depth0_as_heading=render_depth0,
    )

    if config.filter_empty_outline_lines:
        formatted = [line for line in formatted if line != ""]

    extend_outline(formatted)


def render_entry_section(
    entries: list[dict[str, Any]],
    section_label: str,
    *,
    lines: list[str],
    heading_map: dict[str, list[NumberedHeading]],
    expanded_options: ExpandedTocOptions,
    max_depth: int,
    entry_config_factory: callable,
    extend_outline: callable,
) -> None:
    """Unified renderer for appendix/annex entry lists.

    Args:
        entries: List of entry dicts with 'label', 'subtitle', 'path' keys
        section_label: The section header (e.g., "Appendices", "Annexes")
        lines: The output lines list to append to
        heading_map: Map of file paths to their numbered headings
        expanded_options: TOC expansion options
        max_depth: Maximum depth to render
        entry_config_factory: Callable that takes an entry dict and returns TocEntryConfig
        extend_outline: Callable to extend lines with outline content
    """
    if not entries:
        return

    # Ensure blank line before section header for proper markdown separation
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(f"## **{section_label}**")

    if max_depth < 2:
        return

    for entry in entries:
        config = entry_config_factory(entry)

        # Ensure blank line after previous list block before new entry header
        _ensure_list_separation(lines)

        render_single_entry(
            config,
            lines=lines,
            heading_map=heading_map,
            expanded_options=expanded_options,
            extend_outline=extend_outline,
        )
        
        # Add blank line after entry for vertical separation
        lines.append("")


def parse_book_order() -> tuple[
    list[str],
    dict[str, str],
    dict[str, tuple[str, str]],
    dict[str, str],
    dict[str, str],
    dict[str, str],
    dict[str, str],
    set[str],
    dict[str, list[str]],
    dict[str, set[str]],
    bool,
    dict[str, Path],
    set[str],  # main_body_paths - paths from the main order file (not annexes)
]:
    paths: list[str] = []
    front_labels: dict[str, str] = {}
    chapter_labels: dict[str, tuple[str, str]] = {}
    sidebar_labels: dict[str, str] = {}
    note_labels: dict[str, str] = {}
    appendix_labels: dict[str, str] = {}
    annex_labels: dict[str, str] = {}
    annex_source_paths: set[str] = set()
    annex_entries_by_id: dict[str, list[str]] = {}
    annex_source_paths_by_id: dict[str, set[str]] = {}
    annex_toc_in_order = False
    annex_dir_by_id: dict[str, Path] = {}
    main_body_paths: set[str] = set()

    def _merge_label_map(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in extra.items():
            if key not in merged:
                merged[key] = value
        return merged

    def _parse_order_file(order_path: Path) -> tuple[
        list[str],
        dict[str, str],
        dict[str, tuple[str, str]],
        dict[str, str],
        dict[str, str],
        dict[str, str],
        dict[str, str],
    ]:
        file_paths: list[str] = []
        file_front: dict[str, str] = {}
        file_chapter: dict[str, tuple[str, str]] = {}
        file_sidebar: dict[str, str] = {}
        file_note: dict[str, str] = {}
        file_appendix: dict[str, str] = {}
        file_annex: dict[str, str] = {}

        if not order_path.exists():
            return file_paths, file_front, file_chapter, file_sidebar, file_note, file_appendix, file_annex

        for raw in order_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue

            if line.startswith("# TOC:front"):
                try:
                    _, rest = line.split("# TOC:front", 1)
                    path_part, label = rest.split("=", 1)
                    path = path_part.strip()
                    file_front[path] = label.strip()
                except ValueError:
                    pass
                continue

            if line.startswith("# TOC:chapter"):
                try:
                    _, rest = line.split("# TOC:chapter", 1)
                    path_part, rhs = rest.split("=", 1)
                    code_part, title_part = rhs.split("|", 1)
                    file_chapter[path_part.strip()] = (code_part.strip(), title_part.strip())
                except ValueError:
                    pass
                continue

            if line.startswith("# TOC:sidebar"):
                try:
                    _, rest = line.split("# TOC:sidebar", 1)
                    path_part, label = rest.split("=", 1)
                    file_sidebar[path_part.strip()] = label.strip()
                except ValueError:
                    pass
                continue

            if line.startswith("# TOC:note"):
                try:
                    _, rest = line.split("# TOC:note", 1)
                    path_part, label = rest.split("=", 1)
                    file_note[path_part.strip()] = label.strip()
                except ValueError:
                    pass
                continue

            if line.startswith("# TOC:appendix"):
                try:
                    _, rest = line.split("# TOC:appendix", 1)
                    path_part, label = rest.split("=", 1)
                    file_appendix[path_part.strip()] = label.strip()
                except ValueError:
                    pass
                continue

            if line.startswith("# TOC:annex"):
                try:
                    _, rest = line.split("# TOC:annex", 1)
                    path_part, label = rest.split("=", 1)
                    file_annex[path_part.strip()] = label.strip()
                except ValueError:
                    pass
                continue

            if line.startswith("#"):
                continue

            file_paths.append(line)

        return file_paths, file_front, file_chapter, file_sidebar, file_note, file_appendix, file_annex

    main_paths, main_front, main_chapter, main_sidebar, main_note, main_appendix, main_annex = _parse_order_file(BOOK_ORDER)
    paths.extend(main_paths)
    # Track normalized paths from the main order file (for filtering annex-only content)
    for p in main_paths:
        main_body_paths.add(normalize_path(p).lower())
    front_labels.update(main_front)
    chapter_labels.update(main_chapter)
    sidebar_labels.update(main_sidebar)
    note_labels.update(main_note)
    appendix_labels.update(main_appendix)
    annex_labels.update(main_annex)

    if ANNEX_TOC_MODE != "none":
        discovered_orders: list[tuple[str, Path]] = []
        if ANNEX_TOC_MODE == "embedded":
            discovered_orders = _discover_annex_orders()
        profiles_path = ROOT / "build-profiles.json"
        definitions: dict[str, Any] = {}
        if profiles_path.exists():
            try:
                raw = json.loads(profiles_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
            if isinstance(raw, dict):
                definitions = raw

        annex_paths: list[tuple[str, str]] = []
        for annex_id in ANNEX_IDS:
            entry = definitions.get(annex_id)
            order_value = None
            if isinstance(entry, dict):
                order_value = entry.get("order_file") or entry.get("order")

            candidate = Path(order_value) if order_value else Path(annex_id)
            if not candidate.is_absolute():
                candidate = (ROOT / candidate).resolve()

            if candidate == BOOK_ORDER:
                continue

            if not candidate.exists():
                fallback = ROOT / "annexes" / str(annex_id) / "book-order.txt"
                if fallback.exists():
                    candidate = fallback.resolve()

            annex_paths.append((annex_id, str(candidate)))

            annex_key = Path(annex_id).name or candidate.stem
            annex_entries_by_id.setdefault(annex_key, [])
            annex_source_paths_by_id.setdefault(annex_key, set())

        annex_orders: list[str] = []
        duplicates: list[str] = []
        discovered_ids = {annex_id for annex_id, _ in annex_paths}
        for annex_id, path in discovered_orders:
            if annex_id in discovered_ids:
                continue
            annex_paths.append((annex_id, str(path)))

        for annex_id, raw_path in annex_paths:
            order_path = Path(raw_path)
            annex_key = Path(annex_id).name or order_path.stem
            file_paths, file_front, file_chapter, file_sidebar, file_note, file_appendix, file_annex = _parse_order_file(
                order_path
            )
            annex_dir_by_id.setdefault(annex_key, order_path.parent)
            for entry in file_paths:
                key = normalize_path(entry).lower()
                if any(normalize_path(existing).lower() == key for existing in paths):
                    duplicates.append(entry)
                    continue
                annex_orders.append(entry)
                annex_source_paths.add(key)
                annex_entries_by_id.setdefault(annex_key, []).append(entry)
                annex_source_paths_by_id.setdefault(annex_key, set()).add(key)
                filename = Path(entry).name.lower()
                if "toc" in filename and "annexes/" in key:
                    annex_toc_in_order = True
            front_labels = _merge_label_map(front_labels, file_front)
            chapter_labels = _merge_label_map(chapter_labels, file_chapter)
            sidebar_labels = _merge_label_map(sidebar_labels, file_sidebar)
            note_labels = _merge_label_map(note_labels, file_note)
            appendix_labels = _merge_label_map(appendix_labels, file_appendix)
            annex_labels = _merge_label_map(annex_labels, file_annex)

        if duplicates:
            sample = ", ".join(duplicates[:5])
            print(
                "-- Warning: annex order entries already exist in main order; "
                f"skipping {len(duplicates)} duplicate(s). Sample: {sample}"
            )

        if annex_orders:
            appendices = [
                idx for idx, entry in enumerate(paths) if entry.strip().lower().startswith("appendices/")
            ]
            if ANNEX_POSITION_AFTER_APPENDICES:
                insert_at = appendices[-1] + 1 if appendices else len(paths)
            else:
                insert_at = appendices[0] if appendices else len(paths)
            paths[insert_at:insert_at] = annex_orders

    return (
        paths,
        front_labels,
        chapter_labels,
        sidebar_labels,
        note_labels,
        appendix_labels,
        annex_labels,
        annex_source_paths,
        annex_entries_by_id,
        annex_source_paths_by_id,
        annex_toc_in_order,
        annex_dir_by_id,
        main_body_paths,
    )


def run_pandoc_json(path: Path) -> dict[str, Any]:
    cmd = [
        "pandoc",
        "-f",
        PANDOC_MARKDOWN_FORMAT,
        "-t",
        "json",
    ]
    if TOC_LUA_FILTER.exists():
        cmd += ["--metadata", f"build-profile={BUILD_PROFILE}"]
        cmd += ["--lua-filter", str(TOC_LUA_FILTER)]
    cmd.append(str(path))
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Pandoc failed for {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


@lru_cache(maxsize=None)
def load_document_blocks(rel_path: str) -> list[Any] | None:
    file_path = ROOT / rel_path
    if not file_path.exists():
        return None
    try:
        data = run_pandoc_json(file_path)
    except RuntimeError:
        return None
    return data.get("blocks", [])


# Regex to match toc-nesting-N class (e.g., toc-nesting-1, toc-nesting-2)
# Also supports legacy underscore format (toc_nesting_N) for backwards compatibility
TOC_NESTING_CLASS_RE = re.compile(r"^toc[-_]nesting[-_](\d+)$")


@dataclass
class TocDivOverrides:
    """Per-file TOC overrides extracted from outer div classes."""
    nesting_level: int | None = None  # .toc-nesting-N
    no_subtitle: bool = False  # .no-subtitle


def extract_toc_div_overrides(rel_path: str) -> TocDivOverrides:
    """Extract per-file TOC overrides from outer div classes.
    
    Looks for classes on the outermost Div wrapper:
    - `.toc-nesting-N` (or legacy `.toc_nesting_N`): Override max nesting level
    - `.no-subtitle`: Suppress subtitle display in TOC
    
    Example: `::: {.appendix .toc-nesting-0 .no-subtitle}`
    
    Args:
        rel_path: Relative path to the markdown file
        
    Returns:
        TocDivOverrides with extracted settings
    """
    overrides = TocDivOverrides()
    
    blocks = load_document_blocks(rel_path)
    if not blocks:
        return overrides
    
    # Check first block for outer Div wrapper
    first_block = blocks[0] if blocks else None
    if not first_block or first_block.get("t") != "Div":
        return overrides
    
    # Div structure: {"t": "Div", "c": [[id, classes, attrs], content]}
    attrs = first_block.get("c", [])
    if len(attrs) < 2:
        return overrides
    
    attr_tuple = attrs[0]
    if len(attr_tuple) < 2:
        return overrides
    
    classes = attr_tuple[1]  # List of class names
    for cls in classes:
        # Check for toc-nesting-N or toc_nesting_N
        match = TOC_NESTING_CLASS_RE.match(cls)
        if match:
            level = int(match.group(1))
            # Clamp to valid range 0-3 (0 = H1 only, 1 = H2+, 2 = H3+, 3 = H4+)
            overrides.nesting_level = max(0, min(3, level))
        # Check for no-subtitle
        elif cls == "no-subtitle":
            overrides.no_subtitle = True
    
    return overrides


def extract_toc_nesting_override(rel_path: str) -> int | None:
    """Extract per-file TOC nesting level override from outer div classes.
    
    Convenience wrapper around extract_toc_div_overrides() for nesting only.
    """
    return extract_toc_div_overrides(rel_path).nesting_level


def ensure_directory_tags() -> None:
    if not TAGGER.exists():
        return
    print("-- Updating semantic wrappers via tag_by_dir.py")
    subprocess.run([sys.executable, str(TAGGER)], check=True)


def stringify_inlines(inlines: list[Any]) -> str:
    parts: list[str] = []

    def walk(nodes: Iterable[Any]) -> None:
        for node in nodes:
            node_type = node["t"]
            if node_type == "Str":
                parts.append(node["c"])
            elif node_type == "Space":
                parts.append(" ")
            elif node_type in {"SoftBreak", "LineBreak"}:
                parts.append(" ")
            elif node_type in {"Emph", "Strong", "Underline", "Strikeout", "Superscript", "Subscript", "SmallCaps"}:
                walk(node["c"])
            elif node_type == "Code":
                parts.append(node["c"][1])
            elif node_type == "Quoted":
                parts.append("\"")
                walk(node["c"][1])
                parts.append("\"")
            elif node_type == "Span":
                walk(node["c"][2])
            elif node_type == "Cite":
                walk(node["c"][1])
            elif node_type in {"Link", "Image"}:
                walk(node["c"][1])

    walk(inlines)
    return "".join(parts).strip()


def attr_to_map(attr: list[Any]) -> dict[str, Any]:
    identifier, classes, kv_pairs = attr
    data: dict[str, Any] = {}
    if identifier:
        data["id"] = identifier
    if classes:
        data["classes"] = classes
    for key, value in kv_pairs:
        data[key] = value
    return data


def collect_semantic_tokens(attr_map: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()

    classes = attr_map.get("classes")
    if classes:
        tokens.update(cls.strip() for cls in classes if cls.strip())

    value = attr_map.get("epub:type")
    if value:
        tokens.update(token.strip() for token in value.split() if token.strip())

    return tokens


def collect_headings(
    blocks: list[Any],
    sink: list[dict[str, Any]],
    context_tokens: set[str] | None = None,
    context_state: dict[str, Any] | None = None,
) -> None:
    if context_state is None:
        context_state = {
            "sidebar_active": False,
            "sidebar_count": 0,
            "note_active": False,
            "note_count": 0,
        }
    for block in blocks:
        block_type = block["t"]
        if block_type == "Header":
            header = dict(block)
            header["context_tokens"] = sorted(context_tokens or [])
            if context_state.get("sidebar_active"):
                header["prefix_once_sidebar"] = context_state.get("sidebar_count", 0) == 0
                context_state["sidebar_count"] = context_state.get("sidebar_count", 0) + 1
            if context_state.get("note_active"):
                header["prefix_once_note"] = context_state.get("note_count", 0) == 0
                context_state["note_count"] = context_state.get("note_count", 0) + 1
            sink.append(header)
        elif block_type == "Div":
            attrs = attr_to_map(block["c"][0])
            tokens = collect_semantic_tokens(attrs)
            merged = set(context_tokens or [])
            merged.update(tokens)
            next_state = dict(context_state)
            if {"sidebar", "sidebar-inline", "aside"} & tokens:
                next_state["sidebar_active"] = True
                next_state["sidebar_count"] = 0
            if "note" in tokens:
                next_state["note_active"] = True
                next_state["note_count"] = 0
            collect_headings(block["c"][1], sink, merged, next_state)
        elif block_type in {"BlockQuote", "Note"}:
            collect_headings(block["c"], sink, context_tokens, context_state)
        elif block_type in {"BulletList", "OrderedList"}:
            items = block["c"][1] if block_type == "OrderedList" else block["c"]
            for item in items:
                collect_headings(item, sink, context_tokens, context_state)
        elif block_type == "DefinitionList":
            for _, defs in block["c"]:
                for definition in defs:
                    collect_headings(definition, sink, context_tokens, context_state)


def extract_part_headings(rel_path: str) -> dict[str, str | None]:
    file_path = ROOT / rel_path
    headings_info = {
        "toc_title": None,
        "part_title": None,
        "part_subtitle": None,
    }
    blocks = load_document_blocks(rel_path)
    if not blocks:
        return headings_info
    if blocks and blocks[0]["t"] == "Div":
        attrs = attr_to_map(blocks[0]["c"][0])
        classes = attrs.get("classes", [])
        if classes and any(cls == "part" for cls in classes):
            blocks = blocks[0]["c"][1]

    headings: list[dict[str, Any]] = []
    collect_headings(blocks, headings)

    for header in headings:
        level, _attrs, inline = header["c"]
        text = normalize_whitespace(stringify_inlines(inline))
        if not text:
            continue
        if headings_info["toc_title"] is None:
            headings_info["toc_title"] = text
            continue
        if headings_info["part_title"] is None:
            headings_info["part_title"] = text
            continue
        if headings_info["part_subtitle"] is None:
            headings_info["part_subtitle"] = text
            break

    return headings_info


def write_part_meta_file(entries: OrderedDict[str, dict[str, str]]) -> None:
    payload = {
        "_comment": "Auto-generated from parts/ markdown. Do not edit manually.",
        "series": list(entries.values()),
    }
    PART_META_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def derive_part_meta(order: list[str]) -> OrderedDict[str, dict[str, str]]:
    entries: OrderedDict[str, dict[str, str]] = OrderedDict()
    for rel_path in order:
        if not rel_path.startswith("parts/"):
            continue
        part_id = part_id_from_path(rel_path)
        if not part_id:
            continue
        headings = extract_part_headings(rel_path)
        toc_title = headings["toc_title"] or PART_FALLBACK_TEMPLATE.format(part_id=part_id)
        part_title = headings["part_title"] or ""
        part_subtitle = headings["part_subtitle"] or ""
        entries[part_id] = {
            "id": part_id,
            "toc_title": toc_title,
            "part_title": part_title,
            "part_subtitle": part_subtitle,
            "part_file": rel_path,
        }
    if not entries:
        raise RuntimeError("No series part wrappers defined in book-order.txt")
    write_part_meta_file(entries)
    return entries


# Part/series code regex - configurable pattern for parsing chapter codes like "A1", "B2" etc.
# Default pattern matches Series letter + chapter number (e.g., "A1. Title" or "B2 — Subtitle")
_DEFAULT_SERIES_CODE_PATTERN = r"^([A-D])(\d+)(?:[.\-—|:]\s*|\s+)(.+)$"
SERIES_CODE_RE = re.compile(
    _config_str(PARTS_SETTINGS.get("code_pattern"), _DEFAULT_SERIES_CODE_PATTERN)
)

APPENDIX_RE = re.compile(r"^Appendix\s+([A-Z0-9]+)\s*[—\-:|]\s*(.+)$", re.IGNORECASE)

# Pattern for extracting part ID from filename (e.g., "SERIES A" → "A", or "Part 1" → "1")
_DEFAULT_PART_ID_PATTERN = r"SERIES\s+([A-D])"
PART_ID_FROM_FILENAME = re.compile(
    _config_str(PARTS_SETTINGS.get("id_from_filename_pattern"), _DEFAULT_PART_ID_PATTERN),
    re.IGNORECASE,
)

# Pattern for identifying part header lines in chapter files (to skip in outline extraction)
_DEFAULT_PART_HEADER_PATTERN = r"^SERIES\s+[A-D]\s*[—\-]\s*PART\s+\d+"
PART_HEADER_RE = re.compile(
    _config_str(PARTS_SETTINGS.get("header_pattern"), _DEFAULT_PART_HEADER_PATTERN),
    re.IGNORECASE,
)

BRIDGE_PREFIX_RE = re.compile(r"^(?:INTER\s*SERIES\s+)?BRIDGE(?:HEAD)?\s*[—\-:|]\s*", re.IGNORECASE)
# Accept plain decimals (e.g., 2.3.1) and prefixes such as DF1-1.2 or DF1.1.2
NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?P<number>(?:[A-Za-z]+[A-Za-z0-9]*[\-–—.]\d+(?:[.\-–—]\d+)*|\d+(?:[.\-–—]\d+)*))"
    r"(?P<separator>[\s.\-–—:)]{1,10})(?P<title>.+)$"
)
ROMAN_OUTLINE_RE = re.compile(r"^(?P<roman>[IVXLCDM]+)\.?\s+(?P<title>.+)$")
ROMAN_NUMBER_RE = re.compile(r"^[IVXLCDM]+\.?$")


def normalize_number_suffix(value: str | None) -> str:
    if not value:
        return ""
    candidate = value.strip()
    if candidate in {".", ")"}:
        return candidate
    if candidate.lower() in {"period", "dot"}:
        return "."
    if candidate.lower() in {"paren", "parenthesis", "right-paren", "rparen"}:
        return ")"
    return ""


def merge_settings(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if overrides and isinstance(overrides, dict):
        merged.update(overrides)
    return merged


def build_expanded_options(
    settings: dict[str, Any],
    *,
    defaults: ExpandedTocOptions | None = None,
) -> ExpandedTocOptions:
    return ExpandedTocOptions(
        enabled=_config_bool(settings.get("enabled"), defaults.enabled if defaults else TOC_EXPANDED_ENABLED),
        include_unnumbered=_config_bool(
            settings.get("include_unnumbered"),
            defaults.include_unnumbered if defaults else TOC_EXPANDED_INCLUDE_UNNUMBERED,
        ),
        skip_single_letter=_config_bool(
            settings.get("skip_single_letter"),
            defaults.skip_single_letter if defaults else TOC_EXPANDED_SKIP_SINGLE_LETTER,
        ),
        number_suffix=_config_str(
            settings.get("number_suffix"),
            defaults.number_suffix if defaults else TOC_EXPANDED_NUMBER_SUFFIX,
        ),
        promote_orphaned_headings=_config_bool(
            settings.get("promote_orphaned_headings"),
            defaults.promote_orphaned_headings if defaults else TOC_EXPANDED_PROMOTE_ORPHANED,
        ),
        separator_before_block=_config_bool(
            settings.get("separator_before_block_prefix"),
            defaults.separator_before_block if defaults else TOC_EXPANDED_SEPARATOR_BEFORE_BLOCK,
        ),
        unnumbered_style=_config_str(
            settings.get("unnumbered_style"),
            defaults.unnumbered_style if defaults else TOC_EXPANDED_UNNUMBERED_STYLE,
        )
        or TOC_EXPANDED_UNNUMBERED_STYLE,
        roman_end_marker=_config_str(
            settings.get("roman_end_marker"),
            defaults.roman_end_marker if defaults else TOC_EXPANDED_ROMAN_END_MARKER,
        ),
        max_nesting_level=_config_int(
            settings.get("max_nesting_level"),
            defaults.max_nesting_level if defaults else TOC_EXPANDED_MAX_NESTING,
            minimum=1,
            maximum=6,
        ),
        include_level1=_config_bool(
            settings.get("include_level1"),
            defaults.include_level1 if defaults else False,
        ),
        render_depth0_as_heading=_config_bool(
            settings.get("render_depth0_as_heading"),
            defaults.render_depth0_as_heading if defaults else False,
        ),
    )


def resolve_block_heading_prefix(tokens: set[str]) -> str | None:
    if not tokens:
        return None
    sidebar_prefix = _config_str(TOC_EXPANDED_BLOCK_PREFIXES.get("sidebar"), None)
    note_prefix = _config_str(TOC_EXPANDED_BLOCK_PREFIXES.get("note"), None)
    if sidebar_prefix:
        sidebar_tokens = {"sidebar", "sidebar-inline", "aside"}
        if not sidebar_tokens.isdisjoint(tokens):
            return sidebar_prefix
    if note_prefix and "note" in tokens:
        variant_label = None
        if TOC_EXPANDED_NOTE_VARIANTS:
            for key, value in TOC_EXPANDED_NOTE_VARIANTS.items():
                if key in tokens:
                    variant_label = _config_str(value, None)
                    if variant_label:
                        break
        else:
            excluded = {"note", "sidebar", "sidebar-inline", "aside"}
            candidates = sorted(token for token in tokens if token not in excluded)
            if candidates:
                variant_label = candidates[0].replace("-", " ").title()
        if variant_label:
            return f"{variant_label} {note_prefix}"
        return note_prefix
    return None


def apply_block_heading_prefix(title: str, tokens: set[str], *, allow_prefix: bool = True) -> str:
    if not allow_prefix:
        return title
    prefix = resolve_block_heading_prefix(tokens)
    if not prefix:
        return title
    spacer = " " if not prefix.endswith(" ") else ""
    return f"{prefix}{spacer}{title}"


def block_prefix_matches(label: str) -> bool:
    if not label:
        return False
    prefixes = [
        _config_str(TOC_EXPANDED_BLOCK_PREFIXES.get("sidebar"), None),
        _config_str(TOC_EXPANDED_BLOCK_PREFIXES.get("note"), None),
    ]
    for prefix in prefixes:
        if prefix and label.startswith(prefix.strip()):
            return True
    return False


def normalize_whitespace(text: str | None) -> str | None:
    if text is None:
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed or None


# Regex patterns for extracting inline sidebar titles
# Matches ::: {.sidebar ...} or ::: sidebar... blocks and extracts the first heading
INLINE_SIDEBAR_START_RE = re.compile(
    r"^:::(?:\s*\{[^}]*\.sidebar[^}]*\}|\s+sidebar\b)",
    re.IGNORECASE
)
INLINE_SIDEBAR_END_RE = re.compile(r"^:::\s*$")
# Matches H1-H6 headings: ### **Title** or ### Title
INLINE_SIDEBAR_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:\*\*(.+?)\*\*|(.+))\s*$"
)


def extract_inline_sidebar_titles(rel_path: str) -> list[str]:
    """Extract titles from inline sidebar blocks within a file.
    
    Inline sidebars are ::: {.sidebar} blocks with a bold heading.
    Returns a list of sidebar titles found in the file.
    """
    abs_path = ROOT / rel_path
    if not abs_path.exists():
        return []
    
    try:
        content = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    
    titles: list[str] = []
    in_sidebar = False
    found_heading = False
    
    for line in content.splitlines():
        if INLINE_SIDEBAR_START_RE.match(line):
            in_sidebar = True
            found_heading = False
            continue
        
        if in_sidebar:
            if INLINE_SIDEBAR_END_RE.match(line):
                in_sidebar = False
                continue
            
            # Only look for heading if we haven't found one yet for this sidebar
            if not found_heading:
                heading_match = INLINE_SIDEBAR_HEADING_RE.match(line.strip())
                if heading_match:
                    # Group 1: ### **Title**, Group 2: ### Title
                    title = heading_match.group(1) or heading_match.group(2)
                    if title:
                        titles.append(normalize_whitespace(title) or title)
                        found_heading = True
    
    return titles


# Regex pattern for extracting sidebar include directive paths
# Matches ::: {.include path="sidebars/..."} directives
INCLUDE_SIDEBAR_RE = re.compile(
    r'^:::.*\.include.*path\s*=\s*["\']([^"\']*sidebars/[^"\']+)["\']',
    re.IGNORECASE
)


def extract_included_sidebar_titles(rel_path: str) -> list[str]:
    """Extract titles from sidebar files referenced via include directives.
    
    Scans for ::: {.include path="sidebars/..."} directives and extracts
    the title from each referenced sidebar file.
    Returns a list of sidebar titles found.
    """
    abs_path = ROOT / rel_path
    if not abs_path.exists():
        return []
    
    try:
        content = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    
    titles: list[str] = []
    
    for line in content.splitlines():
        match = INCLUDE_SIDEBAR_RE.match(line.strip())
        if match:
            sidebar_path = match.group(1)
            # Get the title from the referenced sidebar file
            meta = infer_document_meta(sidebar_path)
            if meta.title:
                titles.append(normalize_whitespace(meta.title) or meta.title)
    
    return titles


# Regex pattern for detecting ::: {.note ...} or ::: note... block start (with any variant classes)
INLINE_NOTE_START_RE = re.compile(
    r"^:::(?:.*\{\s*\.note\b|\s+note\b)",
    re.IGNORECASE
)
# End of a fenced div block
INLINE_NOTE_END_RE = re.compile(r'^:::$')
# Pattern for extracting a heading from within a note block
# Matches H1-H6 headings: ### **Title** or ### Title
INLINE_NOTE_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:\*\*(.+?)\*\*|(.+))\s*$"
)


def extract_inline_note_titles(rel_path: str) -> list[str]:
    """Extract titles from inline note blocks within a file.
    
    Inline notes are ::: {.note} or ::: {.note.variant} blocks with a bold heading.
    Returns a list of note titles found in the file.
    """
    abs_path = ROOT / rel_path
    if not abs_path.exists():
        return []
    
    try:
        content = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    
    titles: list[str] = []
    in_note = False
    found_heading = False
    
    for line in content.splitlines():
        if INLINE_NOTE_START_RE.match(line):
            in_note = True
            found_heading = False
            continue
        
        if in_note:
            if INLINE_NOTE_END_RE.match(line):
                in_note = False
                continue
            
            # Only look for heading if we haven't found one yet for this note
            if not found_heading:
                heading_match = INLINE_NOTE_HEADING_RE.match(line.strip())
                if heading_match:
                    # Group 1: ### **Title**, Group 2: ### Title
                    title = heading_match.group(1) or heading_match.group(2)
                    if title:
                        titles.append(normalize_whitespace(title) or title)
                        found_heading = True
    
    return titles


# Regex pattern for extracting note include directive paths
# Matches ::: {.include path="notes/..."} directives
INCLUDE_NOTE_RE = re.compile(
    r'^:::.*\.include.*path\s*=\s*["\']([^"\']*notes/[^"\']+)["\']',
    re.IGNORECASE
)


def extract_included_note_titles(rel_path: str) -> list[str]:
    """Extract titles from note files referenced via include directives.
    
    Scans for ::: {.include path="notes/..."} directives and extracts
    the title from each referenced note file.
    Returns a list of note titles found.
    """
    abs_path = ROOT / rel_path
    if not abs_path.exists():
        return []
    
    try:
        content = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    
    titles: list[str] = []
    
    for line in content.splitlines():
        match = INCLUDE_NOTE_RE.match(line.strip())
        if match:
            note_path = match.group(1)
            # Get the title from the referenced note file
            meta = infer_document_meta(note_path)
            if meta.title:
                titles.append(normalize_whitespace(meta.title) or meta.title)
    
    return titles


def split_code_from_title(text: str) -> tuple[str | None, str]:
    appendix_match = APPENDIX_RE.match(text)
    if appendix_match:
        return None, text

    series_match = SERIES_CODE_RE.match(text)
    if series_match:
        letter, number, rest = series_match.groups()
        code = f"{letter}{number}."
        return code, rest.strip()

    return None, text


def strip_bridge_prefix(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = BRIDGE_PREFIX_RE.sub("", text).strip()
    return cleaned or text


def split_numbered_heading(text: str) -> tuple[str, str] | None:
    match = NUMBERED_HEADING_PATTERN.match(text)
    if not match:
        return None
    title = normalize_whitespace(match.group("title"))
    if not title:
        return None
    number = match.group("number").rstrip(".")
    return number, title


def extract_numbered_headings(
    rel_path: str,
    max_nesting_level: int,
    *,
    include_unnumbered: bool = False,
    skip_single_letter: bool = False,
    promote_orphaned_headings: bool = False,
    include_level1: bool = False,
) -> list[NumberedHeading]:
    blocks = load_document_blocks(rel_path)
    if not blocks:
        return []

    headings: list[dict[str, Any]] = []
    collect_headings(blocks, headings)
    outline: list[NumberedHeading] = []
    seen_level2_since_h1 = True
    seen_h1 = False

    for header in headings:
        level, _attrs, inline = header["c"]
        context_tokens = set(header.get("context_tokens") or [])
        allow_prefix = True
        if {"sidebar", "sidebar-inline", "aside"} & context_tokens:
            allow_prefix = bool(header.get("prefix_once_sidebar", False))
        if "note" in context_tokens:
            allow_prefix = allow_prefix and bool(header.get("prefix_once_note", False))
        if level == 1:
            if not seen_h1:
                seen_h1 = True
                seen_level2_since_h1 = False
                continue
            seen_level2_since_h1 = False
            if not include_level1:
                continue
        elif level == 2:
            seen_level2_since_h1 = True
        if level < 2 and level != 1:
            continue
        if level == 1:
            depth = 0
        else:
            depth = max(1, level - 1)
        if promote_orphaned_headings and level >= 3 and not seen_level2_since_h1:
            depth = 1
        # Filter by max_nesting_level: 0 = only H1 (depth 0), 1 = H2+ (depth 1), etc.
        if depth > max_nesting_level:
            continue
        text = normalize_whitespace(stringify_inlines(inline))
        if not text:
            continue
        split = split_numbered_heading(text)
        if split:
            number, title = split
            title = apply_block_heading_prefix(title, context_tokens, allow_prefix=allow_prefix)
            outline.append(NumberedHeading(depth=depth, number=number, title=title))
            continue
        roman_match = ROMAN_OUTLINE_RE.match(text)
        if roman_match:
            roman = roman_match.group("roman")
            roman_title = roman_match.group("title").strip()
            roman_title = apply_block_heading_prefix(roman_title, context_tokens, allow_prefix=allow_prefix)
            outline.append(NumberedHeading(depth=depth, number=roman, title=roman_title))
            continue
        if include_unnumbered:
            if skip_single_letter and len(text) == 1 and text.isalpha():
                continue
            text = apply_block_heading_prefix(text, context_tokens, allow_prefix=allow_prefix)
            outline.append(NumberedHeading(depth=depth, number="", title=text))

    return outline


def gather_numbered_heading_map(
    order: list[str],
    max_nesting_level: int,
    *,
    include_unnumbered: bool = False,
    skip_single_letter: bool = False,
    promote_orphaned_headings: bool = False,
    include_level1: bool = False,
    use_per_file_overrides: bool = True,
) -> dict[str, list[NumberedHeading]]:
    heading_map: dict[str, list[NumberedHeading]] = {}
    for rel_path in order:
        if not rel_path.endswith(".md"):
            continue
        if not (
            rel_path.startswith("chapters/")
            or rel_path.startswith("appendices/")
            or rel_path.startswith("annexes/")
        ):
            continue
        # Check for per-file nesting level override (e.g., .toc-nesting-1 class)
        effective_nesting = max_nesting_level
        if use_per_file_overrides:
            override = extract_toc_nesting_override(rel_path)
            if override is not None:
                effective_nesting = override
        outline = extract_numbered_headings(
            rel_path,
            effective_nesting,
            include_unnumbered=include_unnumbered,
            skip_single_letter=skip_single_letter,
            promote_orphaned_headings=promote_orphaned_headings,
            include_level1=include_level1,
        )
        if outline:
            heading_map[rel_path] = outline
    return heading_map


def format_heading_outline(
    headings: list[NumberedHeading],
    *,
    separator_before_block: bool = False,
    unnumbered_style: str = "list",
    roman_end_marker: str = "",
    number_suffix: str | None = None,
    number_style: str = "ordered",
    number_prefix: str | None = None,
    render_depth0_as_heading: bool = False,
) -> list[str]:
    lines: list[str] = []
    suffix = normalize_number_suffix(number_suffix)
    prev_kind: str | None = None
    prev_indent: str | None = None
    pending_roman_marker_indent: str | None = None
    
    # Check if first item needs spacing to start a block cleanly
    first_is_roman = False
    first_is_ordered = False
    first_is_unordered = False
    if headings:
        first = headings[0]
        first_num = (first.number or "").strip()
        first_title = (first.title or "").strip()
        if first_num and ROMAN_NUMBER_RE.match(first_num):
            first_is_roman = True
        elif first_num:
            first_is_ordered = True
        elif not first_num and ROMAN_OUTLINE_RE.match(first_title):
            first_is_roman = True
        elif not first_num:
            # Unnumbered heading will be rendered as unordered list if unnumbered_style == "list"
            first_is_unordered = unnumbered_style == "list"
    
    # Add blank line before first list item for proper markdown separation
    if first_is_roman or first_is_ordered or first_is_unordered:
        lines.append("")
    
    for heading in headings:
        indent = "  " * max(heading.depth, 0)
        list_indent = "  " * max(heading.depth, 1)
        number = (heading.number or "").strip()
        title = (heading.title or "").strip()
        is_roman = False
        roman_title = title
        roman_label = ""
        if number and ROMAN_NUMBER_RE.match(number):
            is_roman = True
            clean_number = number.rstrip(".")
            roman_label = clean_number + (suffix if suffix else ".")
        elif not number:
            roman_match = ROMAN_OUTLINE_RE.match(title)
            if roman_match:
                is_roman = True
                roman = roman_match.group("roman")
                roman_title = roman_match.group("title").strip()
                roman_label = roman + (suffix if suffix else ".")
        if pending_roman_marker_indent is not None and not is_roman:
            if indent <= pending_roman_marker_indent:
                if roman_end_marker:
                    if lines and lines[-1] != "":
                        lines.append("")
                    lines.append(f"{pending_roman_marker_indent}{roman_end_marker}")
                pending_roman_marker_indent = None

        if is_roman:
            if prev_kind in ("plain", "unordered") and lines and lines[-1] != "":
                lines.append("")
            if separator_before_block and block_prefix_matches(roman_title):
                if lines and lines[-1] != "":
                    lines.append("")
            lines.append(f"{indent}{roman_label}  {roman_title}")
            prev_kind = "roman"
            prev_indent = indent
            if roman_end_marker:
                pending_roman_marker_indent = indent
            continue
        if number:
            number_label = number
            if suffix and not number.endswith((".", ")")):
                number_label = f"{number}{suffix}"
            if number_style == "appendix" and number_prefix:
                prefix = number_prefix
                if not prefix.endswith("."):
                    prefix = f"{prefix}."
                letters_stripped = re.sub(r"^[A-Za-z]+", "", number)
                numeric_part = letters_stripped.lstrip(". )")
                if numeric_part:
                    number_label = f"{prefix}{numeric_part}"
                else:
                    number_label = f"{prefix}{number}"
            label = f"{number_label} {title}".rstrip()
        else:
            label = title
        if not label.strip():
            continue
        if separator_before_block and block_prefix_matches(label):
            if lines and lines[-1] != "":
                lines.append("")
        if prev_kind == "roman" and lines and lines[-1] != "":
            pass
        is_unnumbered = not number
        # Determine rendering style for unnumbered headings:
        # - "list" style: render as bullet list items (not bold)
        # - "plain" style: render as bold plain text
        # Depth 0 headings are rendered as bold headers if render_depth0_as_heading is True,
        # otherwise they are rendered as list items like other depths
        use_plain = is_unnumbered and (
            (heading.depth == 0 and render_depth0_as_heading) or 
            (heading.depth > 0 and unnumbered_style == "plain")
        )
        if use_plain:
            if heading.depth == 0:
                if lines and lines[-1] != "":
                    lines.append("")
                if render_depth0_as_heading:
                    lines.append(f"### **{label}**")
                else:
                    lines.append(f"**{label}**")
                lines.append("")
                prev_kind = "plain-header"
            elif heading.depth == 1:
                # Add blank line after list items to prevent markdown from treating
                # this indented plain-header as a continuation of the list
                if prev_kind in {"unordered", "ordered"} and lines and lines[-1] != "":
                    lines.append("")
                lines.append(f"{indent}**{label}**  ")
                prev_kind = "plain-header"
            else:
                lines.append(f"{indent}{label}")
                prev_kind = "plain"
            prev_indent = indent
        else:
            if number:
                if number_style == "appendix":
                    if prev_kind in {"plain", "plain-header"} and lines and lines[-1] != "":
                        lines.append("")
                    lines.append(f"{list_indent}- {label}")
                    prev_kind = "unordered"
                else:
                    if prev_kind != "ordered" and lines and lines[-1] != "":
                        lines.append("")
                    lines.append(f"{list_indent}{number_label} {title}")
                    prev_kind = "ordered"
            else:
                if prev_kind in {"plain", "plain-header"} and lines and lines[-1] != "":
                    lines.append("")
                lines.append(f"{list_indent}- {label}")
                prev_kind = "unordered"
            prev_indent = indent
    if pending_roman_marker_indent is not None and roman_end_marker:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"{pending_roman_marker_indent}{roman_end_marker}")
    return lines


def prune_outline_duplicates(
    headings: list[NumberedHeading],
    targets: Iterable[str | None],
) -> list[NumberedHeading]:
    wanted = []
    remaining = {
        normalize_whitespace(target) for target in targets if normalize_whitespace(target)
    }
    for heading in headings:
        if not heading.number:
            title = normalize_whitespace(heading.title)
            if title and title in remaining:
                remaining.remove(title)
                continue
        wanted.append(heading)
    return wanted


@lru_cache(maxsize=None)
def infer_document_meta(path: str) -> TocMeta:
    file_path = ROOT / path
    blocks = load_document_blocks(path)
    if blocks is None:
        return TocMeta(title=file_path.stem.replace("_", " "))
    doc_overrides: dict[str, str] = {}
    working_blocks = blocks

    while working_blocks and len(working_blocks) == 1 and working_blocks[0]["t"] == "Div":
        attrs = attr_to_map(working_blocks[0]["c"][0])
        for key, value in attrs.items():
            if key.startswith("toc-") and key not in doc_overrides:
                doc_overrides[key] = value
        working_blocks = working_blocks[0]["c"][1]

    headings: list[dict[str, Any]] = []
    collect_headings(working_blocks, headings)

    title = normalize_whitespace(doc_overrides.get("toc-title"))
    subtitle = normalize_whitespace(doc_overrides.get("toc-subtitle"))
    code = normalize_whitespace(doc_overrides.get("toc-code"))
    series = normalize_whitespace(doc_overrides.get("toc-series"))

    title_level: int | None = None
    label: str | None = None  # Part header label (e.g., "SERIES A — PART 1")

    for header in headings:
        level, attr_raw, inline = header["c"]
        attr_map = attr_to_map(attr_raw)
        tokens = collect_semantic_tokens(attr_map)
        text = stringify_inlines(inline)
        text = normalize_whitespace(text)
        if not text:
            continue

        if attr_map.get("toc-title"):
            title = normalize_whitespace(attr_map["toc-title"])
        if attr_map.get("toc-subtitle"):
            subtitle = normalize_whitespace(attr_map["toc-subtitle"])
        if attr_map.get("toc-code"):
            code = normalize_whitespace(attr_map["toc-code"])
        if attr_map.get("toc-series"):
            series = normalize_whitespace(attr_map["toc-series"])

        if "toc-title" in tokens:
            title = text
            title_level = level
            continue
        if "toc-subtitle" in tokens:
            subtitle = text
            continue

        # First heading: check if it's a part header label
        if not title and not label and tokens.isdisjoint(EPIGRAPH_TYPES):
            if PART_HEADER_RE.match(text):
                # This is a label like "SERIES A — PART 1", not the title
                label = text
                title_level = level  # Remember this level for finding the actual title
                continue
            else:
                title = text
                title_level = level
                continue

        # If we have a label but no title yet, next same-level heading is the title
        if label and not title and tokens.isdisjoint(EPIGRAPH_TYPES):
            if title_level is not None and level == title_level:
                title = text
                continue

        # Subtitle: next heading at a lower level (e.g., H3 after H2)
        if title and not subtitle and tokens.isdisjoint(EPIGRAPH_TYPES):
            if title_level is not None and level > title_level:
                subtitle = text
                continue

    # If we captured a label, the title and subtitle are now correctly separated
    # label = "SERIES A — PART 1" (part header)
    # title = "Predatory Design" (the actual chapter title)
    # subtitle = H3 if captured (e.g., "How Simple Interfaces Exploit Human Trust")

    if title:
        inferred_code, clean_title = split_code_from_title(title)
        if inferred_code and not code:
            code = inferred_code
        title = clean_title

    return TocMeta(title=title, subtitle=subtitle, code=code, series=series, label=label)


def part_id_from_path(path: str) -> str | None:
    name = Path(path).name
    match = PART_ID_FROM_FILENAME.search(name)
    if match:
        return match.group(1).upper()
    return None


def build_front_entries(order: list[str], front_labels: dict[str, str]) -> list[str]:
    entries: list[str] = []
    for rel_path in order:
        if not rel_path.startswith("front matter/"):
            continue
        if rel_path == TOC_SELF_REL_PATH:
            continue
        label = front_labels.get(rel_path)
        if not label:
            meta = infer_document_meta(rel_path)
            label = meta.title
        label = normalize_whitespace(label)
        if label:
            entries.append(f"**{label}**")
            entries.append("")
    while entries and entries[-1] == "":
        entries.pop()
    return entries


def build_chapter_entries(
    order: list[str],
    chapter_labels: dict[str, tuple[str, str]],
    sidebar_labels: dict[str, str],
    note_labels: dict[str, str],
    part_meta: OrderedDict[str, dict[str, str]],
    annex_source_paths: set[str],
    main_body_paths: set[str],
) -> tuple[
    dict[str, list[dict[str, str | None]]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[dict[str, str]]],
    bool,
    list[str],  # appendix_sidebars
    list[str],  # appendix_notes
]:
    part_keys = list(part_meta.keys())
    chapters: dict[str, list[dict[str, str]]] = {k: [] for k in part_keys}
    sidebars: dict[str, list[str]] = {k: [] for k in part_keys}
    notes: dict[str, list[str]] = {k: [] for k in part_keys}
    bridges: dict[str, list[dict[str, str]]] = {k: [] for k in part_keys}
    appendix_sidebars: list[str] = []
    appendix_notes: list[str] = []
    epilogue_present = False
    current_part: str | None = None
    in_appendix_section = False

    for rel_path in order:
        if rel_path.startswith("parts/"):
            current_part = part_id_from_path(rel_path)
            continue

        if rel_path.startswith("chapters/"):
            if rel_path in TOC_EPILOGUE_PATHS or Path(rel_path).name in TOC_EPILOGUE_FILENAMES:
                epilogue_present = True

            if rel_path in chapter_labels:
                code, title = chapter_labels[rel_path]
                meta = TocMeta(title=title, subtitle=None, code=code)
            else:
                meta = infer_document_meta(rel_path)

            meta.title = normalize_whitespace(meta.title)
            meta.subtitle = normalize_whitespace(meta.subtitle)
            meta.code = normalize_whitespace(meta.code)
            meta.label = normalize_whitespace(meta.label) if meta.label else None

            part_id = (
                meta.series
                or (meta.code[0] if meta.code else None)
                or current_part
                or part_id_from_path(rel_path)
            )
            if not part_id or part_id not in chapters:
                continue

            display = meta.title or Path(rel_path).stem
            code = meta.code
            if code and not code.endswith((".", ":")):
                code = f"{code.rstrip('.')}."

            entry = {
                "code": code,
                "title": display,
                "subtitle": meta.subtitle,
                "label": meta.label,  # Part header label (e.g., "SERIES A — PART 1")
                "path": rel_path,
            }
            chapters[part_id].append(entry)
            
            # Collect sidebars referenced via include directives
            if TOC_COLLECT_SIDEBARS in ("include", "inline") and part_id in sidebars:
                for included_title in extract_included_sidebar_titles(rel_path):
                    sidebars[part_id].append(f" • {included_title}")
            # Collect inline sidebars from this chapter
            if TOC_COLLECT_SIDEBARS == "inline" and part_id in sidebars:
                for inline_title in extract_inline_sidebar_titles(rel_path):
                    sidebars[part_id].append(f" • {inline_title}")
            # Collect notes referenced via include directives
            if TOC_COLLECT_NOTES in ("include", "inline") and part_id in notes:
                for included_title in extract_included_note_titles(rel_path):
                    notes[part_id].append(f" • {included_title}")
            # Collect inline notes from this chapter
            if TOC_COLLECT_NOTES == "inline" and part_id in notes:
                for inline_title in extract_inline_note_titles(rel_path):
                    notes[part_id].append(f" • {inline_title}")
            continue

        if rel_path.startswith(("bridges/", "bridgeheads/")):
            meta = infer_document_meta(rel_path)
            part_id = current_part or part_id_from_path(rel_path)
            if not part_id or part_id not in bridges:
                continue
            display = normalize_whitespace(meta.title) or Path(rel_path).stem.replace("_", " ")
            display = strip_bridge_prefix(display)
            entry = {
                "title": display,
                "subtitle": normalize_whitespace(meta.subtitle),
            }
            bridges[part_id].append(entry)
            continue

        if rel_path.startswith("appendices/"):
            in_appendix_section = True
            # Skip sidebar collection for appendices that belong to annexes
            if normalize_path(rel_path).lower() in annex_source_paths:
                continue
            # Collect sidebars referenced via include directives
            if TOC_COLLECT_SIDEBARS in ("include", "inline"):
                for included_title in extract_included_sidebar_titles(rel_path):
                    appendix_sidebars.append(f" • {included_title}")
            # Collect inline sidebars from this appendix
            if TOC_COLLECT_SIDEBARS == "inline":
                for inline_title in extract_inline_sidebar_titles(rel_path):
                    appendix_sidebars.append(f" • {inline_title}")
            # Collect notes referenced via include directives
            if TOC_COLLECT_NOTES in ("include", "inline"):
                for included_title in extract_included_note_titles(rel_path):
                    appendix_notes.append(f" • {included_title}")
            # Collect inline notes from this appendix
            if TOC_COLLECT_NOTES == "inline":
                for inline_title in extract_inline_note_titles(rel_path):
                    appendix_notes.append(f" • {inline_title}")
            continue

        if rel_path.startswith("sidebars/"):
            # Skip if sidebar collection is disabled
            if TOC_COLLECT_SIDEBARS == "none":
                continue
            # Only include sidebars that appear in the main body order (not annex-only)
            if normalize_path(rel_path).lower() not in main_body_paths:
                continue
            label = sidebar_labels.get(rel_path)
            if not label:
                meta = infer_document_meta(rel_path)
                label = meta.title
            label = normalize_whitespace(label)
            if in_appendix_section:
                # Sidebars appearing after first appendix go to appendix sidebar section
                if label:
                    appendix_sidebars.append(f" • {label}")
            else:
                part_id = current_part or part_id_from_path(rel_path) or "B"
                if label and part_id in sidebars:
                    sidebars[part_id].append(f" • {label}")

        if rel_path.startswith("notes/"):
            # Skip if note collection is disabled
            if TOC_COLLECT_NOTES == "none":
                continue
            # Only include notes that appear in the main body order (not annex-only)
            if normalize_path(rel_path).lower() not in main_body_paths:
                continue
            label = note_labels.get(rel_path)
            if not label:
                meta = infer_document_meta(rel_path)
                label = meta.title
            label = normalize_whitespace(label)
            if in_appendix_section:
                # Notes appearing after first appendix go to appendix note section
                if label:
                    appendix_notes.append(f" • {label}")
            else:
                part_id = current_part or part_id_from_path(rel_path) or "B"
                if label and part_id in notes:
                    notes[part_id].append(f" • {label}")

    return chapters, sidebars, notes, bridges, epilogue_present, appendix_sidebars, appendix_notes


def build_appendix_entries(
    order: list[str],
    appendix_labels: dict[str, str],
    annex_source_paths: set[str],
) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    for rel_path in order:
        if normalize_path(rel_path).lower() in annex_source_paths:
            continue
        if not rel_path.startswith("appendices/"):
            continue
        label = appendix_labels.get(rel_path)
        meta = None
        stem_label = Path(rel_path).stem.replace("_", " ")
        fallback_code = None
        fallback_title = stem_label
        if not label:
            meta = infer_document_meta(rel_path)
            if fallback_code and not meta.code:
                meta.code = fallback_code
                if fallback_title:
                    meta.title = fallback_title
            title = meta.title or fallback_title or Path(rel_path).stem.replace("_", " ")
            if meta.code:
                label = f"{meta.code} {title}" if title else meta.code
            else:
                label = title
        label = normalize_whitespace(label)
        if label:
            if meta is None:
                meta = infer_document_meta(rel_path)
            entries.append(
                {
                    "label": label,
                    "subtitle": normalize_whitespace(meta.subtitle),
                    "path": rel_path,
                }
            )
    return entries


def build_annex_entries(
    order: list[str],
    annex_labels: dict[str, str],
    annex_source_paths: set[str],
) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    for rel_path in order:
        if not (
            rel_path.startswith("annexes/")
            or normalize_path(rel_path).lower() in annex_source_paths
        ):
            continue
        label = annex_labels.get(rel_path)
        meta = None
        stem_label = Path(rel_path).stem.replace("_", " ")
        fallback_title = stem_label
        if not label:
            meta = infer_document_meta(rel_path)
            title = meta.title or fallback_title or Path(rel_path).stem.replace("_", " ")
            if meta.code:
                label = f"{meta.code} {title}" if title else meta.code
            else:
                label = title
        label = normalize_whitespace(label)
        if label:
            if meta is None:
                meta = infer_document_meta(rel_path)
            entries.append(
                {
                    "label": label,
                    "subtitle": normalize_whitespace(meta.subtitle),
                    "path": rel_path,
                }
            )
    return entries


def render_toc(
    order: list[str],
    front_labels: dict[str, str],
    chapter_labels: dict[str, tuple[str, str]],
    sidebar_labels: dict[str, str],
    note_labels: dict[str, str],
    appendix_labels: dict[str, str],
    annex_labels: dict[str, str],
    annex_source_paths: set[str],
    annex_summaries: list[dict[str, str | None]],
    part_meta: OrderedDict[str, dict[str, str]],
    *,
    max_depth: int,
    include_appendices: bool,
    include_annexes_section: bool,
    heading_map: dict[str, list[NumberedHeading]],
    expanded_options: ExpandedTocOptions,
    main_body_paths: set[str],
) -> str:
    front_entries = build_front_entries(order, front_labels)
    chapter_entries, sidebar_entries, note_entries, bridge_entries, has_epilogue, appendix_sidebars, appendix_notes = build_chapter_entries(
        order, chapter_labels, sidebar_labels, note_labels, part_meta, annex_source_paths, main_body_paths
    )
    appendix_entries = build_appendix_entries(order, appendix_labels, annex_source_paths)
    annex_entries = build_annex_entries(order, annex_labels, annex_source_paths)

    lines: list[str] = []
    if TOC_RUNNING_HEADER_LABEL:
        lines.append("---")
        lines.append(f'header-left: "{TOC_RUNNING_HEADER_LABEL}"')
        lines.append(f'header-right: "{TOC_RUNNING_HEADER_LABEL}"')
        lines.append("---\n")
    div_tokens = [".frontmatter", ".toc"]
    if TOC_RUNNING_HEADER_LABEL:
        safe_label = TOC_RUNNING_HEADER_LABEL.replace('"', "'")
        div_tokens.append(f'data-running-head="{safe_label}"')
    lines.append(f"::: {{{' '.join(div_tokens)}}}")
    if TOC_HEADING_TITLE:
        lines.append(f"# **{TOC_HEADING_TITLE}**\n")
    if TOC_HEADING_SUBTITLE:
        lines.append(f"### *{TOC_HEADING_SUBTITLE}*\n")
    lines.append("------\n")

    show_front_entries = max_depth >= 2
    show_chapter_entries = max_depth >= 2
    show_details = max_depth >= 3

    lines.append(f"## **{TOC_FRONTMATTER_LABEL}**\n")
    if show_front_entries and front_entries:
        lines.extend(front_entries)
        lines.append("")
    lines.append("\n------\n")

    def _extend_chapter_outline(formatted: list[str]) -> None:
        """Extend lines with formatted outline content."""
        if not formatted:
            return
        # Add blank line before list items for proper markdown list separation
        if _line_is_list_item(formatted[0]) and lines and lines[-1] != "":
            lines.append("")
        lines.extend(formatted)

    for part_key, meta in part_meta.items():
        lines.append(f"## **{meta['toc_title']}**\n")
        if show_chapter_entries:
            for entry in chapter_entries[part_key]:
                code = entry["code"]
                title_text = entry["title"]
                label = entry.get("label")  # Part header label (e.g., "SERIES A — PART 1")
                entry_path = entry.get("path")
                
                # Check for per-file overrides (.no-subtitle, etc.)
                overrides = extract_toc_div_overrides(entry_path) if entry_path else TocDivOverrides()
                
                if label:
                    # This is a part header entry with label, title, and optional subtitle
                    # Format label for display
                    display_label = label
                    display_label = re.sub(r"^(SERIES\s+[A-D])\s+—\s+", r"\1, ", display_label)
                    display_label = re.sub(r"(PART\s+\d+)\b", r"\1 —", display_label, count=1)
                    
                    # Combine label and title for the entry label
                    combined_label = f"{display_label} {title_text}"
                    
                    config = TocEntryConfig(
                        label=combined_label,
                        subtitle=entry["subtitle"] if show_details else None,
                        path=entry_path,
                        number_style="plain",
                        suppress_subtitle=overrides.no_subtitle,
                    )
                    render_single_entry(
                        config,
                        lines=lines,
                        heading_map=heading_map,
                        expanded_options=expanded_options,
                        extend_outline=_extend_chapter_outline,
                        prune_extra_texts=[entry.get("title"), label],  # Prune original label and title
                    )
                else:
                    # Regular chapter entry (no part header label)
                    entry_label = f"{code} {title_text}" if code else title_text
                    
                    config = TocEntryConfig(
                        label=entry_label,
                        subtitle=entry["subtitle"] if show_details else None,
                        path=entry_path,
                        number_style="plain",
                        suppress_subtitle=overrides.no_subtitle,
                    )
                    render_single_entry(
                        config,
                        lines=lines,
                        heading_map=heading_map,
                        expanded_options=expanded_options,
                        extend_outline=_extend_chapter_outline,
                        prune_extra_texts=[entry.get("title")],
                    )
                lines.append("")
        if show_details and sidebar_entries[part_key]:
            lines.append("**Sidebars**")
            lines.extend(sidebar_entries[part_key])
            lines.append("")
        if show_details and bridge_entries[part_key]:
            for bridge in bridge_entries[part_key]:
                heading_title = bridge["title"] or "Bridge"
                bridge_label = f"Bridge — {heading_title}" if bridge["title"] else "Bridge"
                bridge_path = bridge.get("path")
                
                # Check for per-file overrides
                bridge_overrides = extract_toc_div_overrides(bridge_path) if bridge_path else TocDivOverrides()
                
                config = TocEntryConfig(
                    label=bridge_label,
                    subtitle=bridge["subtitle"],
                    path=bridge_path,
                    number_style="plain",
                    suppress_subtitle=bridge_overrides.no_subtitle,
                )
                # Bridges don't have outline expansion
                disabled_options = dataclass_replace(expanded_options, enabled=False)
                render_single_entry(
                    config,
                    lines=lines,
                    heading_map=heading_map,
                    expanded_options=disabled_options,
                    extend_outline=lambda _: None,
                )
                lines.append("")
        lines.append("\n------\n")

    if has_epilogue and TOC_EPILOGUE_LABEL:
        lines.append(f"## **{TOC_EPILOGUE_LABEL}**\n")
        lines.append("\n------\n")

    def _extend_outline(outline_lines: list[str]) -> None:
        if not outline_lines:
            return
        if _line_is_list_item(outline_lines[0]) and lines and lines[-1] != "":
            lines.append("")
        lines.extend(outline_lines)

    def _render_annexes() -> None:
        if not (include_annexes_section and ANNEX_INCLUDE_IN_TOC and annex_entries):
            return

        def annex_config_factory(entry: dict[str, Any]) -> TocEntryConfig:
            return TocEntryConfig(
                label=entry.get("label", ""),
                subtitle=entry.get("subtitle"),
                path=entry.get("path"),
                number_style="ordered",
                filter_empty_outline_lines=True,
            )

        render_entry_section(
            annex_entries,
            TOC_ANNEXES_LABEL,
            lines=lines,
            heading_map=heading_map,
            expanded_options=expanded_options,
            max_depth=max_depth,
            entry_config_factory=annex_config_factory,
            extend_outline=_extend_outline,
        )

    def _render_appendices() -> None:
        if not include_appendices:
            return
        if not appendix_entries:
            # Still render section header even without entries
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"## **{TOC_APPENDICES_LABEL}**")
            return

        def appendix_config_factory(entry: dict[str, Any]) -> TocEntryConfig:
            appendix_code_match = re.search(
                r"\bappendix\s+([A-Z]+)\b", entry.get("label", ""), re.IGNORECASE
            )
            appendix_code = appendix_code_match.group(1).upper() if appendix_code_match else ""
            return TocEntryConfig(
                label=entry.get("label", ""),
                subtitle=entry.get("subtitle"),
                path=entry.get("path"),
                number_style="appendix",
                number_prefix=appendix_code,
            )

        render_entry_section(
            appendix_entries,
            TOC_APPENDICES_LABEL,
            lines=lines,
            heading_map=heading_map,
            expanded_options=expanded_options,
            max_depth=max_depth,
            entry_config_factory=appendix_config_factory,
            extend_outline=_extend_outline,
        )
        # Render appendix sidebars if enabled and present
        if TOC_APPENDIX_SIDEBAR_SECTION and appendix_sidebars:
            lines.append(f"**{TOC_APPENDIX_SIDEBAR_LABEL}**")
            lines.extend(appendix_sidebars)
            lines.append("")
        # Render appendix notes if enabled and present
        if TOC_APPENDIX_NOTE_SECTION and appendix_notes:
            lines.append(f"**{TOC_APPENDIX_NOTE_LABEL}**")
            lines.extend(appendix_notes)
            lines.append("")

    if ANNEX_POSITION_AFTER_APPENDICES:
        _render_appendices()
        _render_annexes()
    else:
        _render_annexes()
        _render_appendices()

    if (not include_annexes_section) and ANNEX_TOC_LINE_ITEM:
        # Ensure blank line before section header for proper markdown separation
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"## **{TOC_ANNEXES_LABEL}**")
        
        # Render each annex using the unified entry renderer
        for annex in annex_summaries:
            config = TocEntryConfig(
                label=annex.get("label", ""),
                subtitle=annex.get("subtitle"),
                path=annex.get("path"),
                number_style="ordered",
            )
            render_single_entry(
                config,
                lines=lines,
                heading_map=heading_map,
                expanded_options=dataclass_replace(expanded_options, enabled=False),
                extend_outline=lambda _: None,
            )
            lines.append("")

    lines.append(":::\n")
    return "\n".join(lines)



def render_annex_toc(
    annex_id: str,
    order: list[str],
    annex_labels: dict[str, str],
    annex_source_paths: set[str],
    *,
    heading_map: dict[str, list[NumberedHeading]],
    expanded_options: ExpandedTocOptions,
    heading_title: str | None,
    running_header: str | None,
) -> str:
    annex_entries = build_annex_entries(order, annex_labels, annex_source_paths)

    lines: list[str] = []

    div_tokens = [".frontmatter", ".toc"]
    if running_header:
        safe_label = running_header.replace('"', "'")
        div_tokens.append(f'data-running-head="{safe_label}"')

    lines.append(f"::: {{{' '.join(div_tokens)}}}")
    if heading_title:
        lines.append(f"# **{heading_title}**\n")
    lines.append("------\n")

    if annex_entries:
        for annex in annex_entries:
            annex_path = annex.get("path")
            # Extract per-file overrides (.toc-nesting-N, .no-subtitle)
            overrides = extract_toc_div_overrides(annex_path) if annex_path else TocDivOverrides()
            
            lines.append(f"**{annex['label']}**")
            if annex["subtitle"] and not overrides.no_subtitle:
                lines.append(f"*{annex['subtitle']}*")
            if expanded_options.enabled:
                outline = heading_map.get(annex_path)
                if outline:
                    lines.append("")
                    # If nesting level is 0, render depth=0 as list items instead of headers
                    render_depth0 = expanded_options.render_depth0_as_heading
                    if overrides.nesting_level is not None and overrides.nesting_level == 0:
                        render_depth0 = False
                    lines.extend(
                        format_heading_outline(
                            outline,
                            separator_before_block=expanded_options.separator_before_block,
                            unnumbered_style=expanded_options.unnumbered_style,
                            roman_end_marker=expanded_options.roman_end_marker or "",
                            number_suffix=expanded_options.number_suffix,
                            render_depth0_as_heading=render_depth0,
                        )
                    )
            lines.append("")

    lines.append(":::\n")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the front-matter and annex TOCs.")
    parser.add_argument(
        "--profile",
        default=None,
        help="Active build profile; controls .profile-only/.standalone-only visibility "
        "(default: $BUILD_PROFILE or 'default').",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


def main(argv: list[str] | None = None) -> None:
    global BUILD_PROFILE
    args = _parse_args(argv)
    if args.profile and args.profile.strip():
        BUILD_PROFILE = args.profile.strip()
        load_document_blocks.cache_clear()

    if not TOC_ENABLED:
        print("-- TOC generation disabled via iasp-config; skipping")
        return

    ensure_directory_tags()
    (
        order,
        front_labels,
        chapter_labels,
        sidebar_labels,
        note_labels,
        appendix_labels,
        annex_labels,
        annex_source_paths,
        annex_entries_by_id,
        annex_source_paths_by_id,
        annex_toc_in_order,
        annex_dir_by_id,
        main_body_paths,
    ) = parse_book_order()

    annex_summaries: list[dict[str, str | None]] = []
    for annex_id, entries in annex_entries_by_id.items():
        if not entries:
            continue
        preferred = None
        for entry in entries:
            if entry.startswith("parts/") or entry.startswith("annexes/"):
                preferred = entry
                break
        target = preferred or entries[0]
        label = annex_labels.get(target)
        meta = None
        if not label:
            meta = infer_document_meta(target)
            label = meta.title
        label = normalize_whitespace(label or "")
        if not label:
            label = Path(target).stem.replace("_", " ")
        if meta is None:
            meta = infer_document_meta(target)
        annex_summaries.append(
            {
                "label": label,
                "subtitle": normalize_whitespace(meta.subtitle),
            }
        )
    part_meta = derive_part_meta(order)
    heading_map: dict[str, list[NumberedHeading]] = {}
    base_expanded_options = ExpandedTocOptions(
        enabled=TOC_EXPANDED_ENABLED,
        include_unnumbered=TOC_EXPANDED_INCLUDE_UNNUMBERED,
        skip_single_letter=TOC_EXPANDED_SKIP_SINGLE_LETTER,
        number_suffix=TOC_EXPANDED_NUMBER_SUFFIX,
        promote_orphaned_headings=TOC_EXPANDED_PROMOTE_ORPHANED,
        separator_before_block=TOC_EXPANDED_SEPARATOR_BEFORE_BLOCK,
        unnumbered_style=TOC_EXPANDED_UNNUMBERED_STYLE,
        roman_end_marker=TOC_EXPANDED_ROMAN_END_MARKER,
        max_nesting_level=TOC_EXPANDED_MAX_NESTING,
        include_level1=False,
        render_depth0_as_heading=False,
    )
    if base_expanded_options.enabled:
        heading_map = gather_numbered_heading_map(
            order,
            base_expanded_options.max_nesting_level,
            include_unnumbered=base_expanded_options.include_unnumbered,
            skip_single_letter=base_expanded_options.skip_single_letter,
            promote_orphaned_headings=base_expanded_options.promote_orphaned_headings,
            include_level1=base_expanded_options.include_level1,
        )
    include_annexes_section = ANNEX_TOC_MODE == "embedded" and not annex_toc_in_order

    toc_md = render_toc(
        order,
        front_labels,
        chapter_labels,
        sidebar_labels,
        note_labels,
        appendix_labels,
        annex_labels,
        annex_source_paths,
        annex_summaries,
        part_meta,
        max_depth=TOC_MAX_DEPTH,
        include_appendices=TOC_INCLUDE_APPENDICES,
        include_annexes_section=include_annexes_section,
        heading_map=heading_map,
        expanded_options=base_expanded_options,
        main_body_paths=main_body_paths,
    )
    TOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOC_PATH.write_text(toc_md, encoding="utf-8")

    if ANNEX_TOC_MODE == "external" and annex_entries_by_id:
        for annex_id, annex_order in annex_entries_by_id.items():
            annex_paths = annex_source_paths_by_id.get(annex_id, set())
            if not annex_order:
                continue
            annex_overrides = _load_annex_toc_overrides(annex_dir_by_id.get(annex_id, ROOT))
            annex_toc_overrides = (
                annex_overrides.get("toc") if isinstance(annex_overrides.get("toc"), dict) else {}
            )
            annex_toc_settings = merge_settings(TOC_SETTINGS, annex_toc_overrides)
            for key, value in annex_overrides.items():
                if key in annex_toc_settings and key not in {"expanded_sections", "toc"}:
                    annex_toc_settings[key] = value
            annex_heading_title = _config_str(
                annex_toc_settings.get("heading_title"),
                ANNEX_TOC_HEADING_TITLE,
            )
            annex_running_header = _config_str(
                annex_overrides.get("running_header"),
                ANNEX_TOC_RUNNING_HEADER,
            )
            annex_expanded_settings = merge_settings(
                TOC_EXPANDED_SETTINGS,
                annex_toc_settings.get("expanded_sections")
                if isinstance(annex_toc_settings.get("expanded_sections"), dict)
                else {},
            )
            annex_expanded_settings = merge_settings(
                annex_expanded_settings,
                annex_overrides.get("expanded_sections") if isinstance(annex_overrides.get("expanded_sections"), dict) else {},
            )
            annex_default_options = ExpandedTocOptions(
                enabled=base_expanded_options.enabled,
                include_unnumbered=base_expanded_options.include_unnumbered,
                skip_single_letter=base_expanded_options.skip_single_letter,
                number_suffix=base_expanded_options.number_suffix,
                promote_orphaned_headings=base_expanded_options.promote_orphaned_headings,
                separator_before_block=base_expanded_options.separator_before_block,
                unnumbered_style=base_expanded_options.unnumbered_style,
                roman_end_marker=base_expanded_options.roman_end_marker,
                max_nesting_level=base_expanded_options.max_nesting_level,
                include_level1=True,
                render_depth0_as_heading=True,
            )
            annex_expanded_options = build_expanded_options(
                annex_expanded_settings,
                defaults=annex_default_options,
            )
            annex_heading_map: dict[str, list[NumberedHeading]] = {}
            if annex_expanded_options.enabled:
                annex_heading_map = gather_numbered_heading_map(
                    annex_order,
                    annex_expanded_options.max_nesting_level,
                    include_unnumbered=annex_expanded_options.include_unnumbered,
                    skip_single_letter=annex_expanded_options.skip_single_letter,
                    promote_orphaned_headings=annex_expanded_options.promote_orphaned_headings,
                    include_level1=annex_expanded_options.include_level1,
                )

            annex_toc_md = render_annex_toc(
                annex_id,
                annex_order,
                annex_labels,
                annex_paths,
                heading_map=annex_heading_map,
                expanded_options=annex_expanded_options,
                heading_title=annex_heading_title,
                running_header=annex_running_header,
            )

            output_rel = ANNEX_TOC_OUTPUT_PATTERN.format(annex_id=annex_id)
            output_path = ROOT / output_rel
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(annex_toc_md, encoding="utf-8")


if __name__ == "__main__":
    main()
