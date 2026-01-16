"""Generate layout override assets (CSS + TeX) from iasp-config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import config as iasp_config
from .background_palettes import select_luma_offset

CSS_OVERRIDE_NAME = "layout-overrides.css"
PDF_OVERRIDE_NAME = "pdf-layout-overrides.tex"

_DEFAULT_SCREEN_GEOMETRY = "margin=1.1in, twoside=false"
_DEFAULT_PRINT_GEOMETRY = (
    "inner=1.05in, outer=0.85in, top=0.95in, bottom=0.95in, bindingoffset=0.18in, twoside=true"
)


def _section(name: str) -> dict[str, Any]:
    value = iasp_config.get(name, default={})
    return value if isinstance(value, dict) else {}


def _config_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return value != 0
    return default


def _config_running_header_scope(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"chapter", "part"}:
            return lowered
    return "chapter"


def _config_appendix_running_header_scope(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"chapter", "section"}:
            return lowered
    return "chapter"


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


def _config_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _config_luma_offset(value: Any, default: float) -> float:
    """Allow luma offsets to be entered as unit fractions or percentages."""

    def _clamp(num: float) -> float:
        return max(-0.5, min(0.5, num))

    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            try:
                percent_value = float(text[:-1]) / 100.0
                return _clamp(percent_value)
            except ValueError:
                pass
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default

    if abs(numeric) > 1.0:
        numeric = numeric / 100.0

    return _clamp(numeric)


def _format_float(value: float) -> str:
    text = f"{value:.4f}"
    text = text.rstrip("0").rstrip(".")
    return text or "0"


_BADGE_COLOR_MACROS: tuple[dict[str, Any], ...] = (
    {
        "macro": "\\notebadgebgnormal",
        "base_color": "noteboxline",
        "base_percent": 15,
        "default_expr": "noteboxline!15!white",
        "offset_kind": "badge",
        "black_limit": 50,
    },
    {
        "macro": "\\notebadgebgbreadcrumb",
        "base_color": "noteboxbreadcrumbline",
        "base_percent": 18,
        "default_expr": "noteboxbreadcrumbline!18!white",
        "offset_kind": "badge",
        "black_limit": 50,
    },
    {
        "macro": "\\notebadgebgwarning",
        "base_color": "noteboxwarningline",
        "base_percent": 15,
        "default_expr": "noteboxwarningline!15!white",
        "offset_kind": "badge",
        "black_limit": 50,
    },
    {
        "macro": "\\sidebarbadgebg",
        "base_color": "sidebarbg",
        "base_percent": 70,
        "default_expr": "sidebarbg!70!white",
        "offset_kind": "badge",
        "black_limit": 50,
    },
    {
        "macro": "\\boxbadgebg",
        "base_color": "sidebarbg",
        "base_percent": 70,
        "default_expr": "sidebarbg!70!white",
        "offset_kind": "badge",
        "black_limit": 50,
    },
)


def _mix_expression(
    base_color: str,
    base_percent: int,
    offset: float,
    *,
    black_limit: int = 50,
) -> str:
    mix_value = base_percent + int(round(offset * 100))
    if mix_value > 100:
        mix_value = 100
    if mix_value < -100:
        mix_value = -100
    if mix_value < 0:
        amount = min(-mix_value, max(0, black_limit))
        return f"{base_color}!{amount}!black"
    return f"{base_color}!{mix_value}!white"


def _resolve_pdf_color_overrides(
    glyph_offset: float,
    badge_offset: float,
    force_white: bool,
) -> dict[str, str]:
    offsets = {"glyph": glyph_offset, "badge": badge_offset}
    overrides: dict[str, str] = {}
    for entry in _BADGE_COLOR_MACROS:
        macro = entry["macro"]
        default_expr = entry["default_expr"]
        if force_white:
            expr = "white"
        else:
            expr = _mix_expression(
                entry["base_color"],
                entry["base_percent"],
                offsets[entry["offset_kind"]],
                black_limit=int(entry.get("black_limit", 50)),
            )
        if expr != default_expr:
            overrides[macro] = expr
    return overrides


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


def _write_css_override(
    path: Path,
    fonts: dict[str, Any],
    page_break_level: int,
    glyph_luma_offset: float,
    badge_luma_offset: float,
    glyph_force_white: bool,
) -> bool:
    body_stack = _normalize_font_stack(fonts.get("body"))
    heading_stack = _normalize_font_stack(fonts.get("heading"))
    mono_stack = _normalize_font_stack(fonts.get("mono"))

    css_lines: list[str] = []
    css_lines.append("/* Auto-generated from iasp-config. Do not edit manually. */")
    css_lines.append("@namespace epub \"http://www.idpf.org/2007/ops\";")
    css_lines.append("")
    wrote_rules = False

    root_lines: list[str] = []
    if abs(glyph_luma_offset) >= 1e-6 or abs(badge_luma_offset) >= 1e-6:
        root_lines.append(
            f"  --glyph-background-luma-offset: {_format_float(glyph_luma_offset)};"
        )
        root_lines.append(
            f"  --badge-background-luma-offset: {_format_float(badge_luma_offset)};"
        )

    if glyph_force_white:
        root_lines.append("  --glyph-marker-background: #ffffff;")
        root_lines.append("  --glyph-background-force-white: 1;")

    if root_lines:
        css_lines.append(":root {")
        css_lines.extend(root_lines)
        css_lines.append("}")
        css_lines.append("")
        wrote_rules = True

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


def _write_pdf_override(
    path: Path,
    fonts: dict[str, Any],
    margins: dict[str, Any],
    page_break_level: int,
    badge_color_overrides: dict[str, str],
    grayscale_screen: bool,
    grayscale_print: bool,
    body_running_headers: bool,
    appendix_running_headers: bool,
    running_header_scope: str,
    appendix_running_header_scope: str,
) -> bool:
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

    if badge_color_overrides:
        for macro, expr in badge_color_overrides.items():
            lines.append(f"\\providecommand{{{macro}}}{{}}")
            lines.append(f"\\renewcommand{{{macro}}}{{{expr}}}")
        has_overrides = True

    if grayscale_screen:
        lines.append("\\providecommand{\\RenderGrayscaleScreen}{0}")
        lines.append("\\renewcommand{\\RenderGrayscaleScreen}{1}")
        has_overrides = True
    if grayscale_print:
        lines.append("\\providecommand{\\RenderGrayscalePrint}{0}")
        lines.append("\\renewcommand{\\RenderGrayscalePrint}{1}")
        has_overrides = True

    if body_running_headers:
        lines.append("\\providecommand{\\BodyRunningHeadersEnabled}{0}")
        lines.append("\\renewcommand{\\BodyRunningHeadersEnabled}{1}")
        has_overrides = True
    if appendix_running_headers:
        lines.append("\\providecommand{\\AppendixRunningHeadersEnabled}{0}")
        lines.append("\\renewcommand{\\AppendixRunningHeadersEnabled}{1}")
        has_overrides = True

    if running_header_scope and running_header_scope != "chapter":
        lines.append("\\providecommand{\\RunningHeaderScope}{chapter}")
        lines.append(f"\\renewcommand{{\\RunningHeaderScope}}{{{running_header_scope}}}")
        has_overrides = True

    if appendix_running_header_scope and appendix_running_header_scope != "chapter":
        lines.append("\\providecommand{\\AppendixRunningHeaderScope}{chapter}")
        lines.append(
            f"\\renewcommand{{\\AppendixRunningHeaderScope}}{{{appendix_running_header_scope}}}"
        )
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
    grayscale_setting = layout.get("render_grayscale")
    grayscale_screen = False
    grayscale_print = False
    if isinstance(grayscale_setting, dict):
        grayscale_screen = _config_bool(grayscale_setting.get("pdf_screen"), False)
        grayscale_print = _config_bool(grayscale_setting.get("pdf_print"), False)
    elif grayscale_setting is not None:
        grayscale_flag = _config_bool(grayscale_setting, False)
        grayscale_screen = grayscale_flag
        grayscale_print = grayscale_flag
    glyph_luma_offset = _config_luma_offset(layout.get("glyph_background_luma_offset"), 0.0)
    badge_luma_offset = _config_luma_offset(layout.get("badge_background_luma_offset"), 0.0)
    glyph_palette_choice = layout.get("glyph_background_palette")
    badge_palette_choice = layout.get("badge_background_palette")

    glyph_luma_offset, glyph_palette_name = select_luma_offset(
        "glyph", glyph_palette_choice, glyph_luma_offset
    )
    badge_luma_offset, badge_palette_name = select_luma_offset(
        "badge", badge_palette_choice, badge_luma_offset
    )

    if glyph_palette_choice and glyph_palette_name is None:
        print(
            f"-- Warning: Unknown glyph_background_palette '{glyph_palette_choice}' (falling back to manual offset)"
        )
    if badge_palette_choice and badge_palette_name is None:
        print(
            f"-- Warning: Unknown badge_background_palette '{badge_palette_choice}' (falling back to manual offset)"
        )
    glyph_force_white = _config_bool(layout.get("glyph_background_force_white"), False)
    badge_color_overrides = _resolve_pdf_color_overrides(
        glyph_luma_offset,
        badge_luma_offset,
        glyph_force_white,
    )

    running_headers = layout.get("running_headers")
    body_running_headers = False
    appendix_running_headers = False
    running_header_scope = "chapter"
    appendix_running_header_scope = "chapter"
    if isinstance(running_headers, dict):
        body_running_headers = _config_bool(running_headers.get("body"), False)
        appendix_running_headers = _config_bool(running_headers.get("appendices"), False)
        running_header_scope = _config_running_header_scope(running_headers.get("scope"))
        appendix_running_header_scope = _config_appendix_running_header_scope(
            running_headers.get("appendix_scope")
        )

    css_path = build_dir / CSS_OVERRIDE_NAME
    pdf_path = build_dir / PDF_OVERRIDE_NAME

    css_written = _write_css_override(
        css_path,
        fonts,
        page_break_level,
        glyph_luma_offset,
        badge_luma_offset,
        glyph_force_white,
    )
    pdf_written = _write_pdf_override(
        pdf_path,
        fonts,
        margins,
        page_break_level,
        badge_color_overrides,
        grayscale_screen,
        grayscale_print,
        body_running_headers,
        appendix_running_headers,
        running_header_scope,
        appendix_running_header_scope,
    )

    if not css_written and css_path.exists():
        css_path.unlink(missing_ok=True)
    if not pdf_written and pdf_path.exists():
        pdf_path.unlink(missing_ok=True)


__all__ = [
    "CSS_OVERRIDE_NAME",
    "PDF_OVERRIDE_NAME",
    "apply",
]
