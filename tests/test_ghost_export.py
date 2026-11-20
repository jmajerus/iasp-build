"""Tests for the Ghost-style Markdown article exporter."""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from iasp_tooling.scripts.ghost_export import GhostExporter


def test_export_expands_includes_and_renders_epigraph_as_blockquote(tmp_path):
    article_dir = tmp_path / "articles"
    notes_dir = tmp_path / "notes"
    article_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    (notes_dir / "snippet.md").write_text("Included *Markdown* text.", encoding="utf-8")

    article = article_dir / "example.md"
    article.write_text(
        """
::: {.article}

Intro paragraph.

::: {.include path="notes/snippet.md"}
:::

::: {.epigraph}
*He suffered ever the same unceasing agonies.*

— Leo Tolstoy
:::

:::
""".strip(),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._process_file(article)

    assert "Intro paragraph." in rendered
    assert "Included *Markdown* text." in rendered
    assert "> *He suffered ever the same unceasing agonies.*" in rendered
    assert "> — Leo Tolstoy" in rendered


def test_export_injects_ai_disclosure_metadata_before_works_cited(tmp_path):
    article = tmp_path / "articles" / "example.md"
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        """
::: {.article}

Body text.

## Works Cited

Reference body.

:::
""".strip(),
        encoding="utf-8",
    )

    sidecar = article.with_suffix(".ai.json")
    sidecar.write_text(
        json.dumps(
            {
                "turns": 7,
                "ai_disclosure": "AI Disclosure: This text was generated via a {turns}-turn drafting session with Claude Sonnet.",
                "technical_note": "Technical Note: This article was published via a custom automated build pipeline co-engineered with ChatGPT.",
            }
        ),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._render_document(article)

    assert "AI Disclosure: This text was generated via a 7-turn drafting session with Claude Sonnet." in rendered
    assert "Technical Note: This article was published via a custom automated build pipeline co-engineered with ChatGPT." in rendered
    assert "AI DISCLOSURE" in rendered
    assert "<div style=\"background-color" in rendered

    disclosure_index = rendered.index("AI Disclosure:")
    works_cited_index = rendered.index("## Works Cited")
    assert disclosure_index < works_cited_index


def test_export_does_not_duplicate_existing_disclosures(tmp_path):
    article = tmp_path / "articles" / "example.md"
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        """
::: {.article}

AI Disclosure: Existing line from source.
Technical Note: Existing note from source.

## Works Cited

Reference body.

:::
""".strip(),
        encoding="utf-8",
    )

    sidecar = article.with_suffix(".ai.json")
    sidecar.write_text(
        json.dumps(
            {
                "turns": 42,
                "ai_disclosure": "AI Disclosure: This text was generated via a {turns}-turn drafting session with Claude Sonnet.",
                "technical_note": "Technical Note: This article was published via a custom automated build pipeline co-engineered with ChatGPT.",
            }
        ),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._render_document(article)

    assert rendered.count("AI Disclosure:") == 1
    assert rendered.count("Technical Note:") == 1


def test_export_supports_fuzzy_turn_placeholders(tmp_path):
    article = tmp_path / "articles" / "example.md"
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        """
::: {.article}

Body text.

## Works Cited

Reference body.

:::
""".strip(),
        encoding="utf-8",
    )

    sidecar = article.with_suffix(".ai.json")
    sidecar.write_text(
        json.dumps(
            {
                "turns": 12,
                "turns_fuzzy_min": 10,
                "turns_fuzzy_max": 18,
                "ai_disclosure": "AI Disclosure: This text was generated via approximately {turns_fuzzy} turns (exact-log baseline {turns_exact}).",
                "technical_note": "Technical Note: This article was published via a custom automated build pipeline co-engineered with ChatGPT.",
            }
        ),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._render_document(article)

    assert "approximately ~10-18 turns" in rendered
    assert "exact-log baseline 12" in rendered


def test_export_supports_turn_bucket_placeholders(tmp_path):
    article = tmp_path / "articles" / "example.md"
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        """
::: {.article}

Body text.

## Works Cited

Reference body.

:::
""".strip(),
        encoding="utf-8",
    )

    sidecar = article.with_suffix(".ai.json")
    sidecar.write_text(
        json.dumps(
            {
                "turns": 8,
                "ai_disclosure": "AI Disclosure: This text was generated via {turns_bucket} AI-assisted turns.",
                "technical_note": "Technical Note: {turns_bucket_phrase} were used across revision workflows.",
            }
        ),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._render_document(article)

    assert "via several AI-assisted turns" in rendered
    assert "Technical Note: several turns were used" in rendered


def test_export_supports_turn_bucket_override(tmp_path):
    article = tmp_path / "articles" / "example.md"
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        """
::: {.article}

Body text.

## Works Cited

Reference body.

:::
""".strip(),
        encoding="utf-8",
    )

    sidecar = article.with_suffix(".ai.json")
    sidecar.write_text(
        json.dumps(
            {
                "turns": 30,
                "turns_bucket_override": "around twenty",
                "ai_disclosure": "AI Disclosure: This text was generated via {turns_bucket} AI-assisted turns.",
                "technical_note": "Technical Note: {turns_bucket_phrase} were used across revision workflows.",
            }
        ),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._render_document(article)

    assert "via around twenty AI-assisted turns" in rendered
    assert "Technical Note: around twenty turns were used" in rendered


def test_export_renders_note_ai_variant(tmp_path):
    article = tmp_path / "articles" / "example.md"
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        """
::: {.article}

::: {.note.ai}
AI-specific authored disclosure content.
:::

:::
""".strip(),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._render_document(article)

    assert "AI-specific authored disclosure content." in rendered
    assert "AI DISCLOSURE" in rendered


def test_export_respects_disclosure_variant_override(tmp_path):
    article = tmp_path / "articles" / "example.md"
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        """
::: {.article}

Body text.

## Works Cited

Reference body.

:::
""".strip(),
        encoding="utf-8",
    )

    sidecar = article.with_suffix(".ai.json")
    sidecar.write_text(
        json.dumps(
            {
                "turns": 5,
                "disclosure_variant": "disclosure",
                "ai_disclosure": "AI Disclosure: Variant override check.",
                "technical_note": "Technical Note: Variant override check.",
            }
        ),
        encoding="utf-8",
    )

    exporter = GhostExporter(tmp_path)
    rendered = exporter._render_document(article)

    assert "DISCLOSURE" in rendered
    assert "AI DISCLOSURE" not in rendered