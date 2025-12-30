"""Helpers for resolving preprocess/catalog configuration from iasp-config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lib import config as iasp_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "preprocessor" / "preprocess.yaml"


def _section() -> dict[str, Any]:
    value = iasp_config.get("preprocessor", default={})
    return value if isinstance(value, dict) else {}


def ensure_absolute(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


def is_enabled() -> bool:
    data = _section()
    enabled = data.get("enabled", True)
    if isinstance(enabled, str):
        return enabled.strip().lower() in {"1", "true", "yes", "on"}
    return bool(enabled)


def profile_name() -> str | None:
    profile = _section().get("profile")
    if profile is None:
        return None
    text = str(profile).strip()
    return text or None


def configured_path() -> Path | None:
    config_value = _section().get("config")
    if not config_value:
        return None
    return ensure_absolute(str(config_value))


def _resolve_profile_path(profile: Any) -> Path | None:
    text = str(profile or "").strip()
    if not text or text.lower() == "default":
        return None

    if "/" in text or text.endswith(".yaml"):
        return ensure_absolute(text)

    token = text.replace(" ", "-")
    candidates = [
        PROJECT_ROOT / "preprocessor" / f"{token}.yaml",
        PROJECT_ROOT / "preprocessor" / f"preprocess-{token}.yaml",
        PROJECT_ROOT / "preprocessor" / f"preprocess.{token}.yaml",
        PROJECT_ROOT / "preprocessor" / token / "preprocess.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_config_path() -> Path:
    configured = configured_path()
    if configured:
        return configured
    profile = profile_name()
    profile_path = _resolve_profile_path(profile)
    if profile_path:
        return profile_path
    return DEFAULT_CONFIG


def config_exists() -> bool:
    return resolve_config_path().exists()


def describe_config_source() -> str:
    path = resolve_config_path()
    marker = " (default)" if path == DEFAULT_CONFIG else ""
    return f"{path}{marker}"


__all__ = [
    "DEFAULT_CONFIG",
    "config_exists",
    "configured_path",
    "describe_config_source",
    "ensure_absolute",
    "is_enabled",
    "profile_name",
    "resolve_config_path",
]
