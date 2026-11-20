"""Generate VS Code tasks from iasp-config."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..paths import project_root
from . import config as iasp_config

ROOT = project_root()
VSCODE_DIR = ROOT / ".vscode"
TASKS_PATH = VSCODE_DIR / "tasks.json"
WORKSPACE_VAR = "${workspaceFolder}"
BUILD_SCRIPT = f"{WORKSPACE_VAR}/build_book.py"
SCRIPTS_DIR = f"{WORKSPACE_VAR}/scripts"
PROFILE_ENV = {"BUILD_PROFILE": "${input:currentBuildProfile}"}
PRESENTATION = {"reveal": "always", "panel": "dedicated"}
EMPTY_MATCHER: list[str] = []


def _section() -> dict[str, Any]:
    value = iasp_config.get("tasks", default={})
    return value if isinstance(value, dict) else {}


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, bool):
        return value
    return default


def _string(value: Any, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _task_base(label: str, args: List[str], *, use_env: bool = True, group_default: bool = False) -> Dict[str, Any]:
    task: Dict[str, Any] = {
        "label": label,
        "type": "shell",
        "command": "python3",
        "args": args,
        "options": {
            "cwd": WORKSPACE_VAR,
        },
        "group": {"kind": "build", "isDefault": True} if group_default else "build",
        "presentation": PRESENTATION,
        "problemMatcher": EMPTY_MATCHER,
    }
    if use_env:
        task["options"]["env"] = PROFILE_ENV
    return task


def _build_tasks_from_outputs(entries: list[Any], default_claimed: bool) -> tuple[List[Dict[str, Any]], bool]:
    tasks: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not _bool(entry.get("enabled", True), True):
            continue
        name = _string(entry.get("name"), entry.get("target"))
        target = _string(entry.get("target"))
        if not name or not target:
            continue
        default_flag = _bool(entry.get("default"), False)
        should_be_default = default_flag and not default_claimed
        draft = _string(entry.get("draft_target"))
        full_label = f"Build {name} (full)" if draft else f"Build {name}"
        tasks.append(
            _task_base(
                label=full_label,
                args=[BUILD_SCRIPT, target],
                group_default=should_be_default,
            )
        )
        if should_be_default:
            default_claimed = True
        if draft:
            tasks.append(
                _task_base(
                    label=f"Build {name} (draft)",
                    args=[BUILD_SCRIPT, draft],
                )
            )
    return tasks, default_claimed


def _build_tasks_from_bundles(entries: list[Any], default_claimed: bool) -> tuple[List[Dict[str, Any]], bool]:
    tasks: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not _bool(entry.get("enabled", True), True):
            continue
        name = _string(entry.get("name"), entry.get("target"))
        target = _string(entry.get("target"))
        if not name or not target:
            continue
        default_flag = _bool(entry.get("default"), False)
        should_be_default = default_flag and not default_claimed
        draft = _string(entry.get("draft_target"))
        full_label = f"Build {name} (full)" if draft else f"Build {name}"
        tasks.append(
            _task_base(
                label=full_label,
                args=[BUILD_SCRIPT, target],
                group_default=should_be_default,
            )
        )
        if should_be_default:
            default_claimed = True
        if draft:
            tasks.append(
                _task_base(
                    label=f"Build {name} (draft)",
                    args=[BUILD_SCRIPT, draft],
                )
            )
    return tasks, default_claimed


def _auxiliary_tasks(aux: dict[str, Any]) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    if _bool(aux.get("drive_sync"), True) and (ROOT / "scripts" / "sync_builds_to_drive.py").is_file():
        tasks.append(
            _task_base(
                label="Drive sync (latest build)",
                args=[f"{SCRIPTS_DIR}/sync_builds_to_drive.py"],
            )
        )
    if _bool(aux.get("build_articles"), False):
        tasks.append(
            _task_base(
                label="Build Articles",
                args=[BUILD_SCRIPT, "articles"],
            )
        )
    if _bool(aux.get("prepare_patch"), True) and (ROOT / "scripts" / "bump_patch_version.py").is_file():
        tasks.append(
            _task_base(
                label="Prepare next patch version",
                args=[f"{SCRIPTS_DIR}/bump_patch_version.py"],
                use_env=False,
            )
        )
    if _bool(aux.get("toggle_profile"), True) and (ROOT / "scripts" / "toggle_build_profile.py").is_file():
        tasks.append(
            _task_base(
                label="Toggle Build Profile",
                args=[f"{SCRIPTS_DIR}/toggle_build_profile.py"],
                use_env=False,
            )
        )
    return tasks


def _ensure_default(tasks: List[Dict[str, Any]]) -> None:
    if any(isinstance(task.get("group"), dict) and task["group"].get("isDefault") for task in tasks):
        return
    for task in tasks:
        if task.get("group") == "build":
            task["group"] = {"kind": "build", "isDefault": True}
            return


def _inputs_block() -> List[Dict[str, Any]]:
    return [
        {
            "id": "currentBuildProfile",
            "type": "command",
            "command": "extension.commandvariable.file.content",
            "args": {
                "fileName": f"{WORKSPACE_VAR}/.vscode/current-profile.json",
                "json": "content.profile",
                "default": "default",
            },
        }
    ]


def _build_payload(settings: dict[str, Any]) -> Dict[str, Any] | None:
    if not _bool(settings.get("manage_vscode_tasks", True), True):
        return None

    tasks: List[Dict[str, Any]] = []
    default_claimed = False

    outputs = settings.get("outputs")
    if isinstance(outputs, list):
        new_tasks, default_claimed = _build_tasks_from_outputs(outputs, default_claimed)
        tasks.extend(new_tasks)

    bundles = settings.get("bundles")
    if isinstance(bundles, list):
        new_tasks, default_claimed = _build_tasks_from_bundles(bundles, default_claimed)
        tasks.extend(new_tasks)

    aux = settings.get("auxiliary") if isinstance(settings.get("auxiliary"), dict) else {}
    tasks.extend(_auxiliary_tasks(aux))

    if not tasks:
        return None

    _ensure_default(tasks)

    if _bool(settings.get("use_workspace_venv"), False):
        for task in tasks:
            task["type"] = "process"
            task["command"] = f"{WORKSPACE_VAR}/.venv/bin/python"
            task["windows"] = {"command": rf"{WORKSPACE_VAR}\.venv\Scripts\python.exe"}

    return {
        "version": "2.0.0",
        "tasks": tasks,
        "inputs": _inputs_block(),
    }


def sync() -> None:
    if not (ROOT / "build_book.py").is_file():
        return

    settings = _section()
    payload = _build_payload(settings)
    if payload is None:
        return

    serialized = json.dumps(payload, indent=2) + "\n"

    try:
        current = TASKS_PATH.read_text(encoding="utf-8") if TASKS_PATH.exists() else None
    except OSError:
        current = None

    if current == serialized:
        return

    VSCODE_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_PATH.write_text(serialized, encoding="utf-8")


__all__ = ["sync"]
