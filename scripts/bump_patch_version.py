#!/usr/bin/env python3
"""Increment the patch component of the book version.

Usage:
    python3 tooling/scripts/bump_patch_version.py
    python3 tooling/scripts/bump_patch_version.py --dry-run

By default this script:
1. Reads metadata.yaml, locates the `version: X.Y.Z` line, and increments Z.
2. Writes the updated metadata back to disk (unless --dry-run is passed).
3. Regenerates metadata.json so Pandoc sees the new version number on the
   next build.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
METADATA_FILE = ROOT / "metadata.yaml"
METADATA_GENERATOR = ROOT / "iasp_tooling" / "scripts" / "generate_metadata_json.py"
VERSION_PATTERN = re.compile(r"^(version:\s*)(['\"]?)(\d+)\.(\d+)\.(\d+)(['\"]?)\s*$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bump the patch component of metadata.yaml version")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the next version without modifying files or regenerating metadata.",
    )
    return parser.parse_args()


def load_metadata() -> str:
    try:
        return METADATA_FILE.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive messaging
        print(f"!! Unable to read {METADATA_FILE}: {exc}", file=sys.stderr)
        sys.exit(2)


def increment_version(contents: str) -> tuple[str, str, str]:
    match = VERSION_PATTERN.search(contents)
    if not match:
        print("!! Could not locate a semantic version in metadata.yaml", file=sys.stderr)
        sys.exit(3)

    prefix, quote_start, major, minor, patch, quote_end = match.groups()
    current_version = f"{major}.{minor}.{patch}"
    new_patch = str(int(patch) + 1)
    new_version = f"{major}.{minor}.{new_patch}"

    replacement_line = f"{prefix}{quote_start}{new_version}{quote_end}"
    updated = (
        contents[: match.start()] + replacement_line + contents[match.end() :]
    )
    return current_version, new_version, updated


def write_metadata(updated_contents: str) -> None:
    try:
        METADATA_FILE.write_text(updated_contents, encoding="utf-8")
    except OSError as exc:  # pragma: no cover
        print(f"!! Unable to write {METADATA_FILE}: {exc}", file=sys.stderr)
        sys.exit(4)


def regenerate_metadata_json() -> None:
    try:
        subprocess.run(
            [sys.executable, str(METADATA_GENERATOR)],
            cwd=ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        print(f"!! metadata generator failed: {exc}", file=sys.stderr)
        sys.exit(exc.returncode)


def main() -> None:
    args = parse_args()
    contents = load_metadata()
    current_version, new_version, updated_contents = increment_version(contents)

    if args.dry_run:
        print(f"Current version: {current_version}\nNext version: {new_version}")
        return

    write_metadata(updated_contents)
    regenerate_metadata_json()
    print(f"Bumped version: {current_version} -> {new_version}")


if __name__ == "__main__":
    main()
