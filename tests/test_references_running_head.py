"""The citeproc reference section must get its own PDF running head."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from iasp_tooling import build_book

CHECKOUT = Path(__file__).resolve().parents[1]
FILTER = CHECKOUT / "iasp_tooling" / "lua" / "references_running_head.lua"

requires_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is required")

BIB = "@book{a, title={A Title}, author={Doe, Jane}, year=2000}\n"


def _latex(tmp_path: Path, source: str, *, citeproc_then_filter: bool = True) -> str:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text(source, encoding="utf-8")
    cmd = ["pandoc", str(doc), "--top-level-division=chapter", "-t", "latex"]
    if citeproc_then_filter:
        cmd += ["--citeproc", "--lua-filter", str(FILTER)]
    else:
        cmd += ["--lua-filter", str(FILTER), "--citeproc"]
    return subprocess.run(
        cmd, cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout


def _source(title: str) -> str:
    return (
        "---\nbibliography: refs.bib\n"
        f"reference-section-title: \"{title}\"\n---\n\n"
        "# Last Appendix\n\nText [@a].\n"
    )


@requires_pandoc
def test_reference_section_sets_running_head(tmp_path):
    latex = _latex(tmp_path, _source("References"))
    heading = latex.index("\\chapter*{References}")
    head = latex.index("\\iaspSetRunningHeadNow{References}")
    refs = latex.index("\\begin{CSLReferences}")
    assert heading < head < refs


@requires_pandoc
def test_running_head_label_is_latex_escaped(tmp_path):
    latex = _latex(tmp_path, _source("Notes & Sources"))
    assert "\\iaspSetRunningHeadNow{Notes \\& Sources}" in latex


@requires_pandoc
def test_running_head_is_guarded_for_documents_without_pdf_header(tmp_path):
    latex = _latex(tmp_path, _source("References"))
    assert "\\ifdefined\\iaspSetRunningHeadNow" in latex


@requires_pandoc
def test_filter_before_citeproc_sees_no_reference_section(tmp_path):
    # Documents why the filter must follow --citeproc on the command line.
    latex = _latex(tmp_path, _source("References"), citeproc_then_filter=False)
    assert "iaspSetRunningHeadNow" not in latex


def test_enable_citations_adds_filter_after_citeproc():
    cmd = ["pandoc", "--lua-filter", "other.lua"]
    build_book.enable_citations(cmd)
    citeproc = cmd.index("--citeproc")
    assert cmd[citeproc + 1 : citeproc + 3] == [
        "--lua-filter",
        str(build_book.REFERENCES_RUNNING_HEAD_FILTER),
    ]
