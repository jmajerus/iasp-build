#!/usr/bin/env python3
"""MCP server for article AI-disclosure + Ghost markdown automation.

Tools:
- article_ai_metadata_get
- article_ai_metadata_update
- article_build_markdown
- article_update_and_build
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iasp_tooling.build_book import build_article_markdown, find_article_source

PROTOCOL_VERSION = "2024-11-05"


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}

    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None

        if line in (b"\r\n", b"\n"):
            break

        decoded = line.decode("utf-8", errors="replace").strip()
        if not decoded:
            break

        if ":" not in decoded:
            continue

        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    content_length_raw = headers.get("content-length")
    if not content_length_raw:
        return None

    try:
        content_length = int(content_length_raw)
    except ValueError:
        return None

    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None

    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _write_message(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _send_response(msg_id: Any, result: dict[str, Any]) -> None:
    _write_message({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _send_error(msg_id: Any, code: int, message: str) -> None:
    _write_message(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
    )


def _tool_response(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _resolve_article(article: str) -> Path:
    return find_article_source(article)


def _sidecar_path(article_path: Path) -> Path:
    return article_path.with_suffix(".ai.json")


def _load_sidecar(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_sidecar(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _tool_article_ai_metadata_get(args: dict[str, Any]) -> dict[str, Any]:
    article_spec = str(args.get("article", "")).strip()
    if not article_spec:
        return _tool_response("Missing required argument: article", is_error=True)

    article_path = _resolve_article(article_spec)
    sidecar = _sidecar_path(article_path)
    payload = _load_sidecar(sidecar)

    return _tool_response(
        json.dumps(
            {
                "article": str(article_path.relative_to(ROOT)),
                "sidecar": str(sidecar.relative_to(ROOT)),
                "metadata": payload,
            },
            indent=2,
        )
    )


def _tool_article_ai_metadata_update(args: dict[str, Any]) -> dict[str, Any]:
    article_spec = str(args.get("article", "")).strip()
    if not article_spec:
        return _tool_response("Missing required argument: article", is_error=True)

    article_path = _resolve_article(article_spec)
    sidecar = _sidecar_path(article_path)
    payload = _load_sidecar(sidecar)

    turns_raw = payload.get("turns", 0)
    try:
        turns = int(turns_raw)
    except (TypeError, ValueError):
        turns = 0

    set_turns = args.get("set_turns")
    if set_turns is not None:
        turns = max(0, int(set_turns))

    inc_turns = args.get("inc_turns")
    if inc_turns is not None:
        turns = max(0, turns + int(inc_turns))

    fuzzy_min_raw = payload.get("turns_fuzzy_min")
    fuzzy_max_raw = payload.get("turns_fuzzy_max")
    try:
        fuzzy_min = int(fuzzy_min_raw) if fuzzy_min_raw is not None else None
    except (TypeError, ValueError):
        fuzzy_min = None
    try:
        fuzzy_max = int(fuzzy_max_raw) if fuzzy_max_raw is not None else None
    except (TypeError, ValueError):
        fuzzy_max = None

    set_fuzzy_min = args.get("set_fuzzy_min")
    if set_fuzzy_min is not None:
        fuzzy_min = max(0, int(set_fuzzy_min))

    set_fuzzy_max = args.get("set_fuzzy_max")
    if set_fuzzy_max is not None:
        fuzzy_max = max(0, int(set_fuzzy_max))

    clear_fuzzy = bool(args.get("clear_fuzzy", False))
    if clear_fuzzy:
        fuzzy_min = None
        fuzzy_max = None

    if fuzzy_min is not None and fuzzy_max is not None and fuzzy_max < fuzzy_min:
        fuzzy_min, fuzzy_max = fuzzy_max, fuzzy_min

    bucket_override_raw = payload.get("turns_bucket_override")
    bucket_override = str(bucket_override_raw).strip() if bucket_override_raw is not None else None

    set_bucket_override = args.get("set_bucket_override")
    if set_bucket_override is not None:
        cleaned = str(set_bucket_override).strip()
        bucket_override = cleaned or None

    clear_bucket_override = bool(args.get("clear_bucket_override", False))
    if clear_bucket_override:
        bucket_override = None

    init_defaults = bool(args.get("init_defaults", False))
    if init_defaults:
        payload.setdefault(
            "ai_disclosure",
            "AI Disclosure: This text was generated via a {turns}-turn drafting session with Claude Sonnet.",
        )
        payload.setdefault(
            "technical_note",
            "Technical Note: This article was published via a custom automated build pipeline co-engineered with ChatGPT.",
        )

    if "ai_disclosure" in args and args.get("ai_disclosure") is not None:
        payload["ai_disclosure"] = str(args.get("ai_disclosure"))

    if "technical_note" in args and args.get("technical_note") is not None:
        payload["technical_note"] = str(args.get("technical_note"))

    payload["turns"] = turns
    if fuzzy_min is not None:
        payload["turns_fuzzy_min"] = fuzzy_min
    else:
        payload.pop("turns_fuzzy_min", None)

    if fuzzy_max is not None:
        payload["turns_fuzzy_max"] = fuzzy_max
    else:
        payload.pop("turns_fuzzy_max", None)

    if bucket_override:
        payload["turns_bucket_override"] = bucket_override
    else:
        payload.pop("turns_bucket_override", None)

    _write_sidecar(sidecar, payload)

    return _tool_response(
        json.dumps(
            {
                "article": str(article_path.relative_to(ROOT)),
                "sidecar": str(sidecar.relative_to(ROOT)),
                "turns": turns,
                "metadata": payload,
            },
            indent=2,
        )
    )


def _tool_article_build_markdown(args: dict[str, Any]) -> dict[str, Any]:
    article_spec = str(args.get("article", "")).strip()
    if not article_spec:
        return _tool_response("Missing required argument: article", is_error=True)

    article_path = _resolve_article(article_spec)
    output_hint = args.get("output")
    output_hint_str = str(output_hint) if output_hint is not None else None

    build_article_markdown(article_path, output_hint_str)

    return _tool_response(
        json.dumps(
            {
                "article": str(article_path.relative_to(ROOT)),
                "status": "built",
                "target": output_hint_str or "build/ghost/<stem>-ghost.md",
            },
            indent=2,
        )
    )


def _tool_article_update_and_build(args: dict[str, Any]) -> dict[str, Any]:
    update_result = _tool_article_ai_metadata_update(args)
    if update_result.get("isError"):
        return update_result

    build_result = _tool_article_build_markdown(args)
    if build_result.get("isError"):
        return build_result

    update_text = update_result["content"][0]["text"]
    build_text = build_result["content"][0]["text"]
    return _tool_response(update_text + "\n\n" + build_text)


def _list_tools() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "article_ai_metadata_get",
                "description": "Get per-article AI disclosure metadata sidecar (.ai.json).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "article": {"type": "string", "description": "Article path or slug."}
                    },
                    "required": ["article"],
                },
            },
            {
                "name": "article_ai_metadata_update",
                "description": "Create/update AI disclosure metadata and turn count for an article.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "article": {"type": "string", "description": "Article path or slug."},
                        "set_turns": {"type": "integer", "minimum": 0},
                        "inc_turns": {"type": "integer"},
                        "set_fuzzy_min": {"type": "integer", "minimum": 0},
                        "set_fuzzy_max": {"type": "integer", "minimum": 0},
                        "clear_fuzzy": {"type": "boolean"},
                        "set_bucket_override": {"type": "string"},
                        "clear_bucket_override": {"type": "boolean"},
                        "init_defaults": {"type": "boolean"},
                        "ai_disclosure": {"type": "string"},
                        "technical_note": {"type": "string"},
                    },
                    "required": ["article"],
                },
            },
            {
                "name": "article_build_markdown",
                "description": "Build Ghost-ready Markdown for one article (includes disclosures + Works Cited).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "article": {"type": "string", "description": "Article path or slug."},
                        "output": {"type": "string", "description": "Optional output file or directory."},
                    },
                    "required": ["article"],
                },
            },
            {
                "name": "article_update_and_build",
                "description": "Update AI metadata/turns and build article markdown in one call.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "article": {"type": "string", "description": "Article path or slug."},
                        "set_turns": {"type": "integer", "minimum": 0},
                        "inc_turns": {"type": "integer"},
                        "set_fuzzy_min": {"type": "integer", "minimum": 0},
                        "set_fuzzy_max": {"type": "integer", "minimum": 0},
                        "clear_fuzzy": {"type": "boolean"},
                        "set_bucket_override": {"type": "string"},
                        "clear_bucket_override": {"type": "boolean"},
                        "init_defaults": {"type": "boolean"},
                        "ai_disclosure": {"type": "string"},
                        "technical_note": {"type": "string"},
                        "output": {"type": "string", "description": "Optional output file or directory."},
                    },
                    "required": ["article"],
                },
            },
        ]
    }


def _handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        return _tool_response("Tool arguments must be an object.", is_error=True)

    try:
        if name == "article_ai_metadata_get":
            return _tool_article_ai_metadata_get(args)
        if name == "article_ai_metadata_update":
            return _tool_article_ai_metadata_update(args)
        if name == "article_build_markdown":
            return _tool_article_build_markdown(args)
        if name == "article_update_and_build":
            return _tool_article_update_and_build(args)
        return _tool_response(f"Unknown tool: {name}", is_error=True)
    except SystemExit as exc:
        return _tool_response(f"Tool failed: {exc}", is_error=True)
    except Exception as exc:  # noqa: BLE001
        return _tool_response(f"Tool failed: {exc}", is_error=True)


def main() -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0

        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            client_version = params.get("protocolVersion")
            protocol_version = client_version or PROTOCOL_VERSION
            _send_response(
                msg_id,
                {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "iasp-article-assist",
                        "version": "0.1.0",
                    },
                },
            )
            continue

        if method == "notifications/initialized":
            continue

        if method == "ping":
            _send_response(msg_id, {})
            continue

        if method == "tools/list":
            _send_response(msg_id, _list_tools())
            continue

        if method == "tools/call":
            _send_response(msg_id, _handle_tools_call(params))
            continue

        if msg_id is not None:
            _send_error(msg_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
