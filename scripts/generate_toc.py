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

import json
import re
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
TAGGER = ROOT / "tag_by_dir.py"
PANDOC_MARKDOWN_FORMAT = "markdown+fenced_divs+header_attributes+link_attributes+smart"

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
TOC_EXPANDED_MAX_NESTING = _config_int(
    TOC_EXPANDED_SETTINGS.get("max_nesting_level"), 2, minimum=1, maximum=3
)
TOC_RUNNING_HEADER_LABEL = _config_str(TOC_SETTINGS.get("running_header_label"), None)
TOC_OUTPUT_PATH = _config_str(TOC_SETTINGS.get("output_path"), DEFAULT_TOC_OUTPUT) or DEFAULT_TOC_OUTPUT
TOC_PATH = ROOT / TOC_OUTPUT_PATH
TOC_HEADING_TITLE = _config_str(TOC_SETTINGS.get("heading_title"), "TABLE OF CONTENTS")
TOC_HEADING_SUBTITLE = _config_str(TOC_SETTINGS.get("heading_subtitle"), None)
TOC_FRONTMATTER_LABEL = _config_str(TOC_SETTINGS.get("frontmatter_label"), "Front Matter")
TOC_APPENDICES_LABEL = _config_str(TOC_SETTINGS.get("appendices_label"), "Appendices")
TOC_EPILOGUE_LABEL = _config_str(TOC_SETTINGS.get("epilogue_label"), "Epilogue")
TOC_EPILOGUE_PATHS = set(_config_list(TOC_SETTINGS.get("epilogue_paths")))
TOC_EPILOGUE_FILENAMES = set(_config_list(TOC_SETTINGS.get("epilogue_filenames")))
TOC_SELF_REL_PATH = str(TOC_PATH.relative_to(ROOT)) if TOC_PATH.is_absolute() else str(TOC_PATH)


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


@dataclass
class NumberedHeading:
    depth: int
    number: str
    title: str


def parse_book_order() -> tuple[
    list[str],
    dict[str, str],
    dict[str, tuple[str, str]],
    dict[str, str],
    dict[str, str],
    dict[str, str],
    set[str],
    dict[str, list[str]],
    dict[str, set[str]],
    bool,
    dict[str, Path],
]:
    paths: list[str] = []
    front_labels: dict[str, str] = {}
    chapter_labels: dict[str, tuple[str, str]] = {}
    sidebar_labels: dict[str, str] = {}
    appendix_labels: dict[str, str] = {}
    annex_labels: dict[str, str] = {}
    annex_source_paths: set[str] = set()
    annex_entries_by_id: dict[str, list[str]] = {}
    annex_source_paths_by_id: dict[str, set[str]] = {}
    annex_toc_in_order = False
    annex_dir_by_id: dict[str, Path] = {}

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
    ]:
        file_paths: list[str] = []
        file_front: dict[str, str] = {}
        file_chapter: dict[str, tuple[str, str]] = {}
        file_sidebar: dict[str, str] = {}
        file_appendix: dict[str, str] = {}
        file_annex: dict[str, str] = {}

        if not order_path.exists():
            return file_paths, file_front, file_chapter, file_sidebar, file_appendix, file_annex

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

        return file_paths, file_front, file_chapter, file_sidebar, file_appendix, file_annex

    main_paths, main_front, main_chapter, main_sidebar, main_appendix, main_annex = _parse_order_file(BOOK_ORDER)
    paths.extend(main_paths)
    front_labels.update(main_front)
    chapter_labels.update(main_chapter)
    sidebar_labels.update(main_sidebar)
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
            file_paths, file_front, file_chapter, file_sidebar, file_appendix, file_annex = _parse_order_file(
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
        appendix_labels,
        annex_labels,
        annex_source_paths,
        annex_entries_by_id,
        annex_source_paths_by_id,
        annex_toc_in_order,
        annex_dir_by_id,
    )


def run_pandoc_json(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "pandoc",
            "-f",
            PANDOC_MARKDOWN_FORMAT,
            "-t",
            "json",
            str(path),
        ],
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


def collect_headings(blocks: list[Any], sink: list[dict[str, Any]]) -> None:
    for block in blocks:
        block_type = block["t"]
        if block_type == "Header":
            sink.append(block)
        elif block_type == "Div":
            collect_headings(block["c"][1], sink)
        elif block_type in {"BlockQuote", "Note"}:
            collect_headings(block["c"], sink)
        elif block_type in {"BulletList", "OrderedList"}:
            items = block["c"][1] if block_type == "OrderedList" else block["c"]
            for item in items:
                collect_headings(item, sink)
        elif block_type == "DefinitionList":
            for _, defs in block["c"]:
                for definition in defs:
                    collect_headings(definition, sink)


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
        toc_title = headings["toc_title"] or f"Part {part_id}"
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


SERIES_CODE_RE = re.compile(r"^([A-D])(\d+)(?:[.\-—|:]\s*|\s+)(.+)$")
APPENDIX_RE = re.compile(r"^Appendix\s+([A-Z0-9]+)\s*[—\-:|]\s*(.+)$", re.IGNORECASE)
PART_ID_FROM_FILENAME = re.compile(r"SERIES\s+([A-D])", re.IGNORECASE)
PART_HEADER_RE = re.compile(r"^SERIES\s+[A-D]\s*[—\-]\s*PART\s+\d+", re.IGNORECASE)
BRIDGE_PREFIX_RE = re.compile(r"^(?:INTER\s*SERIES\s+)?BRIDGE(?:HEAD)?\s*[—\-:|]\s*", re.IGNORECASE)
# Accept plain decimals (e.g., 2.3.1) and prefixes such as DF1-1.2 or DF1.1.2
NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?P<number>(?:[A-Za-z]+[A-Za-z0-9]*[\-–—.]\d+(?:[.\-–—]\d+)*|\d+(?:[.\-–—]\d+)*))"
    r"(?P<separator>[\s.\-–—:)]{1,10})(?P<title>.+)$"
)


def normalize_whitespace(text: str | None) -> str | None:
    if text is None:
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed or None


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
) -> list[NumberedHeading]:
    blocks = load_document_blocks(rel_path)
    if not blocks:
        return []

    headings: list[dict[str, Any]] = []
    collect_headings(blocks, headings)
    outline: list[NumberedHeading] = []

    for header in headings:
        level, _attrs, inline = header["c"]
        if level < 2:
            continue
        depth = max(1, level - 1)
        if depth > max_nesting_level:
            continue
        text = normalize_whitespace(stringify_inlines(inline))
        if not text:
            continue
        split = split_numbered_heading(text)
        if split:
            number, title = split
            outline.append(NumberedHeading(depth=depth, number=number, title=title))
            continue
        if include_unnumbered:
            outline.append(NumberedHeading(depth=depth, number="", title=text))

    return outline


def gather_numbered_heading_map(
    order: list[str],
    max_nesting_level: int,
    *,
    include_unnumbered: bool = False,
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
        outline = extract_numbered_headings(
            rel_path,
            max_nesting_level,
            include_unnumbered=include_unnumbered,
        )
        if outline:
            heading_map[rel_path] = outline
    return heading_map


def format_heading_outline(headings: list[NumberedHeading]) -> list[str]:
    lines: list[str] = []
    for heading in headings:
        indent = "  " * max(heading.depth - 1, 0)
        label = f"{heading.number} {heading.title}".strip()
        lines.append(f"{indent}- {label}")
    return lines


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

        if not title and tokens.isdisjoint(EPIGRAPH_TYPES):
            title = text
            title_level = level
            continue

        if not subtitle and tokens.isdisjoint(EPIGRAPH_TYPES):
            if title_level is not None and level > title_level:
                subtitle = text
                continue

        if (
            title
            and not subtitle
            and title_level is not None
            and level == title_level
            and not PART_HEADER_RE.match(text)
        ):
            subtitle = text
            continue

    if title:
        inferred_code, clean_title = split_code_from_title(title)
        if inferred_code and not code:
            code = inferred_code
        title = clean_title

    return TocMeta(title=title, subtitle=subtitle, code=code, series=series)


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
    part_meta: OrderedDict[str, dict[str, str]],
) -> tuple[
    dict[str, list[dict[str, str | None]]],
    dict[str, list[str]],
    dict[str, list[dict[str, str]]],
    bool,
]:
    part_keys = list(part_meta.keys())
    chapters: dict[str, list[dict[str, str]]] = {k: [] for k in part_keys}
    sidebars: dict[str, list[str]] = {k: [] for k in part_keys}
    bridges: dict[str, list[dict[str, str]]] = {k: [] for k in part_keys}
    epilogue_present = False
    current_part: str | None = None

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
                "path": rel_path,
            }
            chapters[part_id].append(entry)
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

        if rel_path.startswith("sidebars/"):
            label = sidebar_labels.get(rel_path)
            if not label:
                meta = infer_document_meta(rel_path)
                label = meta.title
            label = normalize_whitespace(label)
            part_id = current_part or part_id_from_path(rel_path) or "B"
            if label and part_id in sidebars:
                sidebars[part_id].append(f" • {label}")

    return chapters, sidebars, bridges, epilogue_present


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
    expanded_enabled: bool,
) -> str:
    front_entries = build_front_entries(order, front_labels)
    chapter_entries, sidebar_entries, bridge_entries, has_epilogue = build_chapter_entries(
        order, chapter_labels, sidebar_labels, part_meta
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

    for part_key, meta in part_meta.items():
        lines.append(f"## **{meta['toc_title']}**\n")
        if show_chapter_entries:
            for entry in chapter_entries[part_key]:
                code = entry["code"]
                heading = f"**{code}** {entry['title']}" if code else f"**{entry['title']}**"
                lines.append(heading)
                if show_details and entry["subtitle"]:
                    lines.append(f"*{entry['subtitle']}*")
                if expanded_enabled:
                    entry_path = entry.get("path")
                    outline = heading_map.get(entry_path)
                    if outline:
                        lines.extend(format_heading_outline(outline))
                lines.append("")
        if show_details and sidebar_entries[part_key]:
            lines.append("**Sidebars**")
            lines.extend(sidebar_entries[part_key])
            lines.append("")
        if show_details and bridge_entries[part_key]:
            for bridge in bridge_entries[part_key]:
                heading_title = bridge["title"] or "Bridge"
                heading = f"**Bridge — {heading_title}**" if bridge["title"] else "**Bridge**"
                lines.append(heading)
                if bridge["subtitle"]:
                    lines.append(f"*{bridge['subtitle']}*")
                lines.append("")
        lines.append("\n------\n")

    if has_epilogue and TOC_EPILOGUE_LABEL:
        lines.append(f"## **{TOC_EPILOGUE_LABEL}**\n")
        lines.append("\n------\n")

    def _render_annexes() -> None:
        if not (include_annexes_section and ANNEX_INCLUDE_IN_TOC and annex_entries):
            return
        lines.append(f"## **{TOC_ANNEXES_LABEL}**\n")
        if max_depth >= 2:
            for annex in annex_entries:
                lines.append(f"**{annex['label']}**")
                if annex["subtitle"]:
                    lines.append(f"*{annex['subtitle']}*")
                if expanded_enabled:
                    outline = heading_map.get(annex.get("path"))
                    if outline:
                        lines.extend(format_heading_outline(outline))
                lines.append("")

    def _render_appendices() -> None:
        if not include_appendices:
            return
        lines.append(f"## **{TOC_APPENDICES_LABEL}**\n")
        if appendix_entries and max_depth >= 2:
            for appendix in appendix_entries:
                lines.append(f"**{appendix['label']}**")
                if appendix["subtitle"]:
                    lines.append(f"*{appendix['subtitle']}*")
                if expanded_enabled:
                    outline = heading_map.get(appendix.get("path"))
                    if outline:
                        lines.extend(format_heading_outline(outline))
                lines.append("")

    if ANNEX_POSITION_AFTER_APPENDICES:
        _render_appendices()
        _render_annexes()
    else:
        _render_annexes()
        _render_appendices()

    if (not include_annexes_section) and ANNEX_TOC_LINE_ITEM:
        lines.append("")
        lines.append(f"## **{TOC_ANNEXES_LABEL}**\n")
        for annex in annex_summaries:
            lines.append(f"**{annex['label']}**")
            if annex.get("subtitle"):
                lines.append(f"*{annex['subtitle']}*")
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
    expanded_enabled: bool,
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
            lines.append(f"**{annex['label']}**")
            if annex["subtitle"]:
                lines.append(f"*{annex['subtitle']}*")
            if expanded_enabled:
                outline = heading_map.get(annex.get("path"))
                if outline:
                    lines.extend(format_heading_outline(outline))
            lines.append("")

    lines.append(":::\n")
    return "\n".join(lines)


def main() -> None:
    if not TOC_ENABLED:
        print("-- TOC generation disabled via iasp-config; skipping")
        return

    ensure_directory_tags()
    (
        order,
        front_labels,
        chapter_labels,
        sidebar_labels,
        appendix_labels,
        annex_labels,
        annex_source_paths,
        annex_entries_by_id,
        annex_source_paths_by_id,
        annex_toc_in_order,
        annex_dir_by_id,
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
    if TOC_EXPANDED_ENABLED:
        heading_map = gather_numbered_heading_map(
            order,
            TOC_EXPANDED_MAX_NESTING,
            include_unnumbered=TOC_EXPANDED_INCLUDE_UNNUMBERED,
        )
    include_annexes_section = ANNEX_TOC_MODE == "embedded" and not annex_toc_in_order

    toc_md = render_toc(
        order,
        front_labels,
        chapter_labels,
        sidebar_labels,
        appendix_labels,
        annex_labels,
        annex_source_paths,
        annex_summaries,
        part_meta,
        max_depth=TOC_MAX_DEPTH,
        include_appendices=TOC_INCLUDE_APPENDICES,
        include_annexes_section=include_annexes_section,
        heading_map=heading_map,
        expanded_enabled=TOC_EXPANDED_ENABLED,
    )
    TOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOC_PATH.write_text(toc_md, encoding="utf-8")

    if ANNEX_TOC_MODE == "external" and annex_entries_by_id:
        for annex_id, annex_order in annex_entries_by_id.items():
            annex_paths = annex_source_paths_by_id.get(annex_id, set())
            if not annex_order:
                continue
            annex_overrides = _load_annex_toc_overrides(annex_dir_by_id.get(annex_id, ROOT))
            annex_heading_title = _config_str(
                annex_overrides.get("heading_title"),
                ANNEX_TOC_HEADING_TITLE,
            )
            annex_running_header = _config_str(
                annex_overrides.get("running_header"),
                ANNEX_TOC_RUNNING_HEADER,
            )
            annex_expanded_settings = annex_overrides.get("expanded_sections") or {}
            annex_expanded = _config_bool(
                annex_expanded_settings.get("enabled"),
                TOC_EXPANDED_ENABLED,
            )
            annex_include_unnumbered = _config_bool(
                annex_expanded_settings.get("include_unnumbered"),
                True,
            )
            annex_max_nesting = _config_int(
                annex_expanded_settings.get("max_nesting_level"),
                TOC_EXPANDED_MAX_NESTING,
                minimum=1,
                maximum=6,
            )
            annex_heading_map: dict[str, list[NumberedHeading]] = {}
            if annex_expanded:
                annex_heading_map = gather_numbered_heading_map(
                    annex_order,
                    annex_max_nesting,
                    include_unnumbered=annex_include_unnumbered,
                )

            annex_toc_md = render_annex_toc(
                annex_id,
                annex_order,
                annex_labels,
                annex_paths,
                heading_map=annex_heading_map,
                expanded_enabled=annex_expanded,
                heading_title=annex_heading_title,
                running_header=annex_running_header,
            )

            output_rel = ANNEX_TOC_OUTPUT_PATTERN.format(annex_id=annex_id)
            output_path = ROOT / output_rel
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(annex_toc_md, encoding="utf-8")


if __name__ == "__main__":
    main()
