"""iasp-build reports which version of the tooling ran a build."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import iasp_tooling

CHECKOUT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (CHECKOUT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', text, re.M).group(1)


def test_checkout_reports_pyproject_version_and_commit():
    version = iasp_tooling.__version__
    assert version.startswith(_pyproject_version())
    if (CHECKOUT / ".git").exists():
        assert re.fullmatch(re.escape(_pyproject_version()) + r"\+g[0-9a-f]{4,}(\.dirty)?", version)


def test_cli_version_flag():
    result = subprocess.run(
        [sys.executable, "-m", "iasp_tooling.cli", "--version"],
        cwd=CHECKOUT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip().endswith(iasp_tooling.__version__)


def test_installed_copy_reports_plain_version(tmp_path, monkeypatch):
    # Outside a checkout there is no pyproject.toml or .git beside the
    # package, so the version comes from the installed metadata alone.
    monkeypatch.setattr(iasp_tooling, "_PACKAGE_DIR", tmp_path / "site-packages" / "iasp_tooling")
    monkeypatch.setattr(iasp_tooling.metadata, "version", lambda name: "9.8.7")
    assert iasp_tooling._version() == "9.8.7"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def test_untracked_file_marks_checkout_dirty(tmp_path, monkeypatch):
    repo = tmp_path / "checkout"
    package = repo / "iasp_tooling"
    package.mkdir(parents=True)
    (repo / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    monkeypatch.setattr(iasp_tooling, "_PACKAGE_DIR", package)

    assert re.fullmatch(r"1\.2\.3\+g[0-9a-f]+", iasp_tooling._version())

    # Ignored files leave the checkout clean.
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "x.pyc").write_bytes(b"")
    assert not iasp_tooling._version().endswith(".dirty")

    # A new source file that is not committed yet makes it dirty.
    (package / "new_filter.lua").write_text("-- new\n", encoding="utf-8")
    assert iasp_tooling._version().endswith(".dirty")
