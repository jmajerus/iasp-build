#!/usr/bin/env python3
"""Expand a Markdown file via the preprocess pipeline with change detection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iasp_tooling.paths import TOOLING_ROOT, project_root

PROJECT_ROOT = project_root()
DEFAULT_INPUT = None
DEFAULT_CONFIG = PROJECT_ROOT / "preprocessor" / "preprocess.yaml"
DEFAULT_FILTER = TOOLING_ROOT / "lua" / "catalog_collections.lua"
OUTPUT_DIR = PROJECT_ROOT / ".build"
STAMP_DIR = PROJECT_ROOT / ".build" / "preprocess-stamps"


def ensure_absolute(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


def slugify_path(path: Path) -> str:
    token = path.stem.lower()
    token = re.sub(r"[^a-z0-9]+", "-", token)
    token = re.sub(r"-+", "-", token).strip("-")
    return token or "preprocess"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def run_pandoc(input_path: Path, output_path: Path, config_path: Path, filter_path: Path) -> None:
    cmd = [
        "pandoc",
        "--lua-filter",
        str(filter_path),
        str(input_path),
        "-t",
        "markdown",
        "-o",
        str(output_path),
    ]
    if config_path != DEFAULT_CONFIG:
        cmd.extend(["-M", f"catalog_collections.config={config_path}"])
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        default=DEFAULT_INPUT,
        help="Markdown file containing catalog slots (required unless --input is provided)",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Preprocess configuration YAML (default: %(default)s)",
    )
    parser.add_argument(
        "--filter",
        default=str(DEFAULT_FILTER),
        help="Lua filter path (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        help="Output path (default: .build/<input-stem>-expanded.md)",
    )
    parser.add_argument(
        "--stamp",
        help="Override stamp file used for change detection",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even when inputs are unchanged",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.input:
        parser.error("An input Markdown file is required")
    input_path = ensure_absolute(args.input)
    config_path = ensure_absolute(args.config)
    filter_path = ensure_absolute(args.filter)

    for candidate, label in ((input_path, "input"), (config_path, "config"), (filter_path, "filter")):
        if not candidate.exists():
            sys.stderr.write(f"Missing {label} file: {candidate}\n")
            return 1

    default_output = OUTPUT_DIR / f"{slugify_path(input_path)}-expanded.md"
    output_path = ensure_absolute(args.output) if args.output else default_output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stamp_path: Path
    if args.stamp:
        stamp_path = ensure_absolute(args.stamp)
    else:
        stamp_token = hashlib.sha1(str(input_path).encode("utf-8")).hexdigest()[:16]
        stamp_path = STAMP_DIR / f"{stamp_token}.json"
    stamp_path.parent.mkdir(parents=True, exist_ok=True)

    current = {
        "input": file_hash(input_path),
        "config": file_hash(config_path),
        "filter": file_hash(filter_path),
    }

    previous: dict[str, str] = {}
    if stamp_path.exists() and not args.force:
        try:
            previous = json.loads(stamp_path.read_text())
        except json.JSONDecodeError:
            previous = {}

    if not args.force and previous == current and output_path.exists():
        print(f"No changes detected; skipping ({output_path.relative_to(PROJECT_ROOT)})")
        return 0

    try:
        run_pandoc(input_path, output_path, config_path, filter_path)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"Pandoc failed with exit code {exc.returncode}\n")
        return exc.returncode

    stamp_path.write_text(json.dumps(current, indent=2))
    print(f"Expanded {input_path.relative_to(PROJECT_ROOT)} -> {output_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
