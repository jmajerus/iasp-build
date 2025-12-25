#!/usr/bin/env python3
"""Cycle through profiles defined in build-profiles.json.

Usage: python3 iasp_tooling/scripts/toggle_build_profile.py

The script updates .vscode/current-profile.json with the next profile name,
printing the new value so status-bar widgets (or run tasks) can display it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES_FILE = ROOT / "build-profiles.json"
STATE_FILE = ROOT / ".vscode" / "current-profile.json"
SETTINGS_FILE = ROOT / ".vscode" / "settings.json"

BUTTON_TASK = "Toggle Build Profile"
BUTTON_LABEL_TEMPLATE = "$(sync) Profile: {profile}"
BUTTON_TOOLTIP_TEMPLATE = "Active build profile: {profile}. Click to cycle."


def load_profiles() -> list[str]:
    if not PROFILES_FILE.exists():
        print("No build-profiles.json found.", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Unable to parse build-profiles.json: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict) or not data:
        print("build-profiles.json must contain a JSON object with at least one profile.", file=sys.stderr)
        sys.exit(1)

    return list(data.keys())


def load_current() -> str:
    if not STATE_FILE.exists():
        return "default"
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "default"
    if isinstance(raw, dict) and isinstance(raw.get("profile"), str):
        return raw["profile"]
    return "default"


def save_current(name: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"profile": name}, indent=2) + "\n", encoding="utf-8")


def update_status_button(name: str) -> None:
    if not SETTINGS_FILE.exists():
        return
    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Warning: unable to parse {SETTINGS_FILE.name}: {exc}", file=sys.stderr)
        return

    task_buttons = settings.get("VsCodeTaskButtons.tasks")
    if not isinstance(task_buttons, list):
        return

    changed = False
    for entry in task_buttons:
        if not isinstance(entry, dict) or entry.get("task") != BUTTON_TASK:
            continue
        desired_label = BUTTON_LABEL_TEMPLATE.format(profile=name)
        desired_tooltip = BUTTON_TOOLTIP_TEMPLATE.format(profile=name)
        if entry.get("label") != desired_label:
            entry["label"] = desired_label
            changed = True
        if entry.get("tooltip") != desired_tooltip:
            entry["tooltip"] = desired_tooltip
            changed = True
        break
    else:
        return

    if changed:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    profiles = load_profiles()
    current = load_current()
    if current not in profiles:
        current = profiles[0]

    index = profiles.index(current)
    next_index = (index + 1) % len(profiles)
    next_profile = profiles[next_index]

    save_current(next_profile)
    update_status_button(next_profile)
    print(next_profile)


if __name__ == "__main__":
    main()
