#!/usr/bin/env python3
"""ghost_export.py — Export an IASP article as Ghost-compatible Markdown.

Resolves ::: include directives and converts semantic fenced blocks (note
variants, sidebars, callouts, bridges, etc.) to HTML <div> wrappers. The
*content* inside every wrapper is left as plain Markdown so Ghost's native
Markdown card renders footnotes, bold, links, etc. without any special
handling.

CommonMark HTML block behaviour makes this work: a <div> on its own line
starts a Type-6 HTML block which ends at the next blank line. Subsequent
Markdown is processed normally by the parser, and the browser places the
rendered output inside the still-open <div>.

Usage:
    python3 iasp_tooling/scripts/ghost_export.py articles/my-article.md
    python3 iasp_tooling/scripts/ghost_export.py articles/my-article.md -o out.md
    python3 iasp_tooling/scripts/ghost_export.py articles/my-article.md --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKS_CITED_HEADING_RE = re.compile(r"^\s*##+\s+Works Cited\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Style palette — note variants
# Each entry: bg, border, badge_bg, badge_fg, glyph, label
# Set glyph_only=True for variants that show just an inline glyph (no badge).
# ---------------------------------------------------------------------------

_V = dict  # shorthand

VARIANT_STYLES: dict[str, dict] = {
    "idea":           _V(bg="#fffdf0", border="#e0c84a", badge_bg="#e5c22a", badge_fg="#4a3800", glyph="💡", label="IDEA",           glyph_only=True),
    "insight":        _V(bg="#f0f4fa", border="#5b7fa6", badge_bg="#5b7fa6", badge_fg="#ffffff", glyph="⁂", label="INSIGHT"),
    "insight-major":  _V(bg="#dce8f5", border="#2a5fa5", badge_bg="#2a5fa5", badge_fg="#ffffff", glyph="⁂", label="INSIGHT"),
    "warning":        _V(bg="#fff8eb", border="#d97706", badge_bg="#d97706", badge_fg="#ffffff", glyph="⚠", label="WARNING"),
    "breadcrumb":     _V(bg="#f5f5f5", border="#9ca3af", badge_bg="#9ca3af", badge_fg="#ffffff", glyph="›", label="BREADCRUMB"),
    "transition":     _V(bg="#f4f0ff", border="#9b7fd4", badge_bg="#9b7fd4", badge_fg="#ffffff", glyph="⇥", label="TRANSITION", glyph_only=True),
    "usage":          _V(bg="#e8f0fe", border="#1a73e8", badge_bg="#1a73e8", badge_fg="#ffffff", glyph="⚙", label="USAGE"),
    "integration":    _V(bg="#e0f7f4", border="#00897b", badge_bg="#00897b", badge_fg="#ffffff", glyph="∞", label="INTEGRATION"),
    "responsibility": _V(bg="#fff8e1", border="#f9a825", badge_bg="#f9a825", badge_fg="#4a3200", glyph="⚖", label="RESPONSIBILITY"),
    "reflexive":      _V(bg="#f0f4f8", border="#546e7a", badge_bg="#546e7a", badge_fg="#ffffff", glyph="⟲", label="REFLEXIVE"),
    "synthesis":      _V(bg="#e8f5e9", border="#388e3c", badge_bg="#388e3c", badge_fg="#ffffff", glyph="⊕", label="SYNTHESIS"),
    "disclosure":     _V(bg="#f3e5f5", border="#7b1fa2", badge_bg="#7b1fa2", badge_fg="#ffffff", glyph="◊", label="DISCLOSURE"),
    "ai":             _V(bg="#eef6ff", border="#2563eb", badge_bg="#1d4ed8", badge_fg="#ffffff", glyph="◇", label="AI DISCLOSURE"),
    "orientation":    _V(bg="#e0f2f1", border="#00796b", badge_bg="#00796b", badge_fg="#ffffff", glyph="⇢", label="ORIENTATION"),
    "navigation":     _V(bg="#e0f2f1", border="#00796b", badge_bg="#00796b", badge_fg="#ffffff", glyph="⇢", label="NAVIGATION"),
    "bridge":         _V(bg="#ede7f6", border="#673ab7", badge_bg="#673ab7", badge_fg="#ffffff", glyph="—",  label="BRIDGE"),
    "contrast":       _V(bg="#fff3e0", border="#f57c00", badge_bg="#f57c00", badge_fg="#ffffff", glyph="⇆", label="CONTRAST", glyph_only=True),
    "misuse":         _V(bg="#ffebee", border="#c62828", badge_bg="#c62828", badge_fg="#ffffff", glyph="✕", label="MISUSE"),
    "diagnostic":     _V(bg="#e3f2fd", border="#1565c0", badge_bg="#1565c0", badge_fg="#ffffff", glyph="🔍", label="DIAGNOSTIC"),
    "closing":        _V(bg="#f5f5f5", border="#9e9e9e", badge_bg="#757575", badge_fg="#ffffff", glyph="∎", label="CLOSING NOTE"),
    "methodology":    _V(bg="#e8eaf6", border="#3949ab", badge_bg="#3949ab", badge_fg="#ffffff", glyph="⊢", label="METHODOLOGY"),
    "context":        _V(bg="#f5f0eb", border="#78716c", badge_bg="#78716c", badge_fg="#ffffff", glyph="◉", label="CONTEXT"),
    "scope":          _V(bg="#fdf0e7", border="#b45309", badge_bg="#b45309", badge_fg="#ffffff", glyph="◎", label="SCOPE"),
    "checklist":      _V(bg="#e0f7f4", border="#00838f", badge_bg="#00838f", badge_fg="#ffffff", glyph="☐", label="CHECKLIST"),
    "prelude":        _V(bg="#f9f9f9", border="#aaaaaa", badge_bg="#aaaaaa", badge_fg="#ffffff", glyph="◈", label="PRELUDE"),
}

SIDEBAR_STYLE  = _V(bg="#f8f9fa", border="#6b7280", badge_bg="#374151", badge_fg="#ffffff", glyph="🗒", label="SIDEBAR")
CALLOUT_STYLE  = _V(bg="#f0f7ff", border="#3b82f6", badge_bg="#3b82f6", badge_fg="#ffffff", glyph="◆", label="CALLOUT")
BRIDGE_STYLE   = _V(bg="#f6f2ff", border="#6f58b9", badge_bg="#6f58b9", badge_fg="#ffffff", glyph="⬡", label="BRIDGE")
EXAMPLE_STYLE  = _V(bg="#eff6ff", border="#3b82f6", badge_bg="#3b82f6", badge_fg="#ffffff", glyph="◆", label="EXAMPLE")
DEFN_STYLE     = _V(bg="#f0fdf4", border="#22c55e", badge_bg="#16a34a", badge_fg="#ffffff", glyph="≡", label="DEFINITION")

# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class TextLine:
    text: str

@dataclass
class FenceNode:
    classes: list[str]
    attrs: dict[str, str]
    children: list[Union["TextLine", "FenceNode"]] = field(default_factory=list)

Node = Union[TextLine, FenceNode]

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_FENCE_OPENER_RE = re.compile(r"^:::\s*(.+)$")
_FENCE_CLOSER_RE = re.compile(r"^:::\s*$")


def _parse_fence_header(line: str) -> tuple[list[str] | None, dict[str, str]]:
    """Return (classes, attrs) for a fence opener, or (None, {}) for a non-fence line."""
    stripped = line.strip()
    if not stripped.startswith(":::"):
        return None, {}
    rest = stripped[3:].strip()
    if not rest:
        return None, {}  # closer — not an opener

    classes: list[str] = []
    attrs: dict[str, str] = {}

    if rest.startswith("{"):
        inner = rest.lstrip("{").rstrip("}")
        for m in re.finditer(r'\.([^\s}{\'\"=]+)|(\w[\w-]*)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))', inner):
            if m.group(1):
                for chunk in m.group(1).lower().split("."):
                    if chunk:
                        classes.append(chunk)
            elif m.group(2):
                val = m.group(3) or m.group(4) or m.group(5) or ""
                attrs[m.group(2)] = val
    else:
        parts = rest.split()
        for chunk in parts[0].split("."):
            if chunk:
                classes.append(chunk.lower())
        for part in parts[1:]:
            if part.startswith("."):
                for chunk in part[1:].split("."):
                    if chunk:
                        classes.append(chunk.lower())
            else:
                m = re.match(r'(\w[\w-]*)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))', part)
                if m:
                    attrs[m.group(1)] = m.group(2) or m.group(3) or m.group(4) or ""

    classes = [c for c in classes if c]
    return (classes or ["unknown"]), attrs


_SINGLE_LINE_FENCE_RE = re.compile(r"^(:::\s*\{[^}]+\})\s+(.*?)\s*:::$")
_INLINE_CONTENT_FENCE_RE = re.compile(r"^(:::\s*\{[^}]+\})\s+(.+?)\s*$")


def _normalize_fences(lines: list[str]) -> list[str]:
    """Normalize fence lines that carry inline content on the opener.

    Handles two cases (curly-brace class spec only, to avoid breaking
    attribute-style directives like ```::: include path="foo.md"```):

    1. Single-line self-closing: ``::: {.class} content :::`` →
       opener line, content line, ``:::`` closer line.
    2. Opener with inline content (closer on its own next line):
       ``::: {.class} content`` → opener line, content line
       (the existing closer ``:::`` remains in place).
    """
    result: list[str] = []
    for line in lines:
        stripped = line.strip()

        # Case 1: single-line self-closing fence ends with :::
        m = _SINGLE_LINE_FENCE_RE.match(stripped)
        if m:
            opener, content = m.group(1), m.group(2).strip()
            if content:
                result.extend([opener, content, ":::"])
                continue

        # Case 2: opener with inline content (curly-brace class spec only)
        m = _INLINE_CONTENT_FENCE_RE.match(stripped)
        if m:
            opener, content = m.group(1), m.group(2).strip()
            if content:
                result.append(opener)
                result.append(content)
                continue

        result.append(line)
    return result


def parse_lines(lines: list[str], start: int = 0) -> tuple[list[Node], int]:
    """Recursively parse lines into a Node list. Returns (nodes, next_index)."""
    nodes: list[Node] = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if _FENCE_CLOSER_RE.match(stripped):
            i += 1
            return nodes, i

        classes, attrs = _parse_fence_header(line)
        if classes is not None:
            i += 1
            children, i = parse_lines(lines, i)
            nodes.append(FenceNode(classes=classes, attrs=attrs, children=children))
        else:
            nodes.append(TextLine(line))
            i += 1
    return nodes, i

# ---------------------------------------------------------------------------
# HTML wrapper builders
#
# Structure produced for each block:
#
#   <div style="...container...">            ← HTML block starts here
#   <div style="...badge...">⊕ LABEL</div>  ← no blank line → same block
#                                            ← blank line ends the HTML block
#   Markdown content rendered by Ghost
#
#   </div>                                   ← new HTML block (closing tag)
#
# Because CommonMark Type-6 HTML blocks end at the first blank line, the
# content between the blank lines is parsed as ordinary Markdown.  The
# browser then places the rendered output inside the still-open container
# <div>.
# ---------------------------------------------------------------------------

_CONTAINER = (
    "background-color: {bg}; border-left: 4px solid {border}; "
    "padding: 16px 20px; margin: 20px 0; border-radius: 0 6px 6px 0; "
    "font-family: Georgia, 'Times New Roman', serif; line-height: 1.5;"
)
_BADGE = (
    "display: inline-block; background-color: {badge_bg}; color: {badge_fg}; "
    "font-size: 0.68em; font-weight: bold; text-transform: uppercase; "
    "letter-spacing: 0.1em; padding: 3px 10px; border-radius: 3px; "
    "margin-bottom: 10px; font-family: 'Helvetica Neue', Arial, sans-serif;"
)


def wrap_block(inner_md: str, style: dict, no_badge: bool = False) -> str:
    """Wrap Markdown content in a styled HTML div.

    The container <div> and optional badge <div> are placed on consecutive
    lines (one HTML block).  A blank line then ends that block so the inner
    Markdown is parsed normally by Ghost.
    """
    container_style = _CONTAINER.format(**style)
    opened = f'<div style="{container_style}">'

    if no_badge:
        html_header = f"\n{opened}"
    elif style.get("glyph_only"):
        glyph_line = f'<p style="margin: 0 0 8px 0; font-size: 1.1em;">{style["glyph"]}</p>'
        html_header = f"\n{opened}\n{glyph_line}"
    else:
        badge_style = _BADGE.format(**style)
        badge_line = f'<div style="{badge_style}">{style["glyph"]} {style["label"]}</div>'
        html_header = f"\n{opened}\n{badge_line}"

    return f"{html_header}\n\n{inner_md.strip()}\n\n</div>\n"


def wrap_epigraph(inner_md: str) -> str:
    """Render an epigraph as a Markdown blockquote."""
    lines = inner_md.strip().splitlines()
    quoted_lines = [f"> {line}" if line.strip() else ">" for line in lines]
    return "\n" + "\n".join(quoted_lines) + "\n"

# ---------------------------------------------------------------------------
# Main exporter class
# ---------------------------------------------------------------------------

class GhostExporter:
    def __init__(self, root: Path):
        self.root = root

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def export(self, input_path: Path, output_path: Path) -> None:
        body = self._render_document(input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")
        print(f"Ghost export written to: {output_path}", file=sys.stderr)

    def _render_document(self, path: Path) -> str:
        body = self._process_file(path)
        metadata = self._load_ai_metadata(path)
        return self._inject_ai_disclosures(body, metadata)

    # ------------------------------------------------------------------
    # File processing
    # ------------------------------------------------------------------

    def _process_file(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        lines = _normalize_fences(text.splitlines())
        nodes, _ = parse_lines(lines)
        return self._render_mixed(nodes, path.parent)

    def _load_ai_metadata(self, path: Path) -> dict[str, object]:
        sidecar = path.with_suffix(".ai.json")
        if not sidecar.exists():
            return {}
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _turn_bucket_label(turn_count: int) -> str:
        """Map turn count to a linguistic bucket label.
        
        DEPRECATED: This function supports legacy turns-based measurement.
        The concept of counting "turns" is imprecise and easily gamed.
        Prefer qualitative descriptions instead. This function remains
        for backwards compatibility only.
        """
        if turn_count <= 5:
            return "a few"
        if turn_count <= 9:
            return "several"
        if turn_count <= 18:
            return "around a dozen"
        if turn_count <= 48:
            return "a few dozen"
        return "dozens of"

    @staticmethod
    def _build_turn_tokens(metadata: dict[str, object]) -> dict[str, str]:
        """Build template tokens from turns metadata.
        
        DEPRECATED: This function supports legacy turns-based measurement
        via template placeholders ({turns}, {turns_bucket}, etc.).
        The turns-based approach is imprecise and not recommended for
        user-facing disclosures. This function remains for backwards
        compatibility; prefer simpler qualitative disclosure text instead.
        """
        turns_raw = metadata.get("turns", 0)
        try:
            turns = max(0, int(turns_raw))
        except (TypeError, ValueError):
            turns = 0

        fuzzy_min_raw = metadata.get("turns_fuzzy_min")
        fuzzy_max_raw = metadata.get("turns_fuzzy_max")
        fuzzy_min: int | None
        fuzzy_max: int | None
        try:
            fuzzy_min = int(fuzzy_min_raw) if fuzzy_min_raw is not None else None
        except (TypeError, ValueError):
            fuzzy_min = None
        try:
            fuzzy_max = int(fuzzy_max_raw) if fuzzy_max_raw is not None else None
        except (TypeError, ValueError):
            fuzzy_max = None

        fuzzy = ""
        representative_turns = turns
        if fuzzy_min is not None and fuzzy_max is not None:
            if fuzzy_max < fuzzy_min:
                fuzzy_min, fuzzy_max = fuzzy_max, fuzzy_min
            if fuzzy_min == fuzzy_max:
                fuzzy = f"~{fuzzy_min}"
                representative_turns = fuzzy_min
            else:
                fuzzy = f"~{fuzzy_min}-{fuzzy_max}"
                representative_turns = max(0, (fuzzy_min + fuzzy_max) // 2)

        turns_display = fuzzy or str(turns)
        override_raw = metadata.get("turns_bucket_override")
        override = str(override_raw).strip() if override_raw is not None else ""

        turns_bucket = override or GhostExporter._turn_bucket_label(representative_turns)
        if re.search(r"\bturns?\b", turns_bucket, flags=re.IGNORECASE):
            turns_bucket_phrase = turns_bucket
        else:
            turns_bucket_phrase = f"{turns_bucket} turns"

        return {
            "turns": str(turns),
            "turns_exact": str(turns),
            "turns_fuzzy": fuzzy,
            "turns_display": turns_display,
            "turns_bucket": turns_bucket,
            "turns_bucket_phrase": turns_bucket_phrase,
        }

    @staticmethod
    def _format_disclosure_line(template: str, tokens: dict[str, str]) -> str:
        safe_tokens = dict(tokens)
        safe_tokens.setdefault("turns", "0")
        safe_tokens.setdefault("turns_exact", safe_tokens["turns"])
        safe_tokens.setdefault("turns_fuzzy", "")
        safe_tokens.setdefault("turns_display", safe_tokens["turns"])
        safe_tokens.setdefault("turns_bucket", GhostExporter._turn_bucket_label(int(safe_tokens["turns"])))
        safe_tokens.setdefault("turns_bucket_phrase", f"{safe_tokens['turns_bucket']} turns")
        try:
            return template.format(**safe_tokens)
        except Exception:  # noqa: BLE001
            line = template
            for key, value in safe_tokens.items():
                line = line.replace("{" + key + "}", value)
            return line

    def _inject_ai_disclosures(self, body: str, metadata: dict[str, object]) -> str:
        if not metadata:
            return body

        # Respect hand-authored disclosure lines and avoid duplicates.
        if "AI Disclosure:" in body or "Technical Note:" in body:
            return body

        tokens = self._build_turn_tokens(metadata)

        disclosure_lines: list[str] = []

        ai_disclosure = metadata.get("ai_disclosure")
        if isinstance(ai_disclosure, str) and ai_disclosure.strip():
            disclosure_lines.append(self._format_disclosure_line(ai_disclosure.strip(), tokens))

        technical_note = metadata.get("technical_note")
        if isinstance(technical_note, str) and technical_note.strip():
            disclosure_lines.append(self._format_disclosure_line(technical_note.strip(), tokens))

        if not disclosure_lines:
            return body

        variant_raw = metadata.get("disclosure_variant", "ai")
        variant = str(variant_raw).strip().lower() if variant_raw is not None else "ai"
        style = VARIANT_STYLES.get(variant, VARIANT_STYLES["ai"])
        wrapped_disclosure = wrap_block("\n".join(disclosure_lines), style)

        lines = body.splitlines()
        insert_at = len(lines)
        for idx, line in enumerate(lines):
            if WORKS_CITED_HEADING_RE.match(line):
                insert_at = idx
                break

        wrapped_lines = wrapped_disclosure.strip("\n").splitlines()
        block = [""] + wrapped_lines + [""]
        updated = lines[:insert_at] + block + lines[insert_at:]
        return "\n".join(updated)

    # ------------------------------------------------------------------
    # Mixed-mode renderer — Markdown prose passes through unchanged;
    # semantic fenced blocks become HTML <div> wrappers with Markdown inside.
    # ------------------------------------------------------------------

    def _render_mixed(self, nodes: list[Node], base_dir: Path) -> str:
        parts: list[str] = []
        for node in nodes:
            if isinstance(node, TextLine):
                parts.append(node.text)  # all lines pass through, including [^fn]: defs
            else:
                parts.append(self._render_fence_mixed(node, base_dir))
        return "\n".join(parts)

    def _render_fence_mixed(self, fence: FenceNode, base_dir: Path) -> str:
        classes = fence.classes
        attrs = fence.attrs

        # --- Include directive ---
        if "include" in classes:
            transferred = [c for c in classes if c in ("nobadge", "no-badge", "noglyph", "no-glyph")]
            return self._resolve_include(attrs, base_dir, extra_classes=transferred)

        # --- Article wrapper: unwrap ---
        if "article" in classes:
            return self._render_mixed(fence.children, base_dir)

        # --- Note variants ---
        if "note" in classes:
            variant = self._detect_note_variant(classes)
            style = VARIANT_STYLES.get(variant, VARIANT_STYLES["insight"])
            no_badge = "nobadge" in classes or "no-badge" in classes
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, style, no_badge)

        # --- Sidebar / aside ---
        if any(c in classes for c in ("sidebar", "sidebar-block", "aside", "sidebar-inline")):
            no_badge = "nobadge" in classes or "no-badge" in classes
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, SIDEBAR_STYLE, no_badge)

        # --- Callout ---
        if "callout" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, CALLOUT_STYLE)

        # --- Bridge (block-level) ---
        if "bridge" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, BRIDGE_STYLE)

        # --- Example ---
        if "example" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, EXAMPLE_STYLE)

        # --- Definition ---
        if "definition" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, DEFN_STYLE)

        # --- Epigraph ---
        if "epigraph" in classes or "epigraph-inline" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_epigraph(inner)

        # --- Unknown / wrapper-only: unwrap and continue ---
        return self._render_mixed(fence.children, base_dir)

    # ------------------------------------------------------------------
    # Inner-Markdown renderer — used for content *inside* HTML div wrappers.
    # Text lines pass through verbatim; nested fenced blocks get their own
    # div wrappers so styling is preserved even at multiple nesting levels.
    # ------------------------------------------------------------------

    def _render_inner_markdown(self, nodes: list[Node], base_dir: Path) -> str:
        parts: list[str] = []
        for node in nodes:
            if isinstance(node, TextLine):
                parts.append(node.text)
            else:
                parts.append(self._render_fence_inner_markdown(node, base_dir))
        return "\n".join(parts)

    def _render_fence_inner_markdown(self, fence: FenceNode, base_dir: Path) -> str:
        """Render a FenceNode that appears inside an HTML div wrapper."""
        classes = fence.classes
        attrs = fence.attrs

        if "include" in classes:
            transferred = [c for c in classes if c in ("nobadge", "no-badge", "noglyph", "no-glyph")]
            return self._resolve_include(attrs, base_dir, extra_classes=transferred)

        if "article" in classes:
            return self._render_inner_markdown(fence.children, base_dir)

        if "note" in classes:
            variant = self._detect_note_variant(classes)
            style = VARIANT_STYLES.get(variant, VARIANT_STYLES["insight"])
            no_badge = "nobadge" in classes or "no-badge" in classes
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, style, no_badge)

        if any(c in classes for c in ("sidebar", "sidebar-block", "aside", "sidebar-inline")):
            no_badge = "nobadge" in classes or "no-badge" in classes
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, SIDEBAR_STYLE, no_badge)

        if "callout" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, CALLOUT_STYLE)

        if "bridge" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, BRIDGE_STYLE)

        if "example" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, EXAMPLE_STYLE)

        if "definition" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_block(inner, DEFN_STYLE)

        if "epigraph" in classes or "epigraph-inline" in classes:
            inner = self._render_inner_markdown(fence.children, base_dir)
            return wrap_epigraph(inner)

        # Default: pass content through as plain Markdown
        return self._render_inner_markdown(fence.children, base_dir)

    # ------------------------------------------------------------------
    # Include resolution
    # ------------------------------------------------------------------

    def _resolve_include(
        self,
        attrs: dict[str, str],
        base_dir: Path,
        extra_classes: list[str] | None = None,
    ) -> str:
        path_str = attrs.get("path", "")
        if not path_str:
            return "<!-- empty include path -->"
        # Try project-root-relative first (matching Pandoc CWD behaviour),
        # then fall back to base_dir-relative for includes within nested files.
        candidate_root = (self.root / path_str).resolve()
        candidate_rel = (base_dir / path_str).resolve()
        if candidate_root.exists():
            inc_path = candidate_root
        elif candidate_rel.exists():
            inc_path = candidate_rel
        else:
            return f"<!-- include not found: {path_str} -->"
        inc_text = inc_path.read_text(encoding="utf-8")
        inc_nodes, _ = parse_lines(_normalize_fences(inc_text.splitlines()))
        # Transfer modifier classes (e.g. nobadge) to the outermost FenceNode
        if extra_classes:
            for node in inc_nodes:
                if isinstance(node, FenceNode):
                    for cls in extra_classes:
                        if cls not in node.classes:
                            node.classes.append(cls)
                    break
        return self._render_mixed(inc_nodes, inc_path.parent)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_note_variant(classes: list[str]) -> str:
        if "insight" in classes and "major" in classes:
            return "insight-major"
        for v in VARIANT_STYLES:
            if v in classes:
                return v
        return "insight"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _default_output(input_path: Path) -> Path:
    stem = input_path.stem
    return PROJECT_ROOT / "build" / "ghost" / f"{stem}-ghost.md"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="Article Markdown file to export")
    p.add_argument("-o", "--output", default=None, help="Output file path (default: build/ghost/<stem>-ghost.md)")
    p.add_argument("--dry-run", action="store_true", help="Print output to stdout instead of writing a file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = (PROJECT_ROOT / input_path).resolve()
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    exporter = GhostExporter(PROJECT_ROOT)

    if args.dry_run:
        print(exporter._render_document(input_path))
        return 0

    output_path = Path(args.output) if args.output else _default_output(input_path)
    if not output_path.is_absolute():
        output_path = (PROJECT_ROOT / output_path).resolve()

    exporter.export(input_path, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
