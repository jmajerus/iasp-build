"""Discrete palette presets for glyph and badge background mixes."""

from __future__ import annotations

from typing import Any, Mapping

_GLYPH_LUMA_PRESETS: Mapping[str, float] = {
    "balanced": -0.20,
    "subtle": -0.12,
    "contrast": -0.30,
    "bright": 0.08,
    "neutral": 0.0,
}

_BADGE_LUMA_PRESETS: Mapping[str, float] = {
    "balanced": -0.18,
    "subtle": -0.10,
    "contrast": -0.26,
    "bright": 0.10,
    "neutral": 0.0,
}


def _normalize_palette_name(name: Any) -> str | None:
    if not isinstance(name, str):
        return None
    normalized = name.strip().lower().replace("_", "-")
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or None


def _palette_value(presets: Mapping[str, float], choice: Any) -> tuple[float | None, str | None]:
    normalized = _normalize_palette_name(choice)
    if not normalized:
        return None, None
    value = presets.get(normalized)
    if value is None:
        return None, None
    return value, normalized


def select_luma_offset(kind: str, choice: Any, fallback: float) -> tuple[float, str | None]:
    if kind == "badge":
        value, normalized = _palette_value(_BADGE_LUMA_PRESETS, choice)
    else:
        value, normalized = _palette_value(_GLYPH_LUMA_PRESETS, choice)
    if value is None:
        return fallback, None
    return value, normalized


def available_palettes(kind: str) -> tuple[str, ...]:
    if kind == "badge":
        return tuple(sorted(_BADGE_LUMA_PRESETS.keys()))
    return tuple(sorted(_GLYPH_LUMA_PRESETS.keys()))
