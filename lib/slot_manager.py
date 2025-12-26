"""Helpers for updating standardized slot markers inside text files."""

from __future__ import annotations

from pathlib import Path

__all__ = ["slot_markers", "replace_slot_content", "update_slot_file"]


def _normalize_slot_name(slot: str) -> str:
    cleaned = (slot or "").strip()
    if not cleaned:
        raise ValueError("Slot name cannot be empty")
    return cleaned.replace(" ", "-").replace("::", ":").upper()


def slot_markers(slot: str) -> tuple[str, str]:
    name = _normalize_slot_name(slot)
    return f"<!-- SLOT:{name}:START -->", f"<!-- SLOT:{name}:END -->"


def replace_slot_content(text: str, slot: str, new_content: str) -> str:
    start_marker, end_marker = slot_markers(slot)
    start_idx = text.find(start_marker)
    if start_idx == -1:
        raise ValueError(f"Start marker {start_marker} not found")
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1:
        raise ValueError(f"End marker {end_marker} not found")

    start_close = start_idx + len(start_marker)
    before = text[:start_close]
    after = text[end_idx:]

    body = new_content.rstrip() + "\n"
    newline = "\n" if not before.endswith("\n") else ""

    return f"{before}{newline}\n{body}{after}"


def update_slot_file(path: Path | str, slot: str, new_content: str) -> None:
    file_path = Path(path)
    original = file_path.read_text(encoding="utf-8")
    updated = replace_slot_content(original, slot, new_content)
    file_path.write_text(updated, encoding="utf-8")
