#!/usr/bin/env python3
"""Preview catalog slots by running the Lua filter directly via Pandoc."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iasp_tooling.paths import TOOLING_ROOT, project_environment, project_root

PROJECT_ROOT = project_root()

from iasp_tooling.preprocess import config as preprocess_config
FILTER = TOOLING_ROOT / "lua" / "catalog_collections.lua"
DEFAULT_CONFIG = preprocess_config.resolve_config_path()

try:
    import yaml  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - dependency notice
    raise SystemExit(
        "PyYAML is required for preprocess previews. Install it with "
        "`pip install pyyaml` (or your package manager) and rerun the script."
    ) from exc


def infer_slots_from_config(path: Path) -> list[str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return []
    except yaml.YAMLError as exc:
        raise SystemExit(f"Failed to parse preprocess config at {path}: {exc}") from exc

    insertions = data.get("insertions") if isinstance(data, dict) else None
    if not isinstance(insertions, list):
        return []

    slots: list[str] = []
    for entry in insertions:
        if not isinstance(entry, dict):
            continue
        slot = entry.get("slot")
        if slot and slot not in slots:
            slots.append(str(slot))
    return slots


def build_placeholder_doc(slots: list[str]) -> str:
    segments: list[str] = []
    for slot in slots:
        marker = slot.upper().replace("-", "_")
        segments.append(f"<!-- SLOT:{marker}:START -->")
        segments.append(f"::{{.catalog-slot data-slot=\"{slot}\"}}")
        segments.append(":::")
        segments.append(f"<!-- SLOT:{marker}:END -->")
        segments.append("")
    return "\n".join(segments)


def render_catalog(slots: list[str], config_path: Path) -> str:
    if not FILTER.exists():
        raise SystemExit(f"Catalog collections Lua filter not found at {FILTER}")

    markdown = build_placeholder_doc(slots)
    meta_data = f"catalog_collections:\n  config: \"{config_path}\"\n"

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as meta_file:
        meta_file.write(meta_data)
        meta_file_path = Path(meta_file.name)

    try:
        cmd = [
            "pandoc",
            "-f",
            "markdown",
            "-t",
            "markdown",
            "--metadata-file",
            str(meta_file_path),
            "--lua-filter",
            str(FILTER),
        ]
        result = subprocess.run(
            cmd,
            input=markdown.encode("utf-8"),
            capture_output=True,
            cwd=PROJECT_ROOT,
            env=project_environment(PROJECT_ROOT),
        )
    finally:
        meta_file_path.unlink(missing_ok=True)

    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode("utf-8", errors="ignore"))
        raise SystemExit(result.returncode)

    return result.stdout.decode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to a preprocess configuration YAML file (default: %(default)s)",
    )
    parser.add_argument(
        "--slot",
        dest="slots",
        action="append",
        help="Slot ID to render (repeat for multiple). Defaults to every slot declared in the config.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write rendered output to this file instead of stdout.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = preprocess_config.ensure_absolute(args.config)
    if not config_path.exists():
        raise SystemExit(f"Preprocess config not found at {config_path}")

    slots = args.slots or infer_slots_from_config(config_path)
    if not slots:
        raise SystemExit(
            "No slot IDs provided and none found in the preprocess config. Add --slot values or define insertions."
        )
    output = render_catalog(slots, config_path)

    if args.output:
        out_path = Path(args.output).expanduser()
        if not out_path.is_absolute():
            out_path = (PROJECT_ROOT / out_path).resolve()
        out_path.write_text(output, encoding="utf-8")
        print(f"-- Wrote catalog preview to {out_path}")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
