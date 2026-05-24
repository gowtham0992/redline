#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def main() -> int:
    args = _parser().parse_args()
    prompts = _read_prompts(args.prompts)
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    for spec in args.logs:
        tool, path = _parse_log_spec(spec)
        rows = _read_rows(path)
        rows = _drop_recording_instruction(rows, expected=len(prompts))
        if len(rows) != len(prompts):
            raise SystemExit(
                f"{path}: expected {len(prompts)} task rows after filtering, got {len(rows)}"
            )

        target = output_dir / f"{_slug(tool)}.jsonl"
        with target.open("w", encoding="utf-8") as handle:
            for index, (prompt, row) in enumerate(zip(prompts, rows), 1):
                raw_metadata = row.get("metadata")
                metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
                normalized = {
                    "case_id": f"task_{index:02d}",
                    "prompt": prompt,
                    "response": str(row.get("response", "")),
                    "metadata": {
                        **metadata,
                        "tool": tool,
                        "task_index": index,
                        "original_prompt": str(row.get("prompt", "")),
                    },
                }
                handle.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"wrote {target} ({len(rows)} rows)")

    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize AI assistant session JSONL exports for redline dogfood comparisons.",
    )
    parser.add_argument("--prompts", required=True, help="canonical prompt JSONL file")
    parser.add_argument("--out", required=True, help="output directory for normalized logs")
    parser.add_argument("logs", nargs="+", help="tool=path JSONL exports, for example claude=.redline/private/claude.jsonl")
    return parser


def _read_prompts(path: str) -> list[str]:
    prompts = []
    for line_number, row in _iter_jsonl(Path(path)):
        prompt = row.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SystemExit(f"{path}:{line_number} missing prompt string")
        prompts.append(prompt)
    if not prompts:
        raise SystemExit(f"{path}: expected at least one prompt")
    return prompts


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows = [row for _, row in _iter_jsonl(path)]
    if not rows:
        raise SystemExit(f"{path}: expected at least one JSONL row")
    for index, row in enumerate(rows, 1):
        if not isinstance(row.get("prompt"), str):
            raise SystemExit(f"{path}:{index} missing prompt string")
        if not isinstance(row.get("response"), str):
            raise SystemExit(f"{path}:{index} missing response string")
    return rows


def _iter_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise SystemExit(f"{path}: not found") from exc

    rows = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_number} invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise SystemExit(f"{path}:{line_number} expected a JSON object")
        rows.append((line_number, row))
    return rows


def _drop_recording_instruction(rows: list[dict[str, Any]], *, expected: int) -> list[dict[str, Any]]:
    if len(rows) == expected + 1 and _looks_like_recording_instruction(str(rows[0].get("prompt", ""))):
        return rows[1:]
    return rows


def _looks_like_recording_instruction(prompt: str) -> bool:
    lowered = prompt.lower()
    return (
        "dogfooding redline" in lowered
        and "record every substantive user task" in lowered
    )


def _parse_log_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise SystemExit(f"{spec}: expected tool=path")
    tool, path = spec.split("=", 1)
    tool = tool.strip()
    if not tool:
        raise SystemExit(f"{spec}: missing tool name")
    return tool, Path(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise SystemExit("tool name produced an empty output filename")
    return slug


if __name__ == "__main__":
    raise SystemExit(main())
