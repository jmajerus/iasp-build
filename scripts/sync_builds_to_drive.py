#!/usr/bin/env python3
"""Copy the latest build artifacts into the mounted Google Drive folder."""

from __future__ import annotations

import argparse
import errno
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

MTIME_SKEW_TOLERANCE = 0.5  # seconds; GVFS mounts can quantize mtimes

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT / "build"
ANNEXES_DIR = BUILD_DIR / "annexes"
ARTICLES_DIR = BUILD_DIR / "articles"
PATCH_BUMP_SCRIPT = ROOT / "iasp_tooling" / "scripts" / "bump_patch_version.py"
DEFAULT_DRIVE_PATH = \
    Path(
        os.environ.get(
            "DRIVE_SYNC_TARGET",
            "/run/user/1000/gvfs/google-drive:host=gmail.com,user=skyanchor/0AI3PRVVN3WXRUk9PVA/1MgQaE_TLTrlVIvZNBg9isynjr4ZWo3W_",
        )
    )

ARTIFACTS = [
    ("The-Struggle-Against-Dehumanization.epub", "EPUB"),
    ("The-Struggle-Against-Dehumanization.pdf", "PDF (screen)"),
    ("The-Struggle-Against-Dehumanization-print.pdf", "PDF (print)"),
    ("The-Struggle-Against-Dehumanization.docx", "DOCX"),
    ("The-Struggle-Against-Dehumanization.rtf", "RTF"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync build outputs to Google Drive")
    parser.add_argument(
        "destination",
        nargs="?",
        help=(
            "Optional path to the Drive folder. Overrides the DRIVE_SYNC_TARGET env "
            "variable and the default GVFS mount path."
        ),
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip missing artifacts without returning a non-zero exit code.",
    )
    parser.add_argument(
        "--no-version-bump",
        action="store_true",
        help="Do not increment the metadata patch version after a successful sync.",
    )
    return parser.parse_args()


def resolve_destination(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value)
    return DEFAULT_DRIVE_PATH


def ensure_destination(dest: Path) -> None:
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - defensive messaging
        print(f"!! Unable to create destination directory {dest}: {exc}", file=sys.stderr)
        sys.exit(2)


def copy_artifact(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)

    if files_match(src, dest):
        print(f"-- Skipped {src.name}: destination already up to date.")
        return

    try:
        shutil.copy2(src, dest)
        print(f"-- Copied {src.name} -> {dest}")
        return
    except OSError as exc:
        if exc.errno != errno.EOPNOTSUPP:
            raise
        # GVFS (and some cloud-backed mounts) reject utime/copy2 metadata updates.
        shutil.copyfile(src, dest)
        print(
            f"-- Copied {src.name} -> {dest} (metadata preserved best-effort; mount "
            "does not support timestamps)",
        )


def files_match(src: Path, dest: Path) -> bool:
    """Return True if destination exists and matches the source bit-for-bit."""
    if not dest.exists():
        return False

    try:
        src_stat = src.stat()
        dest_stat = dest.stat()
    except OSError:
        return False

    if src_stat.st_size != dest_stat.st_size:
        return False

    # GVFS and similar mounts sometimes collapse mtimes to coarse increments. If
    # the source file is even slightly newer, assume it differs to avoid stale
    # copies when content changed but the bytewise comparison is skipped.
    if src_stat.st_mtime > dest_stat.st_mtime + MTIME_SKEW_TOLERANCE:
        return False

    try:
        return filecmp.cmp(src, dest, shallow=False)
    except OSError:
        return False


def copy_directory_contents(src_dir: Path, dest_dir: Path) -> None:
    if not src_dir.exists():
        return

    for path in sorted(src_dir.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(src_dir)
        target = dest_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_artifact(path, target)


def bump_patch_version() -> None:
    if not PATCH_BUMP_SCRIPT.exists():
        print("-- Warning: bump_patch_version.py not found; skipping version bump")
        return

    try:
        subprocess.run([sys.executable, str(PATCH_BUMP_SCRIPT)], cwd=ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"!! patch version bump failed: {exc}", file=sys.stderr)
        sys.exit(exc.returncode)


def main() -> None:
    args = parse_args()
    destination = resolve_destination(args.destination)

    if not destination:
        print("!! No Drive destination configured. Pass a path or set DRIVE_SYNC_TARGET.", file=sys.stderr)
        sys.exit(2)

    ensure_destination(destination)

    if not destination.exists():
        print(f"!! Destination {destination} is not accessible (GVFS mount missing?)", file=sys.stderr)
        sys.exit(3)

    if not BUILD_DIR.exists():
        print("!! Build directory does not exist yet. Generate artifacts before syncing.", file=sys.stderr)
        sys.exit(4)

    missing: list[str] = []
    for filename, label in ARTIFACTS:
        src = BUILD_DIR / filename
        if not src.exists():
            print(f"-- Skipping {label}: {filename} not found.")
            missing.append(filename)
            continue
        copy_artifact(src, destination / src.name)

    if ARTICLES_DIR.exists():
        print("\n== Syncing article outputs ==")
        articles_destination = destination / "articles"
        articles_destination.mkdir(parents=True, exist_ok=True)
        copy_directory_contents(ARTICLES_DIR, articles_destination)
    else:
        print("\n-- No article outputs to sync (build/articles missing).")

    annex_destination = destination / "annexes"
    if ANNEXES_DIR.exists():
        print("\n== Syncing annex outputs ==")
        annex_destination.mkdir(parents=True, exist_ok=True)
        copy_directory_contents(ANNEXES_DIR, annex_destination)
    else:
        print("\n-- No annex outputs to sync (build/annexes missing).")

    if missing and not args.skip_missing:
        print(
            "!! Some artifacts were missing: " + ", ".join(missing) +
            " (rerun build_book.py before syncing, or pass --skip-missing)",
            file=sys.stderr,
        )
        sys.exit(5)

    if not args.no_version_bump:
        bump_patch_version()
    else:
        print("-- Skipping version bump (per --no-version-bump)")

    print(f"Done. Synced artifacts to {destination}")


if __name__ == "__main__":
    main()
