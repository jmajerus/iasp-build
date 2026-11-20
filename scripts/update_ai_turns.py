#!/usr/bin/env python3
"""Create/update per-article AI disclosure metadata.

Stores metadata in a sidecar JSON file next to the article source:
  articles/My Article.ai.json

Usage examples:
  python3 iasp_tooling/scripts/update_ai_turns.py "articles/What We Stop Providing.md" --set 42
  python3 iasp_tooling/scripts/update_ai_turns.py "articles/What We Stop Providing.md" --inc 3
    python3 iasp_tooling/scripts/update_ai_turns.py "articles/What We Stop Providing.md" --set-fuzzy-min 10 --set-fuzzy-max 18
    python3 iasp_tooling/scripts/update_ai_turns.py "articles/What We Stop Providing.md" --set-bucket "several"
  python3 iasp_tooling/scripts/update_ai_turns.py "articles/What We Stop Providing.md" --init-defaults
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _resolve_article(path_or_slug: str) -> Path:
    candidate = Path(path_or_slug)
    if not candidate.suffix:
        candidate = candidate.with_suffix(".md")

    if candidate.is_absolute():
        path = candidate
    else:
        direct = (ROOT / candidate).resolve()
        if direct.exists():
            path = direct
        else:
            path = (ROOT / "articles" / candidate.name).resolve()

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Article not found: {path_or_slug}")

    return path


def _load_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", help="Article path or slug")
    parser.add_argument("--set", type=int, dest="set_turns", help="Set turns to an absolute value")
    parser.add_argument("--inc", type=int, default=0, help="Increment turns by this amount")
    parser.add_argument("--set-fuzzy-min", type=int, help="Set lower bound for fuzzy turn range")
    parser.add_argument("--set-fuzzy-max", type=int, help="Set upper bound for fuzzy turn range")
    parser.add_argument("--clear-fuzzy", action="store_true", help="Remove fuzzy turn range fields")
    parser.add_argument("--set-bucket", help="Override linguistic bucket label (e.g. 'several')")
    parser.add_argument("--clear-bucket", action="store_true", help="Remove linguistic bucket override")
    parser.add_argument("--init-defaults", action="store_true", help="Add default disclosure templates if missing")
    parser.add_argument("--ai-disclosure", help="Override AI disclosure template text")
    parser.add_argument("--technical-note", help="Override technical note template text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        article = _resolve_article(args.article)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    sidecar = article.with_suffix(".ai.json")
    try:
        payload = _load_json(sidecar)
    except (OSError, ValueError) as exc:
        print(f"Cannot update {sidecar}: {exc}", file=sys.stderr)
        return 1

    turns_raw = payload.get("turns", 0)
    try:
        turns = int(turns_raw)
    except (TypeError, ValueError):
        turns = 0

    if args.set_turns is not None:
        turns = max(0, args.set_turns)

    if args.inc:
        turns = max(0, turns + args.inc)

    payload["turns"] = turns

    if args.set_fuzzy_min is not None:
        payload["turns_fuzzy_min"] = max(0, args.set_fuzzy_min)
    if args.set_fuzzy_max is not None:
        payload["turns_fuzzy_max"] = max(0, args.set_fuzzy_max)

    if args.clear_fuzzy:
        payload.pop("turns_fuzzy_min", None)
        payload.pop("turns_fuzzy_max", None)

    if args.set_bucket is not None:
        override = args.set_bucket.strip()
        if override:
            payload["turns_bucket_override"] = override

    if args.clear_bucket:
        payload.pop("turns_bucket_override", None)

    fuzzy_min = payload.get("turns_fuzzy_min")
    fuzzy_max = payload.get("turns_fuzzy_max")
    if isinstance(fuzzy_min, int) and isinstance(fuzzy_max, int) and fuzzy_max < fuzzy_min:
        payload["turns_fuzzy_min"], payload["turns_fuzzy_max"] = fuzzy_max, fuzzy_min

    if args.init_defaults:
        payload.setdefault(
            "ai_disclosure",
            "AI Disclosure: This text was generated via a {turns}-turn drafting session with Claude Sonnet.",
        )
        payload.setdefault(
            "technical_note",
            "Technical Note: This article was published via a custom automated build pipeline co-engineered with ChatGPT.",
        )

    if args.ai_disclosure is not None:
        payload["ai_disclosure"] = args.ai_disclosure

    if args.technical_note is not None:
        payload["technical_note"] = args.technical_note

    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Updated {sidecar}")
    print(f"turns={turns}")
    if "turns_fuzzy_min" in payload and "turns_fuzzy_max" in payload:
        print(f"turns_fuzzy=~{payload['turns_fuzzy_min']}-{payload['turns_fuzzy_max']}")
    if "turns_bucket_override" in payload:
        print(f"turns_bucket_override={payload['turns_bucket_override']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
