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
