"""Directory container traversal utilities for book-order entries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Tuple

from .order_sources import (
    BookOrderData,
    ManifestItem,
    load_directory_manifest,
    normalize_path,
)

VALID_MARKDOWN_EXTENSIONS = {".md", ".markdown"}

__all__ = [
    "ContainerNode",
    "ContainerWalker",
    "flatten_nodes",
    "collect_wrapper_specs",
    "write_wrapper_metadata",
    "walk_order_entries",
]

CLASS_SPLIT_RE = re.compile(r"[\s,]+")


@dataclass
class ContainerNode:
    label: str
    rel_path: str | None
    abs_path: Path | None
    kind: str
    metadata: dict[str, Any]
    manifest: str | None = None
    notes: list[str] = field(default_factory=list)
    children: list["ContainerNode"] = field(default_factory=list)


class ContainerWalker:
    def __init__(self, root: Path, order_data: BookOrderData):
        self.root = root.resolve()
        self.order_data = order_data

    def expand_entry(self, rel_path: str) -> ContainerNode:
        normalized = normalize_path(rel_path)
        target = (self.root / normalized).resolve()
        if target.is_dir():
            return self._walk_directory(normalized, target, set(), meta=None)
        return self._make_file_node(normalized, target, {})

    def _walk_directory(
        self,
        rel_path: str,
        directory: Path,
        ancestry: set[Path],
        meta: dict[str, Any] | None,
    ) -> ContainerNode:
        rel_path = normalize_path(rel_path)
        node = ContainerNode(
            label=self.order_data.label_for(rel_path),
            rel_path=rel_path,
            abs_path=directory,
            kind="directory",
            metadata={},
        )

        if directory in ancestry:
            node.notes.append("Cycle detected; expansion aborted.")
            return node

        if not directory.exists() or not directory.is_dir():
            node.notes.append("Directory missing")
            return node

        manifest_notes: list[str] = []
        children: list[ContainerNode] = []

        ancestry.add(directory)
        try:

            try:
                manifest = load_directory_manifest(directory)
            except (RuntimeError, ValueError) as exc:
                manifest = None
                manifest_notes.append(str(exc))

            if manifest:
                items = manifest.items
                node.metadata = dict(manifest.metadata)
                node.manifest = self._relative_to_root(manifest.source)
            else:
                items = self._default_items(directory)

            if meta:
                if node.metadata:
                    node.metadata.update(meta)
                else:
                    node.metadata = dict(meta)

            if manifest_notes:
                node.notes.extend(manifest_notes)

            for entry in items:
                child_rel, child_abs = self._resolve_child_paths(rel_path, directory, entry.path)
                if child_abs.is_dir():
                    expansion = self._walk_directory(child_rel, child_abs, ancestry, entry.meta)
                else:
                    expansion = self._make_file_node(child_rel, child_abs, entry.meta)

                if expansion:
                    children.append(expansion)

        finally:
            ancestry.remove(directory)

        if not children:
            node.notes.append("No child entries found")

        node.children = children
        return node

    def _make_file_node(self, rel_path: str, path: Path, meta: dict[str, Any]) -> ContainerNode:
        rel_path = normalize_path(rel_path)
        node = ContainerNode(
            label=self.order_data.label_for(rel_path),
            rel_path=rel_path,
            abs_path=path,
            kind="file",
            metadata=dict(meta or {}),
        )
        if not path.exists():
            node.notes.append("File missing")
        return node

    def _default_items(self, directory: Path) -> list[ManifestItem]:
        entries: list[ManifestItem] = []
        for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if child.is_file() and child.suffix.lower() not in VALID_MARKDOWN_EXTENSIONS:
                continue
            entries.append(ManifestItem(path=child.name, meta={}))
        return entries

    def _relative_to_root(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self.root)
            return normalize_path(str(rel))
        except ValueError:
            return normalize_path(str(path))

    def _resolve_child_paths(
        self,
        parent_rel: str,
        parent_abs: Path,
        child_spec: str,
    ) -> Tuple[str, Path]:
        child_path = Path(child_spec)
        if child_path.is_absolute():
            abs_path = child_path.resolve()
        else:
            abs_path = (parent_abs / child_path).resolve()

        rel = self._relative_to_root(abs_path)
        if not rel and parent_rel:
            rel = normalize_path(str(Path(parent_rel) / child_path))
        return rel, abs_path


def walk_order_entries(order_data: BookOrderData, root: Path) -> list[ContainerNode]:
    walker = ContainerWalker(root, order_data)
    nodes: list[ContainerNode] = []
    for entry in order_data.entries:
        nodes.append(walker.expand_entry(entry))
    return nodes


def flatten_nodes(nodes: Iterable[ContainerNode]) -> list[str]:
    files: list[str] = []

    def _visit(node: ContainerNode) -> None:
        if node.kind == "file" and node.abs_path is not None:
            files.append(str(node.abs_path))
        for child in node.children:
            _visit(child)

    for root in nodes:
        _visit(root)

    return files


def collect_wrapper_specs(nodes: Iterable[ContainerNode]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []

    def _collect(node: ContainerNode) -> None:
        payload = _wrapper_payload_for_node(node)
        if payload:
            specs.append(payload)
        for child in node.children:
            _collect(child)

    for root in nodes:
        _collect(root)

    return specs


def write_wrapper_metadata(nodes: Iterable[ContainerNode], destination: Path) -> None:
    specs = collect_wrapper_specs(nodes)
    payload = {"container-wrappers": specs}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _wrapper_payload_for_node(node: ContainerNode) -> dict[str, Any] | None:
    if not node.rel_path:
        return None

    wrapper_meta = _extract_wrapper_metadata(node.metadata)
    if not wrapper_meta:
        return None

    entry: dict[str, Any] = {
        "path": node.rel_path,
        "kind": node.kind,
    }

    if node.manifest:
        entry["manifest"] = node.manifest

    entry.update(wrapper_meta)
    return entry


def _extract_wrapper_metadata(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}

    classes = _normalize_class_tokens(meta.get("classes"))
    classes.extend(_normalize_class_tokens(meta.get("class")))

    child_classes = _normalize_class_tokens(
        meta.get("child_classes")
        or meta.get("child-classes")
        or meta.get("child-class")
    )

    glyphs = _normalize_string_list(meta.get("glyphs"))
    glyph = _first_string(meta.get("glyph"))
    if not glyph and glyphs:
        glyph = glyphs[0]

    banner = _first_string(meta.get("banner") or meta.get("page-banner"))
    running_head = _first_string(meta.get("running-head") or meta.get("running_head"))
    separator = _first_string(meta.get("separator") or meta.get("separator-mode"))

    payload: dict[str, Any] = {}
    if classes:
        payload["classes"] = classes
    if child_classes:
        payload["child_classes"] = child_classes
    if glyph:
        payload["glyph"] = glyph
    if glyphs:
        payload["glyphs"] = glyphs
    if banner:
        payload["banner"] = banner
    if running_head:
        payload["running_head"] = running_head
    if separator:
        payload["separator"] = separator

    return payload


def _normalize_class_tokens(value: Any) -> list[str]:
    tokens = _normalize_string_list(value)
    result: list[str] = []
    for token in tokens:
        for piece in CLASS_SPLIT_RE.split(token.strip()):
            cleaned = piece.strip().strip(".")
            if cleaned:
                result.append(cleaned)
    return _dedupe(result)


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_normalize_string_list(item))
        return items
    return [_first_string(value)] if value is not None else []


def _first_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            candidate = _first_string(item)
            if candidate:
                return candidate
        return None
    return str(value).strip() or None


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        lowered = value
        if lowered not in seen:
            seen.add(lowered)
            ordered.append(value)
    return ordered
