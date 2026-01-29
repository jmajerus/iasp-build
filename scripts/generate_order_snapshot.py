#!/usr/bin/env python3
"""Render the canonical book order (with include expansions) as Markdown."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iasp_tooling.lib import config as iasp_config
from iasp_tooling.lib.order_sources import BookOrderData, load_book_order, normalize_path
from iasp_tooling.lib.container_walker import ContainerNode, walk_order_entries
from iasp_tooling.lib.snapshot_renderer import (
    SnapshotEntry,
    group_key_from_path,
    render_snapshot_markdown,
)
BUILD_DIR = ROOT / "build"
ANNEX_OUTPUT_DIR = BUILD_DIR / "annexes"
BOOK_ORDER = ROOT / "book-order.txt"


VALID_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
INCLUDE_OPEN_RE = re.compile(r"^\s*:::\s*\{([^}]*)\}\s*$")
DEFAULT_MAX_DEPTH = 2

CONFIG = iasp_config.load_config()


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


def _resolve_annex_settings() -> dict[str, Any]:
    layout = _config_section("layout")
    layout_annex = layout.get("annexes") if isinstance(layout.get("annexes"), dict) else {}
    top_level = _config_section("annexes")
    settings = dict(layout_annex)
    settings.update(top_level)
    return settings


ANNEX_SETTINGS = _resolve_annex_settings()
ANNEX_IDS = _config_list(ANNEX_SETTINGS.get("annex_ids"))
ANNEX_INCLUDE_INSIDE = _config_bool(ANNEX_SETTINGS.get("include_inside_manuscript"), False)
ANNEX_POSITION_AFTER_APPENDICES = _config_bool(ANNEX_SETTINGS.get("position_after_appendices"), True)


def _discover_annex_orders() -> list[Path]:
    annex_root = ROOT / "annexes"
    if not annex_root.exists():
        return []
    candidates = sorted(annex_root.glob("*/book-order.txt"))
    return [path.resolve() for path in candidates if path.is_file()]


@dataclass
class IncludeBlock:
    identifier: str | None
    classes: list[str]
    attrs: dict[str, str]
    source: str
    line_number: int


def _resolve_default_output(profile: str | None) -> Path:
    if profile and profile.strip() and profile.strip().lower() != "default":
        destination = ANNEX_OUTPUT_DIR / profile.strip()
    else:
        destination = BUILD_DIR
    destination.mkdir(parents=True, exist_ok=True)
    return destination / "book-order.generated.md"


def _relative_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _resolve_annex_order_paths() -> list[Path]:
    annex_ids = list(ANNEX_IDS)
    if not annex_ids:
        return _discover_annex_orders()

    profiles_path = ROOT / "build-profiles.json"
    definitions: dict[str, Any] = {}
    if profiles_path.exists():
        try:
            raw = json.loads(profiles_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            definitions = raw

    resolved: list[Path] = []
    seen: set[Path] = set()

    discovered = {path.resolve() for path in _discover_annex_orders()}

    for annex_id in annex_ids:
        entry = definitions.get(annex_id)
        order_value = None
        if isinstance(entry, dict):
            order_value = entry.get("order_file") or entry.get("order")

        order_path = Path(order_value) if order_value else Path(annex_id)
        if not order_path.is_absolute():
            order_path = (ROOT / order_path).resolve()

        if not order_path.exists() and not order_path.is_absolute():
            fallback = ROOT / "annexes" / str(annex_id) / "book-order.txt"
            if fallback.exists():
                order_path = fallback.resolve()

        if order_path == BOOK_ORDER:
            continue

        if not order_path.exists():
            print(
                "-- Warning: annex order not found for "
                f"'{annex_id}'. Looked at {order_path}. "
                "If this is a profile ID, add it to build-profiles.json; "
                "otherwise set annex_ids to the order file path."
            )
            continue

        if order_path not in seen:
            resolved.append(order_path)
            seen.add(order_path)

    for path in discovered:
        if path not in seen:
            resolved.append(path)
            seen.add(path)

    return resolved


def _merge_label_map(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if key not in merged:
            merged[key] = value
    return merged


def _merge_orders(base: BookOrderData, annexes: list[BookOrderData]) -> BookOrderData:
    annex_entries: list[str] = []
    for annex in annexes:
        annex_entries.extend(annex.entries)

    if not annex_entries:
        return base

    entries = list(base.entries)
    base_set = {normalize_path(entry).lower() for entry in entries}
    annex_deduped: list[str] = []
    duplicates: list[str] = []
    for entry in annex_entries:
        key = normalize_path(entry).lower()
        if key in base_set:
            duplicates.append(entry)
            continue
        annex_deduped.append(entry)

    if duplicates:
        sample = ", ".join(duplicates[:5])
        print(
            "-- Warning: annex order entries already exist in main order; "
            f"skipping {len(duplicates)} duplicate(s). Sample: {sample}"
        )
    appendices = [
        idx
        for idx, entry in enumerate(entries)
        if normalize_path(entry).lower().startswith("appendices/")
    ]

    if ANNEX_POSITION_AFTER_APPENDICES:
        insert_at = appendices[-1] + 1 if appendices else len(entries)
    else:
        insert_at = appendices[0] if appendices else len(entries)

    if annex_deduped:
        entries[insert_at:insert_at] = annex_deduped

    front_labels = dict(base.front_labels)
    chapter_labels = dict(base.chapter_labels)
    sidebar_labels = dict(base.sidebar_labels)
    appendix_labels = dict(base.appendix_labels)

    for annex in annexes:
        front_labels = _merge_label_map(front_labels, annex.front_labels)
        chapter_labels = _merge_label_map(chapter_labels, annex.chapter_labels)
        sidebar_labels = _merge_label_map(sidebar_labels, annex.sidebar_labels)
        appendix_labels = _merge_label_map(appendix_labels, annex.appendix_labels)

    return BookOrderData(entries, front_labels, chapter_labels, sidebar_labels, appendix_labels)


FILE_INCLUDE_CACHE: dict[str, list[IncludeBlock]] = {}


def _parse_attr_tokens(raw: str) -> tuple[str | None, list[str], dict[str, str]]:
    lexer = shlex.shlex(raw, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    identifier: str | None = None
    classes: list[str] = []
    attrs: dict[str, str] = {}

    for token in lexer:
        if token.startswith("#"):
            identifier = token[1:]
        elif token.startswith("."):
            classes.append(token[1:])
        elif "=" in token:
            key, value = token.split("=", 1)
            attrs[key] = value
        else:
            classes.append(token)

    return identifier, classes, attrs


def _discover_include_blocks(rel_path: str) -> list[IncludeBlock]:
    if rel_path in FILE_INCLUDE_CACHE:
        return FILE_INCLUDE_CACHE[rel_path]

    source_file = ROOT / rel_path
    if not source_file.exists():
        FILE_INCLUDE_CACHE[rel_path] = []
        return []

    includes: list[IncludeBlock] = []
    with source_file.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            match = INCLUDE_OPEN_RE.match(raw.strip())
            if not match:
                continue
            identifier, classes, attrs = _parse_attr_tokens(match.group(1))
            if "include" not in classes:
                continue
            includes.append(IncludeBlock(identifier, classes, attrs, rel_path, line_number))

    FILE_INCLUDE_CACHE[rel_path] = includes
    return includes


def _attr_get(attrs: dict[str, str], *candidates: str) -> str | None:
    for key in candidates:
        if key in attrs:
            return attrs[key]
    return None


def _resolve_include_path(raw_value: str | None, parent_dir: Path) -> Path | None:
    if not raw_value:
        return None

    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate

    root_candidate = (ROOT / candidate).resolve()
    if root_candidate.exists():
        return root_candidate

    fallback = (parent_dir / candidate).resolve()
    if fallback.exists():
        return fallback

    return root_candidate


def _list_directory_targets(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in VALID_MARKDOWN_EXTENSIONS
    ]
    files.sort(key=lambda path: path.name.lower())
    return files


def _format_include_label(target: str, include_type: str, attrs: dict[str, str], classes: list[str]) -> str:
    detail_bits: list[str] = []
    if include_type:
        detail_bits.append(include_type)

    for key in ("list", "list-style", "glyph", "mode", "banner", "page-banner", "running-head"):
        value = attrs.get(key)
        if value:
            detail_bits.append(f"{key}={value}")

    if "code" in classes and "code" not in detail_bits:
        detail_bits.append("code")

    detail = f" ({', '.join(detail_bits)})" if detail_bits else ""
    return f"Include {target}{detail}"


def _collect_include_children(
    rel_path: str,
    depth: int,
    max_depth: int,
    order_data: BookOrderData,
    visited: set[str] | None = None,
) -> list[SnapshotEntry]:
    if depth > max_depth:
        return []

    visited = visited or set()
    if rel_path in visited:
        return []

    visited.add(rel_path)
    includes = _discover_include_blocks(rel_path)
    parent_file = ROOT / rel_path
    parent_dir = parent_file.parent if parent_file.exists() else ROOT
    nodes: list[SnapshotEntry] = []

    for include in includes:
        node = _build_include_node(
            include,
            parent_dir,
            depth,
            max_depth,
            order_data,
            visited,
        )
        if node:
            nodes.append(node)

    visited.remove(rel_path)
    return nodes


def _build_include_node(
    include: IncludeBlock,
    parent_dir: Path,
    depth: int,
    max_depth: int,
    order_data: BookOrderData,
    visited: set[str],
) -> SnapshotEntry | None:
    dir_attr = _attr_get(include.attrs, "data-dir", "dir", "directory")
    file_attr = _attr_get(include.attrs, "path", "file", "src")
    list_mode = include.attrs.get("list")

    target_type = "directory" if dir_attr else "file" if file_attr else "unspecified"
    target_value = dir_attr or file_attr or "(unspecified)"
    label = _format_include_label(target_value, target_type, include.attrs, include.classes)
    node = SnapshotEntry(label=label, kind="include")

    if dir_attr:
        dir_path = _resolve_include_path(dir_attr, parent_dir)
        if not dir_path or not dir_path.exists():
            node.note = f"Directory not found: {dir_attr}"
            return node

        files = _list_directory_targets(dir_path)
        if not files:
            node.note = f"No Markdown files found in {dir_attr}"
            return node

        for file_path in files:
            rel_child = normalize_path(_relative_to_root(file_path))
            label_child = order_data.label_for(rel_child)
            child_kind = "include-list-item" if list_mode else "include-file"
            child = SnapshotEntry(label=label_child, path=rel_child, kind=child_kind)
            if not list_mode and depth < max_depth:
                child.children.extend(
                    _collect_include_children(
                        rel_child,
                        depth + 1,
                        max_depth,
                        order_data,
                        visited,
                    )
                )
            node.children.append(child)

        return node

    if file_attr:
        file_path = _resolve_include_path(file_attr, parent_dir)
        if not file_path or not file_path.exists():
            node.note = f"File not found: {file_attr}"
            return node

        rel_child = normalize_path(_relative_to_root(file_path))
        label_child = order_data.label_for(rel_child)
        child = SnapshotEntry(label=label_child, path=rel_child, kind="include-file")
        if depth < max_depth:
            child.children.extend(
                _collect_include_children(
                    rel_child,
                    depth + 1,
                    max_depth,
                    order_data,
                    visited,
                )
            )
        node.children.append(child)
        return node

    node.note = "Include directive missing path/data-dir."
    return node


def _format_node_note(node: ContainerNode) -> str | None:
    bits: list[str] = []
    if node.manifest:
        bits.append(f"Manifest: `{node.manifest}`")
    if node.metadata:
        meta_bits = [f"{key}={value}" for key, value in node.metadata.items()]
        if meta_bits:
            bits.append("Metadata: " + ", ".join(meta_bits))
    if node.notes:
        bits.extend(node.notes)
    return " | ".join(bits) if bits else None


def _node_to_snapshot_entry(
    node: ContainerNode,
    order_data: BookOrderData,
    max_depth: int,
) -> SnapshotEntry:
    kind = "book-entry" if node.kind == "file" else "book-directory"
    entry = SnapshotEntry(
        label=node.label,
        path=node.rel_path,
        kind=kind,
    )

    entry.note = _format_node_note(node)

    if node.kind == "file" and node.rel_path:
        entry.children.extend(
            _collect_include_children(
                node.rel_path,
                depth=1,
                max_depth=max_depth,
                order_data=order_data,
            )
        )
    else:
        for child in node.children:
            entry.children.append(_node_to_snapshot_entry(child, order_data, max_depth))

    return entry


def generate_snapshot(
    order_path: Path,
    output_path: Path,
    profile: str | None,
    title: str,
    max_depth: int,
) -> None:
    order_data = load_book_order(order_path)

    if (
        ANNEX_INCLUDE_INSIDE
        and order_path == BOOK_ORDER
        and not (profile and profile in ANNEX_IDS)
    ):
        annex_paths = _resolve_annex_order_paths()
        annex_orders: list[BookOrderData] = []
        for path in annex_paths:
            try:
                annex_orders.append(load_book_order(path))
            except FileNotFoundError:
                print(f"-- Warning: annex order file missing at {path}")
        if annex_orders:
            order_data = _merge_orders(order_data, annex_orders)
    order_nodes = walk_order_entries(order_data, ROOT)

    if not order_nodes:
        print(f"-- No entries found in {order_path}; skipping snapshot generation.")
        return

    snapshot_entries: list[SnapshotEntry] = []

    for idx, node in enumerate(order_nodes, start=1):
        entry = _node_to_snapshot_entry(node, order_data, max_depth)
        entry.group = group_key_from_path(node.rel_path)
        entry.index = idx
        snapshot_entries.append(entry)

    source_label = _relative_to_root(order_path)
    markdown = render_snapshot_markdown(
        snapshot_entries,
        title=title,
        source_label=source_label,
        profile=profile,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"-- Wrote canonical order snapshot to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render book-order.txt (with nested includes) as Markdown.")
    parser.add_argument("--order", default="book-order.txt", help="Path to the canonical order list.")
    parser.add_argument(
        "--output",
        default=None,
        help="Destination Markdown file (defaults to build/book-order.generated.md or the annex profile directory).",
    )
    parser.add_argument("--profile", default=None, help="Optional build profile label (for metadata/output routing).")
    parser.add_argument("--title", default="Canonical Book Order", help="Heading used for the Markdown snapshot.")
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help="Maximum include depth to traverse (1 = just immediate includes).",
    )
    args = parser.parse_args()

    order_path = Path(args.order)
    if not order_path.is_absolute():
        order_path = (ROOT / args.order).resolve()

    if not order_path.exists():
        print(f"!! order file not found at {order_path}")
        raise SystemExit(1)

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (ROOT / args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = _resolve_default_output(args.profile)

    generate_snapshot(order_path, output_path, args.profile, args.title, max(args.max_depth, 1))


if __name__ == "__main__":
    main()
