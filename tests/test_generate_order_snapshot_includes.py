"""Tests for include parsing helpers in generate_order_snapshot."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from iasp_tooling.scripts import generate_order_snapshot as gos


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(gos, "ROOT", tmp_path)
    gos.FILE_INCLUDE_CACHE.clear()
    return tmp_path


def test_parse_attr_tokens_supports_ids_classes_and_attrs():
    attr_string = "#main .include .code dir=appendices glyph=note"
    identifier, classes, attrs = gos._parse_attr_tokens(attr_string)

    assert identifier == "main"
    assert classes == ["include", "code"]
    assert attrs["dir"] == "appendices"
    assert attrs["glyph"] == "note"


def test_discover_include_blocks_returns_only_include_sections(temp_root):
    source_file = temp_root / "chapters" / "test.md"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        """
Intro paragraph
::: {#first .include dir=appendices}
:::

::: {.note}
:::
""".strip()
    )

    blocks = gos._discover_include_blocks("chapters/test.md")
    assert len(blocks) == 1

    block = blocks[0]
    assert block.identifier == "first"
    assert "include" in block.classes
    assert block.attrs["dir"] == "appendices"
    assert block.source == "chapters/test.md"


def test_build_include_node_expands_directory_targets(temp_root):
    extras_dir = temp_root / "appendices"
    extras_dir.mkdir(parents=True, exist_ok=True)
    (extras_dir / "b.md").write_text("Body B", encoding="utf-8")
    (extras_dir / "a.md").write_text("Body A", encoding="utf-8")

    include = gos.IncludeBlock(
        identifier="dir-include",
        classes=["include"],
        attrs={"dir": "appendices"},
        source="chapters/test.md",
        line_number=3,
    )

    class DummyOrder:
        def label_for(self, rel_path: str) -> str:
            return f"Label for {rel_path}"

    parent_dir = temp_root / "chapters"
    parent_dir.mkdir(parents=True, exist_ok=True)

    node = gos._build_include_node(
        include,
        parent_dir=parent_dir,
        depth=1,
        max_depth=2,
        order_data=DummyOrder(),
        visited=set(),
    )

    assert node is not None
    assert node.kind == "include"
    assert node.note is None
    assert [child.label for child in node.children] == [
        "Label for appendices/a.md",
        "Label for appendices/b.md",
    ]
    assert all(child.kind == "include-file" for child in node.children)
    assert all(child.children == [] for child in node.children)
