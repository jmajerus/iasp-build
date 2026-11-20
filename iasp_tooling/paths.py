"""Locate the tooling assets and the manuscript selected for this process."""

import os
from pathlib import Path

TOOLING_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT_ENV = "IASP_PROJECT_ROOT"


def project_root() -> Path:
    return Path(os.environ.get(PROJECT_ROOT_ENV) or Path.cwd()).expanduser().resolve()


def project_environment(root: Path) -> dict[str, str]:
    return {**os.environ, PROJECT_ROOT_ENV: str(root)}
