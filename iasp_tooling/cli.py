"""Command-line entry point for building a manuscript."""

import argparse
import os
from pathlib import Path

from .paths import PROJECT_ROOT_ENV


def main(default_project_root: Path | None = None) -> None:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [--project-root PATH] [--profile NAME] [target] [arguments]",
        description="Build a manuscript. Common targets include epub, pdf, and article-md.",
        allow_abbrev=False,
    )
    parser.add_argument("--project-root", type=Path, help="Manuscript directory (default: current directory)")
    options, build_args = parser.parse_known_args()

    root = options.project_root or os.environ.get(PROJECT_ROOT_ENV) or default_project_root or Path.cwd()
    project_root = Path(root).expanduser().resolve()
    if not project_root.is_dir():
        parser.error(f"manuscript directory does not exist: {project_root}")
    os.environ[PROJECT_ROOT_ENV] = str(project_root)

    from .build_book import main as build

    build(build_args)


if __name__ == "__main__":
    main()
