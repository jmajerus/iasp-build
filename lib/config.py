"""Lightweight loader for project- and user-specific tooling settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from ..paths import project_root

PROJECT_ROOT = project_root()
CONFIG_FILENAME = "iasp-config.yaml"
CONFIG_ENV_VAR = "IASP_CONFIG_PATH"

try:  # pragma: no cover - thin wrapper, exercised via callers
    import yaml  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - surfaced lazily
    yaml = None  # type: ignore
    _yaml_error = exc
else:
    _yaml_error = None

_cached_config: Dict[str, Any] | None = None
_cached_path: Path | None = None


def resolve_config_path() -> Path:
    """Return the absolute path to the active configuration file."""

    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        return candidate
    return PROJECT_ROOT / CONFIG_FILENAME


def load_config(refresh: bool = False) -> Dict[str, Any]:
    """Load the configuration once and cache it for reuse."""

    global _cached_config, _cached_path
    if not refresh and _cached_config is not None:
        return _cached_config

    config_path = resolve_config_path()
    _cached_path = config_path
    if not config_path.exists():
        _cached_config = {}
        return _cached_config

    if yaml is None:  # pragma: no cover - requires PyYAML install
        raise RuntimeError(
            "PyYAML is required to parse '{path}'. Install it with `pip install pyyaml`.".format(
                path=config_path
            )
        ) from _yaml_error

    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Top-level structure in {config_path} must be a mapping/dictionary")

    _cached_config = data
    return _cached_config


def get(*segments: str, default: Any = None) -> Any:
    """Traverse the config (dot/path-style) and return a value or default."""

    config = load_config()
    current: Any = config
    for segment in segments:
        if not isinstance(current, dict):
            return default
        if segment not in current:
            return default
        current = current[segment]
    return current if current is not None else default


def config_path() -> Path:
    """Expose the resolved configuration path for messaging and diagnostics."""

    return _cached_path or resolve_config_path()


__all__ = [
    "CONFIG_ENV_VAR",
    "CONFIG_FILENAME",
    "config_path",
    "get",
    "load_config",
    "resolve_config_path",
]
