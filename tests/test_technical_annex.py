import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is required for the annex build")
def test_technical_annex_includes_its_source_documents(tmp_path):
    checkout = Path(__file__).resolve().parents[1]
    docs = tmp_path / "docs"
    shutil.copytree(
        checkout / "docs", docs, ignore=shutil.ignore_patterns("build", ".build-info.json", "metadata.json")
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(checkout)
    env.pop("IASP_CONFIG_PATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "iasp_tooling.cli",
            "--project-root",
            str(docs),
            "--profile",
            "iasp-framework",
            "docx",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with ZipFile(docs / "build" / "annexes" / "IASP-Framework-Technical-Annex.docx") as docx:
        document = ElementTree.fromstring(docx.read("word/document.xml"))
    text = " ".join(" ".join(document.itertext()).split())
    assert "could not be inserted here" not in text
    assert "could not be expanded here" not in text

    annex = (docs / "annex" / "IASP Framework Technical Annex.md").read_text(encoding="utf-8")
    includes = re.findall(r'^::: \{\.include path="([^"]+)"', annex, re.MULTILINE)
    assert includes and len(includes) == annex.count("::: {.include")
    for target in includes:
        source = (docs / target).read_text(encoding="utf-8")
        title = re.search(r"^# (.+)", source, re.MULTILINE)
        assert title and title.group(1).strip("*") in text, target
