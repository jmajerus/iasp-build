"""Utilities for parsing book-order files and deriving labels.

These helpers are shared between the build pipeline and auxiliary
scripts such as ``generate_order_snapshot.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "BookOrderData",
    "DirectoryManifest",
    "ManifestItem",
    "collapse_spaces",
    "derive_label",
    "load_directory_manifest",
    "load_book_order",
    "normalize_path",
    "resolve_order_inputs",
]


TOC_FRONT = "# TOC:front"
TOC_CHAPTER = "# TOC:chapter"
TOC_SIDEBAR = "# TOC:sidebar"
TOC_APPENDIX = "# TOC:appendix"

SERIES_FILENAMES = ("series.yaml", "series.yml", "series.json")
ORDER_FILENAME = ".order"


@dataclass(frozen=True)
class BookOrderData:
    entries: list[str]
    front_labels: dict[str, str]
    chapter_labels: dict[str, tuple[str, str]]
    sidebar_labels: dict[str, str]
    appendix_labels: dict[str, str]

    def label_for(self, rel_path: str) -> str:
        return derive_label(
            rel_path,
            self.front_labels,
            self.chapter_labels,
            self.sidebar_labels,
            self.appendix_labels,
        )


@dataclass(frozen=True)
class ManifestItem:
    path: str
    meta: dict[str, Any]


@dataclass(frozen=True)
class DirectoryManifest:
    directory: Path
    source: Path
    items: list[ManifestItem]
    metadata: dict[str, Any]


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip()


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def load_book_order(order_path: Path) -> BookOrderData:
    if not order_path.exists():
        raise FileNotFoundError(order_path)

    entries: list[str] = []
    front_labels: dict[str, str] = {}
    chapter_labels: dict[str, tuple[str, str]] = {}
    sidebar_labels: dict[str, str] = {}
    appendix_labels: dict[str, str] = {}

    with order_path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue

            if line.startswith(TOC_FRONT):
                _assign_label_pair(line, TOC_FRONT, front_labels)
                continue

            if line.startswith(TOC_CHAPTER):
                _assign_chapter_label(line, TOC_CHAPTER, chapter_labels)
                continue

            if line.startswith(TOC_SIDEBAR):
                _assign_label_pair(line, TOC_SIDEBAR, sidebar_labels)
                continue

            if line.startswith(TOC_APPENDIX):
                _assign_label_pair(line, TOC_APPENDIX, appendix_labels)
                continue

            if line.startswith("#"):
                continue

            entries.append(normalize_path(line))

    return BookOrderData(entries, front_labels, chapter_labels, sidebar_labels, appendix_labels)


def _assign_label_pair(raw: str, prefix: str, target: dict[str, str]) -> None:
    try:
        _, rest = raw.split(prefix, 1)
        path_part, label = rest.split("=", 1)
        target[normalize_path(path_part)] = label.strip()
    except ValueError:
        return


def _assign_chapter_label(raw: str, prefix: str, target: dict[str, tuple[str, str]]) -> None:
    try:
        _, rest = raw.split(prefix, 1)
        path_part, rhs = rest.split("=", 1)
        code_part, title_part = rhs.split("|", 1)
        target[normalize_path(path_part)] = (code_part.strip(), title_part.strip())
    except ValueError:
        return


def derive_label(
    rel_path: str,
    front_labels: dict[str, str],
    chapter_labels: dict[str, tuple[str, str]],
    sidebar_labels: dict[str, str],
    appendix_labels: dict[str, str],
) -> str:
    if rel_path in front_labels:
        return collapse_spaces(front_labels[rel_path])
    if rel_path in chapter_labels:
        code, title = chapter_labels[rel_path]
        code = code.strip()
        return collapse_spaces(f"{code} {title}")
    if rel_path in sidebar_labels:
        return collapse_spaces(sidebar_labels[rel_path])
    if rel_path in appendix_labels:
        return collapse_spaces(appendix_labels[rel_path])

    name = Path(rel_path).stem
    fallback = name.replace("_", " ").replace("-", " ")
    cleaned = collapse_spaces(fallback)
    return cleaned or rel_path


def resolve_order_inputs(order_data: BookOrderData, root: Path) -> list[str]:
    inputs: list[str] = []
    for rel in order_data.entries:
        path = (root / rel).resolve()
        inputs.append(str(path))
    return inputs


def load_directory_manifest(directory: Path) -> DirectoryManifest | None:
    """Return the first manifest found for ``directory``.

    Manifest precedence:
    1. ``series.yaml`` / ``series.yml`` / ``series.json`` (structured metadata)
    2. ``.order`` (plain text list, comments allowed)

    Returns ``None`` when no manifest exists.
    """

    if not directory.exists() or not directory.is_dir():
        return None

    directory = directory.resolve()

    for filename in SERIES_FILENAMES:
        manifest_path = directory / filename
        if manifest_path.exists():
            return _load_series_manifest(manifest_path, directory)

    order_path = directory / ORDER_FILENAME
    if order_path.exists():
        return _load_order_manifest(order_path, directory)

    return None


def _load_series_manifest(manifest_path: Path, directory: Path) -> DirectoryManifest:
    data = _read_structured_manifest(manifest_path)

    if isinstance(data, list):
        entries = data
        container_meta: dict[str, Any] = {}
        defaults: dict[str, Any] = {}
    elif isinstance(data, dict):
        entries = data.get("items") or data.get("order") or data.get("entries") or []
        defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
        container_meta = {
            key: value
            for key, value in data.items()
            if key not in {"items", "order", "entries", "defaults"}
        }
    else:
        raise ValueError(f"Manifest root must be a list or dict (found {type(data).__name__})")

    items = _build_manifest_items(entries, defaults)
    return DirectoryManifest(directory=directory, source=manifest_path, items=items, metadata=container_meta)


def _load_order_manifest(order_path: Path, directory: Path) -> DirectoryManifest:
    entries: list[str] = []
    with order_path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(normalize_path(line))

    items = [ManifestItem(path=entry, meta={}) for entry in entries]
    return DirectoryManifest(directory=directory, source=order_path, items=items, metadata={})


def _build_manifest_items(sequence: Iterable[Any], defaults: dict[str, Any]) -> list[ManifestItem]:
    items: list[ManifestItem] = []
    for raw in sequence or []:
        if isinstance(raw, str):
            items.append(ManifestItem(path=normalize_path(raw), meta=dict(defaults)))
            continue

        if isinstance(raw, dict):
            path_value = raw.get("path") or raw.get("file") or raw.get("src")
            if not path_value:
                continue
            entry_meta = dict(defaults)
            for key, value in raw.items():
                if key in {"path", "file", "src"}:
                    continue
                entry_meta[key] = value
            items.append(ManifestItem(path=normalize_path(str(path_value)), meta=entry_meta))
            continue

    return items


def _read_structured_manifest(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency hint
            raise RuntimeError(
                f"Reading YAML manifest '{path}' requires PyYAML. Install it with 'pip install pyyaml'."
            ) from exc

        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:  # type: ignore[attr-defined]
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc

    raise ValueError(f"Unsupported manifest format for {path}")
