#!/usr/bin/env python3
"""Generate metadata.json from the canonical metadata.yaml file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:  # PyYAML is already a dependency for other tooling modules
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover - defensive guard for missing dependency
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None

ROOT = Path(__file__).resolve().parents[2]
METADATA_YAML = ROOT / "metadata.yaml"
METADATA_JSON = ROOT / "metadata.json"


def load_metadata_yaml() -> dict[str, object]:
    if yaml is None:
        print(
            "!! PyYAML is required to parse metadata.yaml (pip install pyyaml)",
            file=sys.stderr,
        )
        if YAML_IMPORT_ERROR is not None:
            print(f"   Underlying import error: {YAML_IMPORT_ERROR}", file=sys.stderr)
        sys.exit(2)

    try:
        raw_text = METADATA_YAML.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"!! Unable to read {METADATA_YAML}: {exc}", file=sys.stderr)
        sys.exit(3)

    try:
        data = yaml.safe_load(raw_text)
    except Exception as exc:  # pragma: no cover - PyYAML failure path
        print(f"!! Failed to parse {METADATA_YAML}: {exc}", file=sys.stderr)
        sys.exit(4)

    if not isinstance(data, dict):
        print(
            f"!! Expected {METADATA_YAML} to define a mapping at the top level",
            file=sys.stderr,
        )
        sys.exit(5)
    return data


def write_metadata_json(metadata: dict[str, object]) -> None:
    payload = json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    try:
        METADATA_JSON.write_text(payload, encoding="utf-8")
    except OSError as exc:
        print(f"!! Unable to write {METADATA_JSON}: {exc}", file=sys.stderr)
        sys.exit(6)


def main() -> None:
    metadata = load_metadata_yaml()
    write_metadata_json(metadata)
    print(
        f"Wrote {METADATA_JSON.relative_to(ROOT)} from {METADATA_YAML.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
