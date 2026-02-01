#!/usr/bin/env python3
"""
build_book.py

Cross-platform build script for long-form Markdown/EPUB/PDF projects.

Usage:
    python build_book.py epub
    python build_book.py pdf
    python build_book.py all         # epub + pdf

    python build_book.py draft-epub  # EPUB without Lua filter (faster)
    python build_book.py draft-pdf   # PDF without Lua filter (faster)
    python build_book.py draft-all   # both, without Lua filter

    python build_book.py docx        # DOCX (Word) build
    python build_book.py rtf         # RTF build for proofreaders

    python build_book.py pdf-chapters    # build every entry in book-order.txt individually
    python build_book.py chapter path/to/file.md  # build a single Markdown file
    python build_book.py article path/or-slug [output] [--with-bibliography]
        # build a standalone article PDF (bibliography suppressed by default)
    python build_book.py articles   # build every single-source article (incremental)

    python build_book.py quote-playground  # tiny fixture for quote styling
"""

import copy
import itertools
import json
import os
import re
import sys
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .lib import config as iasp_config
from .lib import layout_overrides, vscode_tasks
from .lib.background_palettes import select_luma_offset
from .lib.order_sources import BookOrderData, load_book_order, normalize_path
from .lib.container_walker import flatten_nodes, walk_order_entries, write_wrapper_metadata
from .preprocess import config as preprocess_config

# Detect repo + tooling roots relative to this module
TOOLING_ROOT = Path(__file__).resolve().parent
ROOT = TOOLING_ROOT.parent
BUILD_DIR = ROOT / "build"
ANNEX_OUTPUT_DIR = BUILD_DIR / "annexes"
ARTICLE_OUTPUT_DIR = BUILD_DIR / "articles"
ARTICLES_DIR = ROOT / "articles"
ARTICLE_SUFFIXES = {".md", ".markdown"}

DEBUG_TEX = BUILD_DIR / "debug.tex"
BOOK_ORDER = ROOT / "book-order.txt"
STYLES_DIR = TOOLING_ROOT / "styles"
CSS_SHARED = STYLES_DIR / "styles-shared.css"
CSS_EPUB = STYLES_DIR / "styles-epub.css"
CSS_OVERRIDE = BUILD_DIR / layout_overrides.CSS_OVERRIDE_NAME
PDF_LAYOUT_OVERRIDES = BUILD_DIR / layout_overrides.PDF_OVERRIDE_NAME
BASE_CSS_FILES = [CSS_SHARED, CSS_EPUB]
IASP_FILTER = TOOLING_ROOT / "lua" / "iasp-semantics.lua"
CATALOG_COLLECTIONS_FILTER = TOOLING_ROOT / "lua" / "catalog_collections.lua"
CHAPTER_FILTER = TOOLING_ROOT / "lua" / "chapter_headings.lua"
TITLE_FROM_HEADING_FILTER = TOOLING_ROOT / "lua" / "title_from_first_heading.lua"
RUNNING_HEAD_FILTER = TOOLING_ROOT / "lua" / "running_headers.lua"
METADATA_JSON = ROOT / "metadata.json"
METADATA_YAML = ROOT / "metadata.yaml"
BUILD_PROFILES_FILE = ROOT / "build-profiles.json"
METADATA_GENERATOR = TOOLING_ROOT / "scripts" / "generate_metadata_json.py"
BUILD_METADATA_JSON = BUILD_DIR / "build-metadata.json"
BUILD_STATE_FILE = ROOT / ".build-info.json"
TAGGER    = TOOLING_ROOT / "tag_by_dir.py"   # our semantic-tagging helper
LATEX_DIR = TOOLING_ROOT / "latex"
PDF_HEADER = LATEX_DIR / "pdf-header.tex"
BLOCKQUOTE_STYLE = LATEX_DIR / "box-blockquote.tex"
SENTINEL_HEADER = LATEX_DIR / "sentinel-logging.tex"
TOC_GENERATOR = TOOLING_ROOT / "scripts" / "generate_toc.py"
ORDER_SNAPSHOT_GENERATOR = TOOLING_ROOT / "scripts" / "generate_order_snapshot.py"
COVER_IMAGE = ROOT / "cover.jpg"
QUOTE_FIXTURE = ROOT / "tests" / "quote-playground.md"
CHAPTER_OUTPUT_DIR = BUILD_DIR / "chapters"
CONTAINER_WRAPPERS_JSON = BUILD_DIR / "container-wrappers.json"
PRE_BUILD_HOOKS_DIR = ROOT / "scripts" / "pre_build_hooks"

EPUB_OUT = BUILD_DIR / "The-Struggle-Against-Dehumanization.epub"
PDF_OUT_SCREEN = BUILD_DIR / "The-Struggle-Against-Dehumanization.pdf"
PDF_OUT_PRINT  = BUILD_DIR / "The-Struggle-Against-Dehumanization-print.pdf"
DOCX_OUT = BUILD_DIR / "The-Struggle-Against-Dehumanization.docx"
RTF_OUT = BUILD_DIR / "The-Struggle-Against-Dehumanization.rtf"
QUOTE_PLAYGROUND_PDF = BUILD_DIR / "quote-playground.pdf"
QUOTE_PLAYGROUND_TEX = BUILD_DIR / "quote-playground.tex"
EPUBCHECK_PROFILE = "EPUB_3.3"
PDF_PAGE_COUNT_CACHE = BUILD_DIR / "pdf-page-counts.json"

DEFAULT_OUTPUT_BASENAME = "The-Struggle-Against-Dehumanization"

PANDOC_MARKDOWN_INPUT = "markdown+fancy_lists+fenced_divs+header_attributes+link_attributes+smart"

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


def _config_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


PREPROCESS_SETTINGS = _config_section("preprocessor")
TOC_SETTINGS = _config_section("toc")
LAYOUT_SETTINGS = _config_section("layout")
TASK_SETTINGS = _config_section("tasks")
PREPROCESS_ACTIVE = preprocess_config.is_enabled()
TOC_ENABLED = _config_bool(TOC_SETTINGS.get("enabled"), True)
TOC_INCLUDE_APPENDICES = _config_bool(TOC_SETTINGS.get("include_appendices"), True)
TOC_MAX_DEPTH = _config_int(TOC_SETTINGS.get("max_depth"), 3, minimum=1, maximum=6)


def _resolve_annex_settings() -> dict[str, Any]:
    layout_annex = LAYOUT_SETTINGS.get("annexes")
    layout_annex = layout_annex if isinstance(layout_annex, dict) else {}
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
class BuildProfile:
    name: str
    order_file: Path
    metadata_files: list[Path]
    cover_image: Path | None
    output_basename: str


PROFILE: BuildProfile | None = None
PROFILE_METADATA_FILES: list[Path] = [METADATA_JSON, METADATA_YAML]


def _resolve_profile_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def _read_profile_definitions() -> dict[str, dict[str, Any]]:
    if not BUILD_PROFILES_FILE.exists():
        return {}

    try:
        raw = json.loads(BUILD_PROFILES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"-- Warning: Unable to load build profiles from {BUILD_PROFILES_FILE}: {exc}")
        return {}

    if not isinstance(raw, dict):
        print(f"-- Warning: build profiles file must contain a JSON object (found {type(raw).__name__})")
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            profiles[key] = value
    return profiles


def load_build_profile(profile_name: str | None) -> BuildProfile:
    definitions = _read_profile_definitions()
    resolved_name = profile_name or None

    if not definitions:
        if profile_name:
            print(f"!! Requested build profile '{profile_name}' but {BUILD_PROFILES_FILE} was not found or is empty.")
            sys.exit(1)
        return BuildProfile(
            name=profile_name or "default",
            order_file=BOOK_ORDER,
            metadata_files=[METADATA_JSON, METADATA_YAML],
            cover_image=COVER_IMAGE,
            output_basename=DEFAULT_OUTPUT_BASENAME,
        )

    if resolved_name is None:
        if "default" in definitions:
            resolved_name = "default"
        else:
            resolved_name = next(iter(definitions.keys()))

    entry = definitions.get(resolved_name)
    if entry is None:
        available = ", ".join(sorted(definitions.keys())) or "<none>"
        print(f"!! Unknown build profile '{resolved_name}'. Available profiles: {available}")
        sys.exit(1)

    order_value = entry.get("order_file") or entry.get("order") or "book-order.txt"
    order_path = _resolve_profile_path(str(order_value))

    metadata_value = entry.get("metadata")
    if metadata_value is None:
        metadata_files = [METADATA_JSON, METADATA_YAML]
    elif isinstance(metadata_value, list):
        metadata_files = [_resolve_profile_path(str(item)) for item in metadata_value]
    else:
        metadata_files = [_resolve_profile_path(str(metadata_value))]

    cover_value = entry.get("cover") or entry.get("cover_image")
    cover_path = _resolve_profile_path(str(cover_value)) if cover_value else None

    basename = str(entry.get("output_basename") or entry.get("output") or DEFAULT_OUTPUT_BASENAME)

    return BuildProfile(
        name=resolved_name,
        order_file=order_path,
        metadata_files=metadata_files,
        cover_image=cover_path,
        output_basename=basename,
    )


def apply_profile(profile: BuildProfile) -> None:
    global PROFILE, BOOK_ORDER, PROFILE_METADATA_FILES
    global COVER_IMAGE, EPUB_OUT, PDF_OUT_SCREEN, PDF_OUT_PRINT, DOCX_OUT, RTF_OUT

    PROFILE = profile
    BOOK_ORDER = profile.order_file
    PROFILE_METADATA_FILES = profile.metadata_files
    COVER_IMAGE = profile.cover_image

    output_root = BUILD_DIR
    if profile.name and profile.name != "default":
        output_root = ANNEX_OUTPUT_DIR

    output_root.mkdir(parents=True, exist_ok=True)

    basename = profile.output_basename or DEFAULT_OUTPUT_BASENAME
    EPUB_OUT = output_root / f"{basename}.epub"
    PDF_OUT_SCREEN = output_root / f"{basename}.pdf"
    PDF_OUT_PRINT = output_root / f"{basename}-print.pdf"
    DOCX_OUT = output_root / f"{basename}.docx"
    RTF_OUT = output_root / f"{basename}.rtf"

NAV_LINK_PATTERN = re.compile(r'(?P<prefix>href=")text/#(?P<ident>[^"#]+)(?P<suffix>")')
NCX_LINK_PATTERN = re.compile(r'(?P<prefix>content src=")text/#(?P<ident>[^"#]+)(?P<suffix>")')
ID_ATTR_PATTERN = re.compile(r'id="([^"\s]+)"')
CITATION_PATTERN = re.compile(r'(?<![A-Za-z0-9_])@([A-Za-z0-9][\w:.-]*)')
BIB_ENTRY_PATTERN = re.compile(r'@\w+\s*\{\s*([^,\s]+)', re.MULTILINE)

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>'
NAV_DOCTYPE = "<!DOCTYPE html>"
XHTML = f"{{{XHTML_NS}}}"
EPUB = f"{{{EPUB_NS}}}"
NCX = f"{{{NCX_NS}}}"


@dataclass
class NavHeading:
    level: int
    identifier: str
    lead_text: str
    children: list[ET.Element]
    plain_text: str
    subsections: list["NavHeading"]


@dataclass
class HeadingContent:
    lead_text: str
    children: list[ET.Element]
    plain_text: str
    subheadings: list[NavHeading]

BIBLIOGRAPHY_FILES = [ROOT / "references.bib"]
SPECIAL_CITATION_KEYS = {"*", "-"}
CITEPROC_MISSING_PATTERN = re.compile(r"Citeproc: citation\s+([^\s]+)\s+not found")


def stage_cover_image() -> None:
    """Copy cover.jpg into build/ so XeLaTeX can resolve it."""
    if COVER_IMAGE is None:
        print("-- No cover image configured for this profile; skipping staging.")
        return

    if not COVER_IMAGE.exists():
        print(f"-- Cover image not found at {COVER_IMAGE}; skipping staging.")
        return

    target = BUILD_DIR / COVER_IMAGE.name
    try:
        shutil.copy2(COVER_IMAGE, target)
    except OSError as exc:
        print(f"!! Failed to copy cover.jpg into build/: {exc}")
        sys.exit(1)


def _report_missing_citations_from_stderr(stderr: str) -> None:
    if not stderr:
        return
    missing = sorted({match.group(1) for match in CITEPROC_MISSING_PATTERN.finditer(stderr)})
    if not missing:
        return
    preview = ", ".join(missing[:12])
    if len(missing) > 12:
        preview = f"{preview}, ..."
    print(
        "\n!! Citeproc reported missing citation keys:\n"
        f"   {preview}\n"
        "\nPlease add these keys to references.bib (or fix typos) before rebuilding."
    )
    sys.exit(1)


def run(cmd: list[str]) -> None:
    print("\n>> Running:", " ".join(str(c) for c in cmd))
    if cmd and cmd[0] == "pandoc":
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        _report_missing_citations_from_stderr(result.stderr or "")
    else:
        result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n!! Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def probe_pdf_page_count(pdf_path: Path) -> int | None:
    if not pdf_path.exists():
        return None
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if line.lower().startswith("pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                return None
    return None


def update_page_count_cache(pdf_path: Path, pdfmode: str | None) -> None:
    pages = probe_pdf_page_count(pdf_path)
    if pages is None:
        return

    key = (pdfmode or "screen").strip().lower() or "screen"

    cache: dict[str, Any]
    if PDF_PAGE_COUNT_CACHE.exists():
        try:
            cache = json.loads(PDF_PAGE_COUNT_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    else:
        cache = {}

    if not isinstance(cache, dict):
        cache = {}

    try:
        relative = pdf_path.relative_to(ROOT)
        source = str(relative)
    except ValueError:
        source = str(pdf_path)

    cache[key] = {
        "pages": pages,
        "source": source,
        "captured": datetime.now(timezone.utc).isoformat(),
    }

    try:
        PDF_PAGE_COUNT_CACHE.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def run_pre_build_hooks() -> None:
    """Execute optional Python scripts before each build to refresh assets."""

    if not PRE_BUILD_HOOKS_DIR.exists():
        return

    hooks = sorted(path for path in PRE_BUILD_HOOKS_DIR.glob("*.py") if path.is_file())
    if not hooks:
        return

    print("\n== Running pre-build hooks ==")
    for hook in hooks:
        run([sys.executable, str(hook)])


def ensure_build_dir() -> None:
    """Create the build/ directory if the user removed it."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)


def run_tag_by_dir() -> None:
    """
    Run tag_by_dir.py to ensure directory-based semantic wrappers
    are up to date before building.

    Safe to call on every build: tag_by_dir.py is idempotent.
    """
    if not TAGGER.exists():
        print("-- tag_by_dir.py not found; skipping semantic tagging step.")
        return

    print("\n== Ensuring directory-based semantic tags (tag_by_dir.py) ==")
    run([sys.executable, str(TAGGER)])


def run_generate_toc() -> None:
    """Ensure the front-matter TOC file is (re)generated.

    This is safe and idempotent; if the generator script is
    not present we simply skip the step.
    """
    if not TOC_GENERATOR.exists():
        print("-- generate_toc.py not found; skipping TOC generation.")
        return
        if not TOC_ENABLED:
            print("-- TOC generation disabled via config; skipping generate_toc.py")
            return

    print("\n== Regenerating front-matter Table of Contents (generate_toc.py) ==")
    run([sys.executable, str(TOC_GENERATOR)])


def run_generate_order_snapshot() -> None:
    """Emit a Markdown snapshot of the active book order for quick review."""

    if not ORDER_SNAPSHOT_GENERATOR.exists():
        print("-- generate_order_snapshot.py not found; skipping order snapshot.")
        return

    cmd = [sys.executable, str(ORDER_SNAPSHOT_GENERATOR), "--order", str(BOOK_ORDER)]
    if PROFILE and PROFILE.name:
        cmd += ["--profile", PROFILE.name]

    print("\n== Writing canonical book-order snapshot (generate_order_snapshot.py) ==")
    run(cmd)


def ensure_metadata_json() -> None:
    """Regenerate metadata.json from the canonical generator script."""

    if not METADATA_GENERATOR.exists():
        return

    print("\n== Refreshing metadata.json (generate_metadata_json.py) ==")
    run([sys.executable, str(METADATA_GENERATOR)])


def apply_layout_overrides_from_config() -> None:
    ensure_build_dir()
    try:
        layout_overrides.apply(BUILD_DIR)
    except Exception as exc:
        print(f"-- Warning: Unable to write layout overrides: {exc}")


def maybe_sync_vscode_tasks() -> None:
    try:
        vscode_tasks.sync()
    except Exception as exc:
        print(f"-- Warning: Unable to refresh VS Code tasks: {exc}")


def slugify_article_basename(label: str | None) -> str:
    """Produce a filesystem-friendly slug for standalone article outputs."""

    if not label:
        return "article"

    candidate = re.sub(r"\.(pdf|md|markdown)$", "", label.strip(), flags=re.IGNORECASE)
    candidate = candidate.replace(os.sep, "-").replace("\\", "-")
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate)
    candidate = candidate.strip("-_.")
    return candidate or "article"


def canonicalize_slug(label: str | None) -> str:
    return slugify_article_basename(label).lower() if label else ""


def detect_article_slug(source_path: Path) -> tuple[str | None, str]:
    try:
        rel = source_path.relative_to(ARTICLES_DIR)
    except ValueError:
        slug = canonicalize_slug(source_path.stem)
        return slug or None, "external"

    parts = rel.parts
    if not parts:
        slug = canonicalize_slug(source_path.stem)
        return slug or None, "external"

    if len(parts) == 1 and source_path.is_file():
        slug = canonicalize_slug(source_path.stem)
        return slug or None, "flat"

    slug = canonicalize_slug(parts[0])
    return slug or None, "nested"


def list_flat_article_sources() -> list[Path]:
    if not ARTICLES_DIR.exists():
        return []

    entries = [
        path
        for path in ARTICLES_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in ARTICLE_SUFFIXES
    ]
    return sorted(entries, key=lambda path: path.name.lower())


def flat_article_output_path(source_path: Path) -> Path:
    return ARTICLE_OUTPUT_DIR / f"{slugify_article_basename(source_path.stem)}.pdf"


def find_article_source(spec: str) -> Path:
    candidate_path = Path(spec)
    if candidate_path.exists():
        return candidate_path.resolve()

    slug = canonicalize_slug(spec)
    if not slug:
        print(f"!! Article source '{spec}' not found. Provide a path or slug under {ARTICLES_DIR}.")
        sys.exit(1)

    slug_dir = ARTICLES_DIR / slug

    if slug_dir.is_dir():
        print(
            "!! Articles must be single Markdown files in the top-level 'articles/' directory. "
            "Move multi-file content into an annex."
        )
        sys.exit(1)

    flat_candidates: list[Path] = []
    if ARTICLES_DIR.exists():
        for entry in ARTICLES_DIR.iterdir():
            if entry.is_file() and entry.suffix.lower() in {".md", ".markdown"}:
                if canonicalize_slug(entry.stem) == slug:
                    flat_candidates.append(entry)

    if len(flat_candidates) == 1:
        return flat_candidates[0].resolve()

    if len(flat_candidates) > 1:
        choices = "\n  - ".join(str(p.name) for p in flat_candidates)
        print(f"!! Multiple Markdown files matching slug '{slug}' found in {ARTICLES_DIR}:\n  - {choices}")
        sys.exit(1)

    print(f"!! Article source '{spec}' not found. Provide a path or slug under {ARTICLES_DIR}.")
    sys.exit(1)


def normalize_build_stage(stage: str | None) -> str:
    """Collapse arbitrary stage labels to 'draft' or 'final'."""

    if not stage:
        return "final"

    lowered = stage.strip().lower()
    return "draft" if lowered == "draft" else "final"

def _load_build_state() -> dict[str, object]:
    if not BUILD_STATE_FILE.exists():
        return {}

    try:
        raw = BUILD_STATE_FILE.read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}

def _read_declared_version() -> str | None:
    if not METADATA_YAML.exists():
        return None

    try:
        for line in METADATA_YAML.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("version:"):
                value = stripped.split(":", 1)[1].strip()
                if (value.startswith("\"") and value.endswith("\"")) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                return value
    except OSError:
        return None

    return None

def _read_git_metadata() -> dict[str, str] | None:
    git_exe = shutil.which("git")
    if not git_exe:
        return None

    try:
        result = subprocess.run(
            [git_exe, "log", "-1", "--pretty=%cI%n%s"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    output = result.stdout.strip()
    if not output:
        return None

    lines = output.splitlines()
    if not lines:
        return None

    commit_date = lines[0].strip()
    commit_subject = "".join(lines[1:]).strip() if len(lines) > 1 else ""

    info: dict[str, str] = {}
    if commit_date:
        info["last_commit_date"] = commit_date
    if commit_subject:
        info["last_commit_comment"] = commit_subject
    return info or None

def update_build_metadata(build_stage: str | None = None) -> None:
    """Increment the build counter and emit dynamic metadata for Pandoc."""

    ensure_build_dir()

    state = _load_build_state()
    try:
        last_number = int(state.get("build_number", 0))
    except (TypeError, ValueError):
        last_number = 0

    build_number = last_number + 1
    now_utc = datetime.now(timezone.utc)
    iso_utc = now_utc.isoformat().replace("+00:00", "Z")
    local_now = now_utc.astimezone()
    iso_local = local_now.isoformat()
    local_date = local_now.strftime("%Y-%m-%d")
    local_time = local_now.strftime("%H:%M:%S %Z")

    new_state = {
        "build_number": build_number,
        "build_timestamp": iso_utc,
    }

    try:
        BUILD_STATE_FILE.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"-- Warning: Unable to persist build state at {BUILD_STATE_FILE}: {exc}")

    normalized_stage = normalize_build_stage(build_stage)

    glyph_palette_choice = LAYOUT_SETTINGS.get("glyph_background_palette")
    badge_palette_choice = LAYOUT_SETTINGS.get("badge_background_palette")
    glyph_luma_raw = _config_float(
        LAYOUT_SETTINGS.get("glyph_background_luma_offset"), 0.0, minimum=-0.5, maximum=0.5
    )
    badge_luma_raw = _config_float(
        LAYOUT_SETTINGS.get("badge_background_luma_offset"), 0.0, minimum=-0.5, maximum=0.5
    )
    glyph_luma_offset, glyph_palette_name = select_luma_offset("glyph", glyph_palette_choice, glyph_luma_raw)
    badge_luma_offset, badge_palette_name = select_luma_offset("badge", badge_palette_choice, badge_luma_raw)

    dynamic_metadata: dict[str, object] = {
        "build-number": build_number,
        "build-timestamp": iso_utc,
        "build-timestamp-local": iso_local,
        "build-date": local_date,
        "build-time": local_time,
        "build-stage": normalized_stage,
        "draft-build": normalized_stage == "draft",
        "final-build": normalized_stage != "draft",
        "layout-named-block-badges": _config_bool(LAYOUT_SETTINGS.get("named_block_badges"), False),
        "layout-named-note-badges": _config_bool(LAYOUT_SETTINGS.get("named_note_badges"), False),
        "layout-glyph-background-luma-offset": glyph_luma_offset,
        "layout-badge-background-luma-offset": badge_luma_offset,
        "layout-glyph-background-force-white": _config_bool(
            LAYOUT_SETTINGS.get("glyph_background_force_white"), False
        ),
        "layout-table-fullpage-min-rows": _config_int(
            LAYOUT_SETTINGS.get("table_fullpage_min_rows"), 0, minimum=0, maximum=100
        ),
        "layout-table-compact-min-cols": _config_int(
            LAYOUT_SETTINGS.get("table_compact_min_cols"), 0, minimum=0, maximum=50
        ),
    }

    if glyph_palette_name:
        dynamic_metadata["layout-glyph-background-palette"] = glyph_palette_name
    if badge_palette_name:
        dynamic_metadata["layout-badge-background-palette"] = badge_palette_name

    if PROFILE:
        dynamic_metadata["build-profile"] = PROFILE.name

    declared_version = _read_declared_version()
    if declared_version:
        dynamic_metadata["version-with-build"] = f"{declared_version} (build {build_number})"

    git_info = _read_git_metadata()
    if git_info:
        if "last_commit_date" in git_info:
            dynamic_metadata["last-commit-date"] = git_info["last_commit_date"]
        if "last_commit_comment" in git_info:
            dynamic_metadata["last-commit-comment"] = git_info["last_commit_comment"]

    try:
        BUILD_METADATA_JSON.write_text(
            json.dumps(dynamic_metadata, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"-- Warning: Unable to write build metadata file {BUILD_METADATA_JSON}: {exc}")


def append_metadata_files(cmd: list[str]) -> None:
    """Attach any available metadata files to a Pandoc command."""

    sources: list[Path | None] = [BUILD_METADATA_JSON, CONTAINER_WRAPPERS_JSON]
    sources.extend(PROFILE_METADATA_FILES)

    def _metadata_has_bibliography(paths: list[Path]) -> bool:
        for path in paths:
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lowered = text.lower()
            if "bibliography:" in lowered or "bibliography=" in lowered:
                return True
        return False

    seen: set[Path] = set()
    for meta in sources:
        if meta is None:
            continue
        try:
            resolved = meta.resolve()
        except OSError:
            resolved = meta
        if resolved in seen:
            continue
        seen.add(resolved)
        if meta.exists():
            cmd += ["--metadata-file", str(meta)]

    if PROFILE and PROFILE.name and PROFILE.name != "default":
        if not _metadata_has_bibliography(PROFILE_METADATA_FILES):
            if BIBLIOGRAPHY_FILES:
                cmd += ["--metadata", f"bibliography:{BIBLIOGRAPHY_FILES[0]}"]


def iter_css_files() -> list[Path]:
    files = list(BASE_CSS_FILES)
    if CSS_OVERRIDE.exists():
        files.append(CSS_OVERRIDE)
    return files


def append_catalog_collections_filter(cmd: list[str]) -> None:
    """Attach the catalog collections Lua filter when available."""

    if not PREPROCESS_ACTIVE:
        return

    if not CATALOG_COLLECTIONS_FILTER.exists():
        return

    config_path = preprocess_config.resolve_config_path()
    if not config_path.exists():
        print(f"-- Warning: Preprocess config not found at {config_path}; skipping catalog filter.")
        return

    cmd += ["--lua-filter", str(CATALOG_COLLECTIONS_FILTER)]
    cmd += ["-M", f"catalog_collections.config={config_path}"]


def append_semantic_filters(cmd: list[str], *, enabled: bool) -> None:
    """Attach chapter-normalization + semantic filters when requested."""

    if not enabled:
        return

    for filter_path in (
        TITLE_FROM_HEADING_FILTER,
        CHAPTER_FILTER,
        IASP_FILTER,
        RUNNING_HEAD_FILTER,
    ):
        if filter_path.exists():
            cmd += ["--lua-filter", str(filter_path)]


def enable_citations(cmd: list[str]) -> None:
    """Ensure citeproc is enabled so bibliography data is rendered."""

    if "--citeproc" not in cmd:
        cmd.append("--citeproc")


def collect_bibliography_keys() -> set[str]:
    keys: set[str] = set()
    for bib in BIBLIOGRAPHY_FILES:
        if not bib.exists():
            continue
        try:
            text = bib.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in BIB_ENTRY_PATTERN.finditer(text):
            keys.add(match.group(1).strip())
    return keys


def verify_citations(input_paths: list[str]) -> None:
    bib_keys = collect_bibliography_keys()
    if not bib_keys:
        print("-- Warning: No bibliography keys found; skipping citation validation.")
        return

    reported_keys: set[str] = set()
    errors: list[tuple[str, int, str, str]] = []

    for path_str in input_paths:
        path = Path(path_str)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        fence_active = False
        fence_token = None
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                token = stripped[:3]
                if fence_active and token == fence_token:
                    fence_active = False
                    fence_token = None
                else:
                    fence_active = True
                    fence_token = token
                continue

            if fence_active:
                continue

            for match in CITATION_PATTERN.finditer(line):
                key = match.group(1)
                if key in SPECIAL_CITATION_KEYS:
                    continue
                if key in bib_keys or key in reported_keys:
                    continue
                reported_keys.add(key)
                try:
                    rel_path = str(path.relative_to(ROOT))
                except ValueError:
                    rel_path = str(path)
                errors.append((rel_path, lineno, key, line.strip()))

    if errors:
        print("\n!! Missing citation keys detected:")
        for rel_path, lineno, key, context in errors:
            print(f"   - {key} → {rel_path}:{lineno} :: {context}")
        print("\nPlease add these keys to references.bib (or fix typos) before rebuilding.")
        sys.exit(1)


def maybe_run_epubcheck(epub_path: Path) -> None:
    """Run epubcheck if the CLI or JAR is available."""

    if not epub_path.exists():
        return

    if os.environ.get("SKIP_EPUBCHECK") == "1":
        print("-- SKIP_EPUBCHECK=1; skipping epubcheck validation.")
        return

    profile = os.environ.get("EPUBCHECK_PROFILE", EPUBCHECK_PROFILE)
    cmd: list[str] | None = None

    exe = shutil.which("epubcheck")
    if exe:
        cmd = [exe, str(epub_path)]
    else:
        jar_hint = os.environ.get("EPUBCHECK_JAR")
        if jar_hint:
            jar_path = Path(jar_hint).expanduser()
            if not jar_path.exists():
                print(f"-- EPUBCHECK_JAR is set but not found at {jar_path}; skipping epubcheck.")
                return
            java = shutil.which("java")
            if not java:
                print("-- java executable not found; cannot run EPUBCHECK_JAR.")
                return
            cmd = [java, "-jar", str(jar_path), str(epub_path)]

    if not cmd:
        print("-- epubcheck not found; skipping EPUB validation.")
        return

    if profile:
        cmd += ["--profile", profile]

    print("\n== Validating EPUB with epubcheck ==")
    run(cmd)


def _collect_epub_id_targets(zf: zipfile.ZipFile) -> dict[str, str]:
    targets: dict[str, str] = {}
    for item in zf.infolist():
        if not item.filename.startswith("EPUB/text/"):
            continue
        if not item.filename.endswith(".xhtml"):
            continue

        try:
            data = zf.read(item.filename).decode("utf-8")
        except UnicodeDecodeError:
            continue

        rel_path = item.filename.replace("EPUB/", "", 1)
        for match in ID_ATTR_PATTERN.finditer(data):
            targets.setdefault(match.group(1), rel_path)
    return targets


def _rewrite_internal_refs(
    text: str,
    pattern: re.Pattern,
    id_targets: dict[str, str],
) -> tuple[str, int, set[str]]:
    missing: set[str] = set()

    def repl(match: re.Match) -> str:
        ident = match.group("ident")
        target = id_targets.get(ident)
        if not target:
            missing.add(ident)
            return match.group(0)
        return f"{match.group('prefix')}{target}#{ident}{match.group('suffix')}"

    updated, count = pattern.subn(repl, text)
    return updated, count, missing


def _rewrite_epub_archive(
    source: Path,
    *,
    nav_text: str | None,
    toc_text: str | None,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "patched.epub"
        with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(tmp_path, "w") as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if nav_text is not None and item.filename == "EPUB/nav.xhtml":
                    data = nav_text.encode("utf-8")
                elif toc_text is not None and item.filename == "EPUB/toc.ncx":
                    data = toc_text.encode("utf-8")

                info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
                info.compress_type = item.compress_type
                info.comment = item.comment
                info.extra = item.extra
                info.internal_attr = item.internal_attr
                info.external_attr = item.external_attr
                info.create_system = item.create_system
                info.flag_bits = item.flag_bits
                dst.writestr(info, data)

        shutil.move(tmp_path, source)


def _extract_spine_hrefs(zf: zipfile.ZipFile) -> list[str]:
    try:
        data = zf.read("EPUB/content.opf").decode("utf-8")
    except KeyError:
        return []

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []

    ns = {"opf": "http://www.idpf.org/2007/opf"}
    manifest: dict[str, str] = {}
    for item in root.findall(".//opf:manifest/opf:item", ns):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        if item_id and href:
            manifest[item_id] = href

    hrefs: list[str] = []
    for itemref in root.findall(".//opf:spine/opf:itemref", ns):
        idref = itemref.attrib.get("idref")
        if not idref:
            continue
        href = manifest.get(idref)
        if href:
            hrefs.append(href)
    return hrefs


def _is_chapter_href(href: str) -> bool:
    return href.startswith("text/ch")


def _insert_before(parent: ET.Element, new_node: ET.Element, ref_node: ET.Element) -> None:
    children = list(parent)
    try:
        index = children.index(ref_node)
    except ValueError:
        parent.append(new_node)
        return
    parent.insert(index, new_node)


def _heading_level_from_tag(tag: str) -> int | None:
    if not isinstance(tag, str):
        return None

    local = tag
    if tag.startswith(XHTML):
        local = tag[len(XHTML) :]
    if not local.startswith("h"):
        return None
    suffix = local[1:]
    if not suffix.isdigit():
        return None
    level = int(suffix)
    if 1 <= level <= 6:
        return level
    return None


def _resolve_heading_identifier(
    elem: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> str | None:
    ident = elem.get("id")
    if ident:
        return ident

    parent = parent_map.get(elem)
    visited = 0
    while parent is not None and visited < 6:
        ident = parent.get("id")
        if ident:
            return ident
        parent = parent_map.get(parent)
        visited += 1
    return None


def _populate_anchor_from_heading(anchor: ET.Element, heading: HeadingContent | NavHeading) -> None:
    for child in list(anchor):
        anchor.remove(child)
    anchor.text = None

    lead_text = getattr(heading, "lead_text", "") or ""
    if lead_text:
        anchor.text = lead_text

    for child in getattr(heading, "children", []):
        anchor.append(copy.deepcopy(child))
    has_children = len(list(anchor)) > 0
    if (anchor.text is None or anchor.text.strip() == "") and not has_children and getattr(heading, "plain_text", ""):
        anchor.text = heading.plain_text


def _append_nav_children(parent_li: ET.Element, base_href: str, nodes: list[NavHeading]) -> None:
    if not nodes:
        return

    child_ol = ET.Element(f"{XHTML}ol", {"class": "toc"})
    for node in nodes:
        child_li = ET.Element(f"{XHTML}li")
        anchor = ET.SubElement(child_li, f"{XHTML}a", {"href": f"{base_href}#{node.identifier}"})
        _populate_anchor_from_heading(anchor, node)
        if node.subsections:
            _append_nav_children(child_li, base_href, node.subsections)
        child_ol.append(child_li)

    parent_li.append(child_ol)


def _append_ncx_children(
    parent_nav_point: ET.Element,
    base_href: str,
    nodes: list[NavHeading],
    id_counter: itertools.count,
) -> None:
    for node in nodes:
        child = ET.SubElement(parent_nav_point, f"{NCX}navPoint", {"id": f"navPoint-{next(id_counter)}"})
        nav_label = ET.SubElement(child, f"{NCX}navLabel")
        text_elem = ET.SubElement(nav_label, f"{NCX}text")
        text_elem.text = node.plain_text or node.lead_text or node.identifier
        ET.SubElement(child, f"{NCX}content", {"src": f"{base_href}#{node.identifier}"})
        if node.subsections:
            _append_ncx_children(child, base_href, node.subsections, id_counter)


REDUNDANT_NAV_TITLES = {"table of contents"}
NAV_TITLE_COMMENT_PREFIX = "nav-title:"


def _extract_nav_title_marker(root: ET.Element) -> str | None:
    for elem in root.iter():
        if elem.tag is ET.Comment:
            text = (elem.text or "").strip()
            if text.lower().startswith(NAV_TITLE_COMMENT_PREFIX):
                return text[len(NAV_TITLE_COMMENT_PREFIX):].strip()
        nav_attr = (elem.attrib.get("data-nav-title") or "").strip()
        if nav_attr:
            return nav_attr
    return None


def _serialize_nav_tree(root: ET.Element) -> str:
    return "\n".join([XML_DECL, NAV_DOCTYPE, ET.tostring(root, encoding="unicode", method="xml")])


def _serialize_xml_tree(root: ET.Element) -> str:
    return "\n".join([XML_DECL, ET.tostring(root, encoding="unicode", method="xml")])


def _load_heading_content(
    zf: zipfile.ZipFile,
    href: str,
    cache: dict[str, HeadingContent | None],
) -> HeadingContent | None:
    if href in cache:
        return cache[href]

    try:
        data = zf.read(f"EPUB/{href}").decode("utf-8")
    except KeyError:
        cache[href] = None
        return None

    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    try:
        root = ET.fromstring(data, parser=parser)
    except ET.ParseError:
        cache[href] = None
        return None

    ET.register_namespace("", XHTML_NS)
    ET.register_namespace("epub", EPUB_NS)
    parent_map: dict[ET.Element, ET.Element] = {
        child: parent
        for parent in root.iter()
        for child in list(parent)
    }
    nav_title = _extract_nav_title_marker(root)
    main_heading: HeadingContent | None = None
    subheadings: list[NavHeading] = []
    stack: list[tuple[int, list[NavHeading]]] = [(1, subheadings)]

    for elem in root.iter():
        level = _heading_level_from_tag(elem.tag)
        if level is None:
            continue

        identifier = _resolve_heading_identifier(elem, parent_map)
        lead_text = elem.text or ""
        child_nodes = [copy.deepcopy(child) for child in elem]
        plain_text = "".join(elem.itertext()).strip() or identifier or Path(href).stem

        if level == 1:
            if main_heading is None:
                main_heading = HeadingContent(
                    lead_text=lead_text,
                    children=child_nodes,
                    plain_text=plain_text,
                    subheadings=subheadings,
                )
            stack = [(1, subheadings)]
            continue

        if level < 2 or level > TOC_MAX_DEPTH:
            continue
        if not identifier:
            continue

        nav_heading = NavHeading(
            level=level,
            identifier=identifier,
            lead_text=lead_text,
            children=child_nodes,
            plain_text=plain_text,
            subsections=[],
        )

        while stack and level <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack = [(1, subheadings)]

        stack[-1][1].append(nav_heading)
        stack.append((level, nav_heading.subsections))

    if main_heading is None and subheadings:
        promoted = subheadings.pop(0)
        merged_children = list(promoted.subsections)
        merged_children.extend(subheadings)
        main_heading = HeadingContent(
            lead_text=promoted.lead_text,
            children=promoted.children,
            plain_text=promoted.plain_text,
            subheadings=merged_children,
        )

    if main_heading is None and nav_title:
        main_heading = HeadingContent(
            lead_text=nav_title,
            children=[],
            plain_text=nav_title,
            subheadings=subheadings,
        )

    if main_heading is None:
        main_heading = HeadingContent(
            lead_text="",
            children=[],
            plain_text=Path(href).stem,
            subheadings=subheadings,
        )

    cache[href] = main_heading
    return main_heading


def _format_missing_targets(hrefs: list[str]) -> str:
    if len(hrefs) <= 3:
        return ", ".join(hrefs)
    preview = ", ".join(hrefs[:3])
    return f"{preview}..."


def _augment_nav_with_missing_chapters(
    nav_text: str,
    zf: zipfile.ZipFile,
    spine_hrefs: list[str],
    heading_cache: dict[str, HeadingContent | None],
) -> tuple[str, int]:
    if not nav_text:
        return nav_text, 0

    ET.register_namespace("", XHTML_NS)
    ET.register_namespace("epub", EPUB_NS)
    try:
        root = ET.fromstring(nav_text)
    except ET.ParseError:
        return nav_text, 0

    nav_elem = root.find(f".//{XHTML}nav[@{EPUB}type='toc']")
    if nav_elem is None:
        return nav_text, 0

    ol = nav_elem.find(f"{XHTML}ol")
    if ol is None:
        return nav_text, 0

    existing: dict[str, ET.Element] = {}
    original_children = [ET.tostring(li, encoding="unicode", method="xml") for li in list(ol)]
    max_id = 0
    for li in list(ol):
        anchor = li.find(f"{XHTML}a")
        if anchor is None:
            continue
        href = anchor.get("href") or ""
        base_href = href.split("#", 1)[0]
        if base_href:
            existing.setdefault(base_href, li)
        ident = li.get("id")
        if ident:
            match = re.search(r"(\d+)$", ident)
            if match:
                max_id = max(max_id, int(match.group(1)))

    present = set(existing.keys())
    chapter_hrefs = [href for href in spine_hrefs if _is_chapter_href(href)]
    id_counter = itertools.count(max_id + 1)
    new_children: list[ET.Element] = []
    missing_titles: list[str] = []

    for href in chapter_hrefs:
        heading = _load_heading_content(zf, href, heading_cache)
        next_id = next(id_counter)
        li: ET.Element
        if heading:
            li = ET.Element(f"{XHTML}li", {"id": f"toc-li-{next_id}"})
            anchor = ET.SubElement(li, f"{XHTML}a", {"href": href})
            _populate_anchor_from_heading(anchor, heading)
            heading_text = (heading.plain_text or "").strip().lower()
            if heading_text not in REDUNDANT_NAV_TITLES:
                _append_nav_children(li, href, heading.subheadings)
        else:
            missing_titles.append(href)
            source = existing.get(href)
            if source is not None:
                li = copy.deepcopy(source)
            else:
                li = ET.Element(f"{XHTML}li")
            li.set("id", f"toc-li-{next_id}")
            anchor = li.find(f"{XHTML}a")
            if anchor is None:
                anchor = ET.SubElement(li, f"{XHTML}a", {"href": href})
            if not anchor.get("href"):
                anchor.set("href", href)
            if "".join(anchor.itertext()).strip() == "":
                anchor.text = href
        new_children.append(li)

    if not new_children:
        return nav_text, 0

    new_serialized = [ET.tostring(li, encoding="unicode", method="xml") for li in new_children]
    if original_children == new_serialized:
        if missing_titles:
            print(
                f"-- Warning: unable to infer nav titles for {len(missing_titles)} chapters: {_format_missing_targets(missing_titles)}"
            )
        return nav_text, 0

    for child in list(ol):
        ol.remove(child)
    for li in new_children:
        ol.append(li)

    if missing_titles:
        print(
            f"-- Warning: unable to infer nav titles for {len(missing_titles)} chapters: {_format_missing_targets(missing_titles)}"
        )

    added = len([href for href in chapter_hrefs if href not in present])
    return _serialize_nav_tree(root), added


def _augment_ncx_with_missing_chapters(
    toc_text: str,
    zf: zipfile.ZipFile,
    spine_hrefs: list[str],
    heading_cache: dict[str, HeadingContent | None],
) -> tuple[str, int]:
    if not toc_text:
        return toc_text, 0

    ET.register_namespace("", NCX_NS)
    try:
        root = ET.fromstring(toc_text)
    except ET.ParseError:
        return toc_text, 0

    nav_map = root.find(f"{NCX}navMap")
    if nav_map is None:
        return toc_text, 0

    existing: dict[str, ET.Element] = {}
    original_children = [ET.tostring(nav_point, encoding="unicode", method="xml") for nav_point in list(nav_map)]
    max_id = 0
    for nav_point in list(nav_map):
        content = nav_point.find(f"{NCX}content")
        if content is None:
            continue
        src = content.get("src") or ""
        base_href = src.split("#", 1)[0]
        if base_href:
            existing.setdefault(base_href, nav_point)
        ident = nav_point.get("id")
        if ident:
            match = re.search(r"(\d+)$", ident)
            if match:
                max_id = max(max_id, int(match.group(1)))

    present = set(existing.keys())
    chapter_hrefs = [href for href in spine_hrefs if _is_chapter_href(href)]
    id_counter = itertools.count(max_id + 1)
    new_points: list[ET.Element] = []
    missing_titles: list[str] = []

    for href in chapter_hrefs:
        heading = _load_heading_content(zf, href, heading_cache)
        next_id = next(id_counter)
        if heading:
            nav_point = ET.Element(f"{NCX}navPoint", {"id": f"navPoint-{next_id}"})
            nav_label = ET.SubElement(nav_point, f"{NCX}navLabel")
            text_elem = ET.SubElement(nav_label, f"{NCX}text")
            text_elem.text = heading.plain_text or Path(href).stem
            ET.SubElement(nav_point, f"{NCX}content", {"src": href})
            heading_text = (heading.plain_text or "").strip().lower()
            if heading_text not in REDUNDANT_NAV_TITLES:
                _append_ncx_children(nav_point, href, heading.subheadings, id_counter)
        else:
            missing_titles.append(href)
            source = existing.get(href)
            if source is not None:
                nav_point = copy.deepcopy(source)
            else:
                nav_point = ET.Element(f"{NCX}navPoint")
            nav_point.set("id", f"navPoint-{next_id}")
            nav_label = nav_point.find(f"{NCX}navLabel")
            if nav_label is None:
                nav_label = ET.SubElement(nav_point, f"{NCX}navLabel")
            text_elem = nav_label.find(f"{NCX}text")
            if text_elem is None:
                text_elem = ET.SubElement(nav_label, f"{NCX}text")
            if not (text_elem.text or "").strip():
                text_elem.text = href
            content = nav_point.find(f"{NCX}content")
            if content is None:
                content = ET.SubElement(nav_point, f"{NCX}content")
            content.set("src", href)
        new_points.append(nav_point)

    if not new_points:
        return toc_text, 0

    new_serialized = [ET.tostring(nav_point, encoding="unicode", method="xml") for nav_point in new_points]
    if original_children == new_serialized:
        if missing_titles:
            print(
                f"-- Warning: unable to infer NCX titles for {len(missing_titles)} chapters: {_format_missing_targets(missing_titles)}"
            )
        return toc_text, 0

    for child in list(nav_map):
        nav_map.remove(child)
    for nav_point in new_points:
        nav_map.append(nav_point)

    if missing_titles:
        print(
            f"-- Warning: unable to infer NCX titles for {len(missing_titles)} chapters: {_format_missing_targets(missing_titles)}"
        )

    added = len([href for href in chapter_hrefs if href not in present])
    return _serialize_xml_tree(root), added


def repair_epub_navigation(epub_path: Path) -> None:
    """Ensure nav.xhtml and toc.ncx never reference fragment-only paths."""

    if not epub_path.exists():
        return

    nav_updated: str | None = None
    toc_updated: str | None = None
    nav_fixes = toc_fixes = 0
    nav_added = toc_added = 0
    nav_changed = toc_changed = False
    missing_ids: set[str] = set()

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            try:
                nav_raw = zf.read("EPUB/nav.xhtml").decode("utf-8")
            except KeyError:
                nav_raw = None

            try:
                toc_raw = zf.read("EPUB/toc.ncx").decode("utf-8")
            except KeyError:
                toc_raw = None

            if nav_raw is None and toc_raw is None:
                return

            id_targets = _collect_epub_id_targets(zf)
            spine_hrefs = _extract_spine_hrefs(zf)
            heading_cache: dict[str, HeadingContent | None] = {}

            nav_updated = nav_raw
            toc_updated = toc_raw

            if nav_raw:
                nav_updated, nav_fixes, missing = _rewrite_internal_refs(nav_raw, NAV_LINK_PATTERN, id_targets)
                missing_ids.update(missing)
                nav_updated, nav_added = _augment_nav_with_missing_chapters(
                    nav_updated,
                    zf,
                    spine_hrefs,
                    heading_cache,
                )
                nav_changed = nav_raw != nav_updated

            if toc_raw:
                toc_updated, toc_fixes, missing = _rewrite_internal_refs(toc_raw, NCX_LINK_PATTERN, id_targets)
                missing_ids.update(missing)
                toc_updated, toc_added = _augment_ncx_with_missing_chapters(
                    toc_updated,
                    zf,
                    spine_hrefs,
                    heading_cache,
                )
                toc_changed = toc_raw != toc_updated
    except zipfile.BadZipFile:
        print("-- Unable to inspect EPUB archive; skipping nav/toc repair.")
        return

    if (nav_fixes + toc_fixes + nav_added + toc_added) == 0 and not nav_changed and not toc_changed:
        if missing_ids:
            print(f"-- Warning: {len(missing_ids)} nav/toc ids missing chapter targets: {sorted(missing_ids)[:5]}...")
        return

    print("\n== Repairing EPUB navigation targets ==")
    if nav_fixes:
        print(f"-- Updated {nav_fixes} entries in nav.xhtml")
    if nav_added:
        print(f"-- Added {nav_added} missing chapters to nav.xhtml")
    if nav_changed and not (nav_fixes or nav_added):
        print("-- Rebuilt nav.xhtml to match spine order")
    if toc_fixes:
        print(f"-- Updated {toc_fixes} entries in toc.ncx")
    if toc_added:
        print(f"-- Added {toc_added} missing chapters to toc.ncx")
    if toc_changed and not (toc_fixes or toc_added):
        print("-- Rebuilt toc.ncx to match spine order")
    if missing_ids:
        print(f"-- Warning: unable to resolve targets for {len(missing_ids)} ids: {sorted(missing_ids)[:5]}...")

    _rewrite_epub_archive(epub_path, nav_text=nav_updated, toc_text=toc_updated)


def read_book_order() -> list[str]:
    """
    Read book-order.txt and return a list of input file paths (as strings),
    resolved relative to ROOT.

    - Ignores blank lines
    - Ignores lines starting with '#'
    """
    def _should_include_annexes() -> bool:
        if not ANNEX_INCLUDE_INSIDE:
            return False
        if PROFILE and PROFILE.name and PROFILE.name in ANNEX_IDS:
            return False
        # Skip annex inclusion if the current profile's order file is inside annexes/
        if PROFILE and PROFILE.order_file:
            annexes_dir = ROOT / "annexes"
            try:
                PROFILE.order_file.relative_to(annexes_dir)
                return False
            except ValueError:
                pass
        return True

    def _resolve_annex_order_paths() -> list[Path]:
        annex_ids = list(ANNEX_IDS)
        if not annex_ids:
            return _discover_annex_orders()

        definitions = _read_profile_definitions()
        resolved: list[Path] = []
        seen: set[Path] = set()

        discovered = {path.resolve() for path in _discover_annex_orders()}

        for annex_id in annex_ids:
            entry = definitions.get(annex_id)
            order_value = None
            if isinstance(entry, dict):
                order_value = entry.get("order_file") or entry.get("order")

            if order_value:
                order_path = _resolve_profile_path(str(order_value))
            else:
                order_path = _resolve_profile_path(str(annex_id))

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

    try:
        order_data = load_book_order(BOOK_ORDER)
    except FileNotFoundError:
        print(f"!! book-order.txt not found at {BOOK_ORDER}")
        sys.exit(1)

    if _should_include_annexes():
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
    inputs = flatten_nodes(order_nodes)
    write_wrapper_metadata(order_nodes, CONTAINER_WRAPPERS_JSON)
    if not inputs:
        print("!! No input files found in book-order.txt")
        sys.exit(1)

    return inputs


def build_epub(use_filter: bool = True) -> None:
    ensure_build_dir()
    run_tag_by_dir()
    run_generate_toc()
    run_generate_order_snapshot()
    ensure_metadata_json()
    inputs = read_book_order()
    verify_citations(inputs)

    cmd = ["pandoc", *inputs, f"--from={PANDOC_MARKDOWN_INPUT}"]

    append_metadata_files(cmd)

    # Attach cover image to EPUB if present
    if COVER_IMAGE and COVER_IMAGE.exists():
        cmd += ["--epub-cover-image", str(COVER_IMAGE)]

    cmd += ["--top-level-division=chapter"]

    for css in iter_css_files():
        if css.exists():
            cmd += ["--css", str(css)]

    append_catalog_collections_filter(cmd)

    append_semantic_filters(cmd, enabled=use_filter)

    enable_citations(cmd)

    cmd += ["-o", str(EPUB_OUT)]
    run(cmd)
    repair_epub_navigation(EPUB_OUT)
    maybe_run_epubcheck(EPUB_OUT)


def build_office_format(
    *,
    output_path: Path,
    writer: str | None,
    use_filter: bool = True,
) -> None:
    """Shared helper for Word-family outputs (DOCX/RTF)."""

    ensure_build_dir()
    run_tag_by_dir()
    run_generate_toc()
    run_generate_order_snapshot()
    ensure_metadata_json()
    inputs = read_book_order()
    verify_citations(inputs)

    cmd = ["pandoc", *inputs, f"--from={PANDOC_MARKDOWN_INPUT}", "--standalone", "--top-level-division=chapter"]

    append_metadata_files(cmd)

    if writer:
        cmd += ["-t", writer]

    append_catalog_collections_filter(cmd)

    append_semantic_filters(cmd, enabled=use_filter)

    enable_citations(cmd)

    cmd += ["-o", str(output_path)]
    run(cmd)


def build_docx(use_filter: bool = True) -> None:
    build_office_format(output_path=DOCX_OUT, writer="docx", use_filter=use_filter)


def build_rtf(use_filter: bool = True) -> None:
    build_office_format(output_path=RTF_OUT, writer="rtf", use_filter=use_filter)

def make_pdf_base_cmd(
    use_filter: bool = True,
    pdfmode: str | None = None,
    include_sentinel: bool = False,
) -> list[str]:
    """Build the common Pandoc command for PDF/LaTeX output.

    If ``pdfmode`` is provided (e.g. "screen" or "print"), it is passed
    through as a Pandoc variable so the LaTeX header can switch layouts.
    """
    run_tag_by_dir()
    run_generate_toc()
    run_generate_order_snapshot()
    ensure_metadata_json()
    inputs = read_book_order()
    verify_citations(inputs)

    cmd: list[str] = ["pandoc", *inputs, f"--from={PANDOC_MARKDOWN_INPUT}"]

    append_metadata_files(cmd)

    # Allow overriding pdfmode from the CLI (e.g., pdf-screen/pdf-print)
    if pdfmode:
        cmd += [f"--variable=pdfmode:{pdfmode}"]

    cmd += [
        "--top-level-division=chapter",
        "--pdf-engine=xelatex",  # ignored when -t latex, fine to leave
    ]

    headers = [BLOCKQUOTE_STYLE]

    if PDF_LAYOUT_OVERRIDES.exists():
        headers.append(PDF_LAYOUT_OVERRIDES)

    headers.append(PDF_HEADER)

    if include_sentinel:
        headers.append(SENTINEL_HEADER)

    for header in headers:
        if header.exists():
            cmd += ["--include-in-header", str(header)]

    append_catalog_collections_filter(cmd)

    append_semantic_filters(cmd, enabled=use_filter)

    enable_citations(cmd)

    return cmd

def build_pdf(use_filter: bool = True, pdfmode: str | None = None) -> None:
    """Build the final PDF via XeLaTeX.

    If a pdfmode is given, choose an output file name that makes the
    mode explicit ("-print" suffix for print), otherwise default to the
    screen-style name.
    """

    ensure_build_dir()
    stage_cover_image()
    cmd = make_pdf_base_cmd(use_filter, pdfmode=pdfmode, include_sentinel=True)

    if pdfmode == "print":
        out_path = PDF_OUT_PRINT
    else:
        # Treat anything else (including None) as screen-style output
        out_path = PDF_OUT_SCREEN

    cmd += ["-o", str(out_path)]
    run(cmd)
    update_page_count_cache(out_path, pdfmode or "screen")

def build_pdf_debug(use_filter: bool = True, pdfmode: str | None = None) -> None:
    """Build only debug.tex (LaTeX) for inspection."""
    ensure_build_dir()
    stage_cover_image()
    cmd = make_pdf_base_cmd(use_filter, pdfmode=pdfmode, include_sentinel=True)
    cmd += ["-t", "latex", "-o", str(DEBUG_TEX)]
    run(cmd)

def build_quote_playground() -> None:
    """Compile the tiny quote fixture for rapid iteration."""

    if not QUOTE_FIXTURE.exists():
        print(f"!! Quote fixture not found at {QUOTE_FIXTURE}")
        sys.exit(1)

    ensure_build_dir()

    base_cmd = [
        "pandoc",
        str(QUOTE_FIXTURE),
        "--pdf-engine=xelatex",
    ]

    for header in (BLOCKQUOTE_STYLE, PDF_HEADER):
        if header.exists():
            base_cmd += ["--include-in-header", str(header)]

    # Emit both PDF and the intermediate LaTeX for inspection.
    run([*base_cmd, "-o", str(QUOTE_PLAYGROUND_PDF)])
    run([*base_cmd, "-t", "latex", "-o", str(QUOTE_PLAYGROUND_TEX)])


def build_article_pdf(
    input_path: Path,
    output_hint: str | None = None,
    *,
    use_filter: bool = True,
    pdfmode: str | None = "screen",
    keep_bibliography: bool = False,
) -> None:
    """Render a standalone Markdown document into PDF without book-order prep."""

    ensure_build_dir()

    resolved = input_path if input_path.is_absolute() else (ROOT / input_path).resolve()

    if not resolved.exists():
        print(f"!! Article source not found: {resolved}")
        sys.exit(1)

    article_slug, article_layout = detect_article_slug(resolved)

    if article_layout == "nested":
        print(
            "!! Multi-file content under 'articles/' must be promoted to an annex before building."
        )
        sys.exit(1)

    hint_path: Path | None = None
    if output_hint:
        hint_path = Path(output_hint).expanduser()
        if not hint_path.is_absolute():
            hint_path = (ROOT / hint_path).resolve()

    default_dir = ARTICLE_OUTPUT_DIR

    if hint_path and hint_path.suffix.lower() == ".pdf":
        target_dir = hint_path.parent
        pdf_out = hint_path
    elif hint_path:
        target_dir = hint_path
        pdf_out = target_dir / f"{slugify_article_basename(resolved.stem)}.pdf"
    else:
        target_dir = default_dir
        pdf_out = target_dir / f"{slugify_article_basename(resolved.stem)}.pdf"

    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n== Building standalone article: {resolved}")
    verify_citations([str(resolved)])

    cmd = [
        "pandoc",
        str(resolved),
        "--standalone",
        "--top-level-division=chapter",
        "--pdf-engine=xelatex",
    ]

    append_metadata_files(cmd)
    article_title = resolved.stem.strip()
    metadata_flags = [
        "--metadata=article-build:true",
        "--metadata=frontmatter-enabled:false",
        "--metadata=backmatter-enabled:false",
        "--metadata=title:",
        "--metadata=subtitle:",
    ]
    if not keep_bibliography:
        metadata_flags.append("--metadata=suppress-bibliography:true")
    if article_slug:
        metadata_flags.append(f"--metadata=article-slug:{article_slug}")
    if article_title:
        safe_title = article_title.replace('"', '\\"')
        metadata_flags.append(f'--metadata=pdftitle:"{safe_title}"')
    cmd += metadata_flags
    cmd += ["--variable=titlepage:false", "--variable=book:false"]
    enable_citations(cmd)

    if pdfmode:
        cmd += [f"--variable=pdfmode:{pdfmode}"]

    for header in (BLOCKQUOTE_STYLE, PDF_HEADER):
        if header.exists():
            cmd += ["--include-in-header", str(header)]

    append_catalog_collections_filter(cmd)

    append_semantic_filters(cmd, enabled=use_filter)

    run([*cmd, "-o", str(pdf_out)])


def build_all_articles(use_filter: bool = True) -> None:
    sources = list_flat_article_sources()

    if not sources:
        print(f"-- No single-source articles found in {ARTICLES_DIR}")
        return

    ensure_build_dir()
    ARTICLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    built = skipped = 0

    for source in sources:
        output_path = flat_article_output_path(source)

        needs_build = True
        if output_path.exists():
            try:
                needs_build = output_path.stat().st_mtime < source.stat().st_mtime
            except OSError:
                needs_build = True

        if not needs_build:
            print(f"-- Skipping {source.name} (up to date)")
            skipped += 1
            continue

        print(f"\n-- Building article {source.name}")
        build_article_pdf(source, use_filter=use_filter)
        built += 1

    print(f"\n== Articles build complete ({built} built, {skipped} skipped) ==")


def build_single_markdown(
    input_path: Path,
    *,
    use_filter: bool = True,
    pdfmode: str | None = "screen",
    preprocess: bool = True,
    output_dir: Path | None = None,
) -> None:
    """Build one Markdown file into PDF and LaTeX for targeted debugging."""

    if preprocess:
        ensure_build_dir()
        run_tag_by_dir()
        run_generate_toc()
        run_generate_order_snapshot()
        ensure_metadata_json()
    else:
        ensure_build_dir()

    resolved = input_path if input_path.is_absolute() else (ROOT / input_path).resolve()

    if not resolved.exists():
        print(f"!! Chapter source not found: {resolved}")
        sys.exit(1)

    target_dir = output_dir or CHAPTER_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    slug = resolved.stem.replace(" ", "-")
    pdf_out = target_dir / f"{slug}.pdf"
    tex_out = target_dir / f"{slug}.tex"

    print(f"\n== Building standalone chapter: {resolved}")
    verify_citations([str(resolved)])

    base_cmd = [
        "pandoc",
        str(resolved),
        "--top-level-division=chapter",
        "--pdf-engine=xelatex",
    ]

    append_metadata_files(base_cmd)
    enable_citations(base_cmd)

    if pdfmode:
        base_cmd += [f"--variable=pdfmode:{pdfmode}"]

    for header in (BLOCKQUOTE_STYLE, PDF_HEADER):
        if header.exists():
            base_cmd += ["--include-in-header", str(header)]

    append_catalog_collections_filter(base_cmd)

    append_semantic_filters(base_cmd, enabled=use_filter)

    run([*base_cmd, "-o", str(pdf_out)])
    run([*base_cmd, "-t", "latex", "-o", str(tex_out)])


def build_all_chapters(use_filter: bool = True, pdfmode: str | None = "screen") -> None:
    """Iterate through book-order.txt and build each entry separately."""

    ensure_build_dir()
    run_tag_by_dir()
    run_generate_toc()
    run_generate_order_snapshot()
    ensure_metadata_json()

    inputs = read_book_order()
    total = len(inputs)
    if total == 0:
        return

    CHAPTER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n== Building {total} chapters individually ==")
    for idx, chapter_path in enumerate(inputs, start=1):
        print(f"\n-- [{idx}/{total}] {chapter_path}")
        build_single_markdown(
            Path(chapter_path),
            use_filter=use_filter,
            pdfmode=pdfmode,
            preprocess=False,
            output_dir=CHAPTER_OUTPUT_DIR,
        )


def _extract_profile_arg(args: list[str]) -> tuple[str | None, list[str]]:
    profile_name: str | None = None
    filtered: list[str] = []
    skip_next = False

    for idx, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue

        if arg == "--profile":
            if idx + 1 >= len(args):
                print("!! --profile requires a value")
                sys.exit(1)
            profile_name = args[idx + 1]
            skip_next = True
            continue

        if arg.startswith("--profile="):
            profile_name = arg.split("=", 1)[1]
            continue

        filtered.append(arg)

    return profile_name, filtered


def determine_build_stage(target: str) -> str:
    """Map the selected build target to a semantic stage label."""

    target = (target or "").strip().lower()
    if target.startswith("draft-"):
        return "draft"
    return "final"


def main() -> None:
    raw_args = sys.argv[1:]
    cli_profile, args = _extract_profile_arg(raw_args)

    env_profile = os.environ.get("BUILD_PROFILE", "").strip() or None
    requested_profile = cli_profile or env_profile

    profile = load_build_profile(requested_profile)
    apply_profile(profile)

    print(f"\n== Using build profile: {profile.name} ==")

    if not args:
        target = "all"
        extra: list[str] = []
    else:
        target = args[0].lower()
        extra = args[1:]

    build_stage = determine_build_stage(target)
    action = None

    if target == "epub":
        action = lambda: build_epub(use_filter=True)
    elif target == "pdf":
        action = lambda: build_pdf(use_filter=True, pdfmode="screen")
    elif target == "docx":
        action = lambda: build_docx(use_filter=True)
    elif target == "rtf":
        action = lambda: build_rtf(use_filter=True)
    elif target == "all":
        def action() -> None:
            build_epub(use_filter=True)
            build_pdf(use_filter=True)
    elif target == "draft-epub":
        action = lambda: build_epub(use_filter=True)
    elif target == "draft-pdf":
        action = lambda: build_pdf(use_filter=True)
    elif target == "draft-all":
        def action() -> None:
            build_epub(use_filter=True)
            build_pdf(use_filter=True)
    elif target == "pdf-debug":
        action = lambda: build_pdf_debug(use_filter=True)
    elif target == "pdf-screen":
        action = lambda: build_pdf(use_filter=True, pdfmode="screen")
    elif target == "pdf-print":
        action = lambda: build_pdf(use_filter=True, pdfmode="print")
    elif target == "pdf-debug-screen":
        action = lambda: build_pdf_debug(use_filter=True, pdfmode="screen")
    elif target == "pdf-debug-print":
        action = lambda: build_pdf_debug(use_filter=True, pdfmode="print")
    elif target == "quote-playground":
        action = build_quote_playground
    elif target == "chapter":
        if not extra:
            print("The 'chapter' target requires a file path.")
            sys.exit(1)
        chapter_path = Path(extra[0])
        action = lambda: build_single_markdown(chapter_path, use_filter=True)
    elif target == "article":
        if not extra:
            print("The 'article' target requires a Markdown path or slug.")
            sys.exit(1)
        article_path = find_article_source(extra[0])
        output_hint: str | None = None
        keep_bibliography = False
        remaining = extra[1:]
        for token in remaining:
            if token == "--with-bibliography":
                keep_bibliography = True
                continue
            if token == "--no-bibliography":
                keep_bibliography = False
                continue
            if token.startswith("--"):
                print(f"Unknown article option: {token}")
                sys.exit(1)
            if output_hint is None:
                output_hint = token
            else:
                print("Too many positional arguments for 'article'.")
                sys.exit(1)
        action = lambda: build_article_pdf(
            article_path,
            output_hint,
            use_filter=True,
            keep_bibliography=keep_bibliography,
        )
    elif target == "articles":
        action = lambda: build_all_articles(use_filter=True)
    elif target == "pdf-chapters":
        action = lambda: build_all_chapters(use_filter=True, pdfmode="screen")
    elif target == "draft-pdf-chapters":
        action = lambda: build_all_chapters(use_filter=True, pdfmode="screen")
    else:
        print(f"Unknown target: {target}")
        print(
            "Valid targets: epub, pdf, all, draft-epub, draft-pdf, draft-all, "
            "pdf-screen, pdf-print, pdf-debug, pdf-debug-screen, pdf-debug-print, "
            "docx, rtf, pdf-chapters, draft-pdf-chapters, chapter <path>, "
            "article <path> [output], articles, quote-playground"
        )
        sys.exit(1)

    maybe_sync_vscode_tasks()
    apply_layout_overrides_from_config()
    run_pre_build_hooks()
    update_build_metadata(build_stage)
    action()


if __name__ == "__main__":
    main()
