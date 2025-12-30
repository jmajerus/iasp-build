"""Generate layout override assets (CSS + TeX) from iasp-config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import config as iasp_config

CSS_OVERRIDE_NAME = "layout-overrides.css"
PDF_OVERRIDE_NAME = "pdf-layout-overrides.tex"

_DEFAULT_SCREEN_GEOMETRY = "margin=1.1in, twoside=false"
_DEFAULT_PRINT_GEOMETRY = (
    "inner=1.05in, outer=0.85in, top=0.95in, bottom=0.95in, bindingoffset=0.18in, twoside=true"
)


def _section(name: str) -> dict[str, Any]:
    value = iasp_config.get(name, default={})
    return value if isinstance(value, dict) else {}


def _config_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _normalize_font_stack(value: Any) -> list[str]:
    stack: list[str] = []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [chunk.strip() for chunk in value.split(",")]
    else:
        items = []
    for item in items:
        text = str(item).strip()
        if text:
            stack.append(text)
    return stack


def _css_family(family: str) -> str:
    token = family.strip()
    if not token:
        return ""
    lowered = token.lower()
    if lowered in {"serif", "sans-serif", "monospace"}:
        return lowered
    if token[0] == token[-1] == '"':
        return token
    if " " in token or "-" in token:
        return f'"{token}"'
    return token


def _css_font_stack(stack: list[str]) -> str:
    formatted = [_css_family(entry) for entry in stack if _css_family(entry)]
    return ", ".join(formatted)


def _pdf_font_name(stack: list[str]) -> str | None:
    if not stack:
        return None
    head = stack[0].strip()
    if head.startswith('"') and head.endswith('"'):
        head = head[1:-1]
    return head or None


def _screen_geometry(margins: dict[str, Any]) -> str:
    margin = str(
        margins.get("outer")
        or margins.get("inner")
        or margins.get("top")
        or margins.get("margin")
        or ""
    ).strip()
    if not margin:
        return _DEFAULT_SCREEN_GEOMETRY
    return f"margin={margin}, twoside=false"


def _print_geometry(margins: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("inner", "outer", "top", "bottom"):
        value = margins.get(key)
        if not value:
            continue
        text = str(value).strip()
        if text:
            parts.append(f"{key}={text}")
    if not parts:
        return _DEFAULT_PRINT_GEOMETRY
    parts.append("bindingoffset=0.18in")
    parts.append("twoside=true")
    return ", ".join(parts)


def _write_css_override(path: Path, fonts: dict[str, Any], page_break_level: int) -> bool:
    body_stack = _normalize_font_stack(fonts.get("body"))
    heading_stack = _normalize_font_stack(fonts.get("heading"))
    mono_stack = _normalize_font_stack(fonts.get("mono"))

    css_lines: list[str] = []
    css_lines.append("/* Auto-generated from iasp-config. Do not edit manually. */")
    css_lines.append("@namespace epub \"http://www.idpf.org/2007/ops\";")
    css_lines.append("")
    wrote_rules = False

    if body_stack:
        css_lines.append("body {")
        css_lines.append(f"  font-family: {_css_font_stack(body_stack)} !important;")
        css_lines.append("}")
        css_lines.append("")
        wrote_rules = True

    if heading_stack:
        css_lines.append("h1, h2, h3, h4 {")
        css_lines.append(f"  font-family: {_css_font_stack(heading_stack)} !important;")
        css_lines.append("}")
        css_lines.append("")
        wrote_rules = True

    if mono_stack:
        css_lines.append("code, pre, tt {")
        css_lines.append(f"  font-family: {_css_font_stack(mono_stack)} !important;")
        css_lines.append("}")
        css_lines.append("")
        wrote_rules = True

    selectors: list[str] = []
    if page_break_level >= 1:
        selectors.append('h1[epub|type~="chapter"]')
    if page_break_level >= 2:
        selectors.append('h2[epub|type~="subchapter"]')
    if page_break_level >= 3:
        selectors.append("h3")
    if page_break_level >= 4:
        selectors.append("h4")
    if selectors:
        css_lines.append(f"{', '.join(selectors)} {{")
        css_lines.append("  break-before: page;")
        css_lines.append("  page-break-before: always;")
        css_lines.append("}")
        css_lines.append("")
        wrote_rules = True

    if wrote_rules:
        payload = "\n".join(line for line in css_lines if line.strip()) + "\n"
        path.write_text(payload, encoding="utf-8")
        return True
    if path.exists():
        path.unlink(missing_ok=True)
    return False


def _write_pdf_override(path: Path, fonts: dict[str, Any], margins: dict[str, Any], page_break_level: int) -> bool:
    body_font = _pdf_font_name(_normalize_font_stack(fonts.get("body")))
    heading_font = _pdf_font_name(_normalize_font_stack(fonts.get("heading")))
    mono_font = _pdf_font_name(_normalize_font_stack(fonts.get("mono")))

    screen_geometry = _screen_geometry(margins)
    print_geometry = _print_geometry(margins)

    lines: list[str] = []
    lines.append("% Auto-generated from iasp-config. Do not edit manually.")
    has_overrides = False

    if body_font:
        lines.append("\\providecommand{\\BodyFontFamily}{}");
        lines.append(f"\\renewcommand{{\\BodyFontFamily}}{{{body_font}}}")
        has_overrides = True
    if heading_font:
        lines.append("\\providecommand{\\HeadingFontFamily}{}");
        lines.append(f"\\renewcommand{{\\HeadingFontFamily}}{{{heading_font}}}")
        has_overrides = True
    if mono_font:
        lines.append("\\providecommand{\\MonoFontFamily}{}");
        lines.append(f"\\renewcommand{{\\MonoFontFamily}}{{{mono_font}}}")
        has_overrides = True

    if screen_geometry:
        lines.append("\\providecommand{\\ScreenGeometryOptions}{}");
        lines.append(f"\\renewcommand{{\\ScreenGeometryOptions}}{{{screen_geometry}}}")
        has_overrides = True
    if print_geometry:
        lines.append("\\providecommand{\\PrintGeometryOptions}{}");
        lines.append(f"\\renewcommand{{\\PrintGeometryOptions}}{{{print_geometry}}}")
        has_overrides = True

    if page_break_level >= 2:
        lines.append("\\pretocmd{\\section}{\\clearpage}{}{}")
        has_overrides = True
    if page_break_level >= 3:
        lines.append("\\pretocmd{\\subsection}{\\clearpage}{}{}")
        has_overrides = True

    if has_overrides:
        content = "\n".join(lines).strip() + "\n"
        path.write_text(content, encoding="utf-8")
        return True
    if path.exists():
        path.unlink(missing_ok=True)
    return False


def apply(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    layout = _section("layout")
    fonts = layout.get("fonts") if isinstance(layout.get("fonts"), dict) else {}
    margins = layout.get("margins") if isinstance(layout.get("margins"), dict) else {}
    page_break_level = _config_int(layout.get("page_break_heading_level"), 1, minimum=0, maximum=6)

    css_path = build_dir / CSS_OVERRIDE_NAME
    pdf_path = build_dir / PDF_OVERRIDE_NAME

    css_written = _write_css_override(css_path, fonts, page_break_level)
    pdf_written = _write_pdf_override(pdf_path, fonts, margins, page_break_level)

    if not css_written and css_path.exists():
        css_path.unlink(missing_ok=True)
    if not pdf_written and pdf_path.exists():
        pdf_path.unlink(missing_ok=True)


__all__ = [
    "CSS_OVERRIDE_NAME",
    "PDF_OVERRIDE_NAME",
    "apply",
]
