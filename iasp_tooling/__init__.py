"""Reusable IASP tooling package for build orchestration."""

from __future__ import annotations

import re
import subprocess
from importlib import metadata
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def _checkout_version() -> str | None:
    """Read the version from pyproject.toml when running from a checkout."""

    pyproject = _PACKAGE_DIR.parent / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    # tomllib is not available on Python 3.10, and the version line is simple.
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else None


def _git_suffix() -> str:
    """Local version label for code running from a git checkout.

    An installed wheel has no .git next to it, so released builds report the
    plain version. A checkout (editable install or PYTHONPATH) reports the
    commit, plus ".dirty" when it has uncommitted changes or new files that
    are not ignored.
    """

    checkout = _PACKAGE_DIR.parent
    if not (checkout / ".git").exists():
        return ""
    try:
        commit = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(checkout), "status", "--porcelain"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    if not commit:
        return ""
    return f"+g{commit}" + (".dirty" if dirty else "")


def _version() -> str:
    # A checkout's pyproject.toml is newer than the metadata an editable
    # install recorded, so prefer it.
    base = _checkout_version()
    if base is None:
        try:
            base = metadata.version("iasp-build")
        except metadata.PackageNotFoundError:
            base = "0+unknown"
    return base + _git_suffix()


__version__ = _version()
