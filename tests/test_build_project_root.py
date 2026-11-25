import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

import iasp_tooling


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is required for a manuscript build")
def test_cli_builds_manuscript_outside_tooling_checkout(tmp_path):
    manuscript = tmp_path / "separate manuscript"
    chapter = manuscript / "chapters" / "introduction.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text(
        '# Introduction\n\nText from the separate manuscript.\n\n::: {.catalog-slot data-slot="example"}\n:::\n',
        encoding="utf-8",
    )
    source = manuscript / "sections" / "catalog entry.md"
    source.parent.mkdir()
    source.write_text("Text from the catalog entry.\n", encoding="utf-8")
    catalog = manuscript / "preprocessor" / "preprocess.yaml"
    catalog.parent.mkdir()
    catalog.write_text(
        "collections:\n"
        "  - key: sample\n"
        "    items:\n"
        "      - title: Catalog entry\n"
        "        source_file: sections/catalog entry.md\n"
        "insertions:\n"
        "  - slot: example\n"
        "    renderer: include_sequence\n"
        "    items:\n"
        "      - title: Catalog entry\n"
        "        source_file: sections/catalog entry.md\n",
        encoding="utf-8",
    )
    (manuscript / "book-order.txt").write_text("chapters/introduction.md\n", encoding="utf-8")
    (manuscript / "metadata.yaml").write_text("title: Portable manuscript\n", encoding="utf-8")
    (manuscript / "build-profiles.json").write_text(
        '{"default": {"output_basename": "portable"}}\n', encoding="utf-8"
    )
    (manuscript / "iasp-config.yaml").write_text(
        "toc:\n  enabled: false\ntasks:\n  manage_vscode_tasks: true\n", encoding="utf-8"
    )
    tasks = manuscript / ".vscode" / "tasks.json"
    tasks.parent.mkdir()
    original_tasks = b'{"version":"2.0.0","tasks":[]}\n'
    tasks.write_bytes(original_tasks)
    env = os.environ.copy()
    env.pop("IASP_CONFIG_PATH", None)
    env.pop("BUILD_PROFILE", None)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "iasp_tooling.cli", "--project-root", str(manuscript), "docx"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((manuscript / "metadata.json").read_text())["title"] == "Portable manuscript"
    build_metadata = json.loads((manuscript / "build" / "build-metadata.json").read_text())
    assert build_metadata["iasp-build-version"] == iasp_tooling.__version__
    assert f"== iasp-build {iasp_tooling.__version__} ==" in result.stdout
    assert "introduction.md" in (manuscript / "build" / "book-order.generated.md").read_text()
    with zipfile.ZipFile(manuscript / "build" / "portable.docx") as docx:
        document = docx.read("word/document.xml")
        assert b"Text from the separate manuscript." in document
        assert b"Text from the catalog entry." in document
    assert tasks.read_bytes() == original_tasks
    assert not (tmp_path / "build").exists()

    env["IASP_PROJECT_ROOT"] = manuscript.name
    expanded = subprocess.run(
        [sys.executable, "-m", "iasp_tooling.scripts.preprocess_expand", "chapters/introduction.md"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert expanded.returncode == 0, expanded.stdout + expanded.stderr
    output = (manuscript / ".build" / "introduction-expanded.md").read_text(encoding="utf-8")
    assert "sections/catalog entry.md" in output
    assert "Missing source" not in output
