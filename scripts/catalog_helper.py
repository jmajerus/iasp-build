#!/usr/bin/env python3
"""Generic slot filler for catalog-style collections."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from ..lib.slot_manager import replace_slot_content

try:
    import yaml  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - dependency notice
    raise SystemExit(
        "PyYAML is required for the catalog helper. Install it with "
        "`pip install pyyaml` (or your package manager) and rerun the script."
    ) from exc

TOOLING_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLING_ROOT.parent
DEFAULT_CONFIG = PROJECT_ROOT / "scripts" / "pattern_catalog" / "mapping.yaml"

Renderer = Callable[[list[dict[str, Any]], dict[str, Any]], str]


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def ensure_absolute(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate)


def relativize(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def escape_attr_value(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace('"', "&quot;")


def resolve_collections(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize domain-specific keys into the generic collections/items shape."""

    vocabulary = config.get("vocabulary") or {}
    collections_field = vocabulary.get("collections_field", "collections")
    raw_collections = config.get(collections_field)
    if raw_collections is None and collections_field != "collections":
        raw_collections = config.get("collections")
    if not raw_collections:
        return []

    items_field = vocabulary.get("items_field", "items")
    normalized: list[dict[str, Any]] = []
    for collection in raw_collections:
        if not isinstance(collection, dict):
            continue
        collection_copy = {**collection}
        raw_items = collection_copy.pop(items_field, None)
        if raw_items is None and items_field != "items":
            raw_items = collection.get("items", [])
        raw_items = raw_items or []
        collection_copy["items"] = [dict(item) for item in raw_items if isinstance(item, dict)]
        normalized.append(collection_copy)

    return normalized


def build_item_block(item: dict[str, Any], defaults: dict[str, Any]) -> str:
    source_file = item.get("source_file")
    if not source_file:
        raise ValueError(f"Item '{item.get('title')}' lacks a source_file")

    template = defaults.get("item_template")
    if template:
        return template.format(**item)

    wrapper_class = defaults.get("include_wrapper_class", "include")
    glyph = item.get("glyph")
    attrs: list[str] = []
    if glyph:
        attrs.append(f"glyph=\"{glyph}\"")
    extra_attrs = item.get("extra_attributes", {})
    for key, value in extra_attrs.items():
        attrs.append(f"{key}=\"{value}\"")

    class_bits = f".{wrapper_class}" if wrapper_class else ""
    attr_bits = (" " + " ".join(attrs)) if attrs else ""

    lines = [f":::{{{class_bits}{attr_bits} path=\"{source_file}\"}}", ":::"]
    return "\n".join(lines)


def normalize_item(item: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    normalized = {**item}
    source_file = normalized.get("source_file")
    if source_file:
        source_path = ensure_absolute(source_file)
        normalized["source_file"] = relativize(source_path)
        normalized["exists"] = source_path.exists()
    else:
        normalized["exists"] = False
    normalized.setdefault("slug", normalized.get("title", "").lower().replace(" ", "-"))
    normalized.setdefault("rendered_block", build_item_block(normalized, defaults))
    return normalized


def render_collection_sections(collections: list[dict[str, Any]], options: dict[str, Any]) -> str:
    heading_level = options.get("heading_level", "###").strip() or "###"
    collection_glyph_field = options.get("collection_glyph_field")
    collection_heading_class = options.get("collection_heading_class", "catalog-collection-heading")
    try:
        item_spacing = int(options.get("item_spacing", 1))
    except (TypeError, ValueError):
        item_spacing = 1
    item_spacing = max(1, item_spacing)
    item_divider = options.get("item_divider")
    lines: list[str] = []

    for collection in collections:
        title = collection["title"]
        glyph_value = collection.get(collection_glyph_field) if collection_glyph_field else None

        heading_tokens: list[str] = []
        heading_classes: list[str] = []
        if collection_heading_class:
            heading_classes.append(collection_heading_class)
        extra_classes = collection.get("heading_classes") or []
        if isinstance(extra_classes, str):
            extra_classes = [extra_classes]
        heading_classes.extend(cls for cls in extra_classes if cls)
        if heading_classes:
            heading_tokens.extend(f".{cls}" for cls in heading_classes)

        if glyph_value:
            heading_tokens.append(f'section-glyph="{escape_attr_value(glyph_value)}"')

        attr_segment = f" {{{' '.join(heading_tokens)}}}" if heading_tokens else ""
        lines.append(f"{heading_level} {title}{attr_segment}")
        description = collection.get("description")
        if description:
            lines.append(description.strip())
        lines.append("")

        items = collection.get("items", [])
        for idx, item in enumerate(items):
            if not item.get("exists"):
                lines.append(
                    f"<!-- WARNING: Missing source '{item.get('source_file')}' for {item.get('title')} -->"
                )
            lines.append(item["rendered_block"])
            if item_divider and idx < len(items) - 1:
                lines.append(item_divider)
            for _ in range(item_spacing):
                lines.append("")

    return "\n".join(line.rstrip() for line in lines).rstrip() + "\n"


def render_collection_index(collections: list[dict[str, Any]], options: dict[str, Any]) -> str:
    list_style = options.get("list_style", "unordered")
    item_label = options.get("item_label_field", "title")
    lines: list[str] = []

    for collection in collections:
        lines.append(f"**{collection['title']}**")
        lines.append("")
        items = collection.get("items", [])
        for idx, item in enumerate(items, start=1):
            bullet = f"{idx}." if list_style == "ordered" else "-"
            label = item.get(item_label, item.get("title", "Unnamed"))
            status_note = f" (TODO: {item['status']})" if item.get("status") else ""
            lines.append(f"{bullet} {label}{status_note}")
        lines.append("")

    return "\n".join(line.rstrip() for line in lines).rstrip() + "\n"


RENDERERS: dict[str, Renderer] = {
    "collection_sections": render_collection_sections,
    "collection_index": render_collection_index,
}


def replace_marked_region(text: str, start: str, end: str, new_block: str) -> str:
    start_idx = text.find(start)
    if start_idx == -1:
        raise ValueError(f"Start marker '{start}' not found")
    end_idx = text.find(end, start_idx)
    if end_idx == -1:
        raise ValueError(f"End marker '{end}' not found")

    start_close = start_idx + len(start)
    before = text[:start_close]
    after = text[end_idx:]
    newline = "\n" if not before.endswith("\n") else ""
    trailing_newline = "\n" if not new_block.endswith("\n") else ""
    return f"{before}{newline}\n{new_block}{trailing_newline}{after}"


def apply_insertions(insertions: list[dict[str, Any]], collections: list[dict[str, Any]], *, dry_run: bool) -> None:
    for insertion in insertions:
        target_path = ensure_absolute(insertion["target"])
        renderer_name = insertion["renderer"]
        renderer = RENDERERS.get(renderer_name)
        if not renderer:
            raise ValueError(f"Unknown renderer '{renderer_name}' in config")

        block = renderer(collections, insertion.get("options", {}))
        original = target_path.read_text(encoding="utf-8")

        slot_name = insertion.get("slot")
        if slot_name:
            updated = replace_slot_content(original, slot_name, block)
        else:
            updated = replace_marked_region(
                original,
                insertion["start_marker"],
                insertion["end_marker"],
                block,
            )

        if dry_run:
            print(f"[dry-run] Would update {relativize(target_path)}")
        else:
            target_path.write_text(updated, encoding="utf-8")
            print(f"Updated {relativize(target_path)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the catalog mapping YAML (defaults to mapping.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render blocks without writing changes to disk.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    collections = resolve_collections(config)
    if not collections:
        raise SystemExit("No collections defined in mapping configuration.")

    normalized: list[dict[str, Any]] = []
    include_defaults = config.get("include_defaults", {})
    for collection in collections:
        collection_copy = {**collection}
        items = [
            normalize_item(item, include_defaults)
            for item in collection.get("items", [])
        ]
        collection_copy["items"] = items
        normalized.append(collection_copy)

    insertions = config.get("insertions", [])
    if not insertions:
        raise SystemExit("No insertion points configured; nothing to update.")

    apply_insertions(insertions, normalized, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
