#!/usr/bin/env python3
"""Generate metadata.json for Pandoc builds.

Edit the METADATA dict below and run this script to regenerate the
machine-written metadata.json file.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "metadata.json"

METADATA: dict[str, object] = {
    "author": ["John Majerus"],
    "title": "The Struggle Against Dehumanization",
    "subtitle": "Technology, Judgment, and Human Dignity in the Age of AI",
    "language": "en-US",
    "rights": "© 2025 John Majerus. All rights reserved.",
    "publisher": "Independent",
    "description": (
        "A multi-part series on how AI technologies contribute to "
        "dehumanization in the age of automation, drawing on real-world "
        "cases, philosophical frameworks, and actionable solutions."
    ),
    "comment": "Prepublication proof. Not for distribution.",
    "keywords": [
        "AI Ethics",
        "Dehumanization",
        "Technology and Society",
        "Human Dignity",
        "Automation",
        "Philosophy",
    ],
    "linernotes": True,
    "revision": True,
    "abstract": (
        "This work explores the ethical and societal implications of AI-driven "
        "dehumanization, examining how technology can erode human dignity and "
        "proposing strategies to uphold humanity in an increasingly automated world."
    ),
    "cover-image": "cover.png",
    "documentclass": "book",
    "classoption": ["oneside"],
    "version": "0.3.20",
}


def main() -> None:
    DEST.write_text(
        json.dumps(METADATA, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {DEST} ({len(METADATA)} top-level fields)")


if __name__ == "__main__":
    main()
