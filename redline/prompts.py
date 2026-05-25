from __future__ import annotations

import hashlib
from pathlib import Path
from shlex import quote
from typing import Sequence

from .io import read_json
from .validate import validate_suite

DEFAULT_PROMPT_EXTENSIONS = (".txt", ".md", ".prompt", ".j2", ".jinja", ".yaml", ".yml")


def build_prompt_manifest(
    root: str | Path,
    *,
    suite_dir: str | Path = "suites",
    extensions: Sequence[str] | None = None,
) -> dict[str, object]:
    root_path = Path(root)
    if not root_path.exists():
        raise ValueError(f"{root_path} not found")

    normalized_extensions = _normalize_extensions(extensions)
    prompt_paths = _prompt_paths(root_path, normalized_extensions)
    if not prompt_paths:
        suffixes = ", ".join(normalized_extensions)
        raise ValueError(f"no prompt files found under {root_path}; scanned extensions: {suffixes}")

    base = root_path if root_path.is_dir() else root_path.parent
    prompts = [
        _prompt_record(path, base=base, root_path=root_path, suite_dir=Path(suite_dir))
        for path in prompt_paths
    ]
    return {
        "schema": "redline-prompt-manifest-v1",
        "version": 1,
        "root": root_path.as_posix(),
        "suite_dir": Path(suite_dir).as_posix(),
        "extensions": list(normalized_extensions),
        "prompt_count": len(prompts),
        "prompts": prompts,
    }


def format_prompt_manifest(manifest: dict[str, object], *, output_path: str | None = None) -> str:
    prompts = manifest.get("prompts", [])
    if not isinstance(prompts, list):
        prompts = []

    lines = [
        "redline prompts",
        "",
        f"Root:      {manifest.get('root')}",
        f"Prompts:   {manifest.get('prompt_count')}",
        f"Suite dir: {manifest.get('suite_dir')}",
    ]
    if output_path:
        lines.append(f"Wrote:     {output_path}")
    lines.append("")

    for prompt in prompts:
        if isinstance(prompt, dict):
            lines.append(f"- {prompt.get('path')} -> {prompt.get('suite')}")

    first_prompt = next((prompt for prompt in prompts if isinstance(prompt, dict)), None)
    lines.extend(["", "Next:"])
    if first_prompt:
        lines.append(f"- Build the first suite: redline suite path/to/baseline.jsonl --out {first_prompt.get('suite')}")
        lines.append(f"- Evaluate that prompt: redline eval {first_prompt.get('suite')} --prompt {first_prompt.get('path')}")
    else:
        lines.append("- Add prompt files, then rerun redline prompts.")
    return "\n".join(lines).rstrip() + "\n"


def check_prompt_manifest(
    stored: dict[str, object],
    current: dict[str, object],
    *,
    manifest_path: str | Path,
) -> dict[str, object]:
    stored_prompts = _prompt_map(stored)
    current_prompts = _prompt_map(current)
    added = sorted(set(current_prompts) - set(stored_prompts))
    removed = sorted(set(stored_prompts) - set(current_prompts))
    changed = sorted(
        prompt_id
        for prompt_id in set(stored_prompts) & set(current_prompts)
        if stored_prompts[prompt_id] != current_prompts[prompt_id]
    )
    field_changes = [
        field
        for field in ("schema", "version", "root", "suite_dir", "extensions", "prompt_count")
        if stored.get(field) != current.get(field)
    ]
    status = "ok" if not added and not removed and not changed and not field_changes else "outdated"
    return {
        "status": status,
        "manifest": Path(manifest_path).as_posix(),
        "prompt_count": current.get("prompt_count", 0),
        "added": added,
        "removed": removed,
        "changed": changed,
        "field_changes": field_changes,
    }


def check_prompt_suites(manifest: dict[str, object]) -> dict[str, object]:
    prompts = manifest.get("prompts", [])
    if not isinstance(prompts, list):
        prompts = []
    missing: list[dict[str, object]] = []
    invalid: list[dict[str, object]] = []
    ready: list[dict[str, object]] = []
    present = 0
    valid = 0
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        suite = str(prompt.get("suite") or "")
        prompt_reference: dict[str, object] = {
            "id": str(prompt.get("id") or ""),
            "path": str(prompt.get("path") or ""),
            "suite": suite,
        }
        if suite and Path(suite).is_file():
            present += 1
            try:
                validation = validate_suite(read_json(suite), suite_path=suite)
            except ValueError as exc:
                invalid.append({**prompt_reference, "error": str(exc)})
                continue
            if not validation.get("valid"):
                invalid.append(
                    {
                        **prompt_reference,
                        "errors": int(validation.get("errors", 0)),
                        "warnings": int(validation.get("warnings", 0)),
                    }
                )
                continue
            valid += 1
            ready.append({**prompt_reference, "command": _eval_command(prompt_reference)})
            continue
        missing.append(prompt_reference)
    prompt_count = len([prompt for prompt in prompts if isinstance(prompt, dict)])
    return {
        "status": _suite_status(missing=missing, invalid=invalid),
        "prompt_count": prompt_count,
        "suite_count": present,
        "valid_suite_count": valid,
        "ready_evals": ready,
        "missing_suites": missing,
        "invalid_suites": invalid,
    }


def format_prompt_manifest_check(report: dict[str, object], *, command: str) -> str:
    status = str(report.get("status", "outdated"))
    lines = [
        "redline prompts check",
        "",
        f"Manifest: {report.get('manifest')}",
        f"Status:   {status.upper()}",
        f"Prompts:  {report.get('prompt_count')}",
    ]
    for label, key in (
        ("Added", "added"),
        ("Changed", "changed"),
        ("Removed", "removed"),
        ("Fields", "field_changes"),
    ):
        values = report.get(key)
        if isinstance(values, list) and values:
            lines.append(f"{label}:   {', '.join(str(value) for value in values)}")

    suite_status = report.get("suite_status")
    missing_suites: list[object] = []
    invalid_suites: list[object] = []
    if isinstance(suite_status, dict):
        suite_count = int(suite_status.get("suite_count") or 0)
        valid_suite_count = int(suite_status.get("valid_suite_count") or 0)
        prompt_count = int(suite_status.get("prompt_count") or 0)
        lines.append(f"Suites:   {suite_count}/{prompt_count} present")
        lines.append(f"Valid:    {valid_suite_count}/{prompt_count} valid")
        raw_missing = suite_status.get("missing_suites")
        if isinstance(raw_missing, list):
            missing_suites = raw_missing
            if missing_suites:
                previews = []
                for item in missing_suites[:5]:
                    if isinstance(item, dict):
                        previews.append(f"{item.get('id')} -> {item.get('suite')}")
                if previews:
                    lines.append(f"Missing suites: {', '.join(previews)}")
        raw_invalid = suite_status.get("invalid_suites")
        if isinstance(raw_invalid, list):
            invalid_suites = raw_invalid
            if invalid_suites:
                previews = []
                for item in invalid_suites[:5]:
                    if isinstance(item, dict):
                        detail = item.get("error") or f"errors={item.get('errors')}"
                        previews.append(f"{item.get('id')} -> {item.get('suite')} ({detail})")
                if previews:
                    lines.append(f"Invalid suites: {', '.join(previews)}")
        raw_ready = suite_status.get("ready_evals")
        if isinstance(raw_ready, list) and raw_ready:
            lines.append("Ready evals:")
            for item in raw_ready[:5]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('command')}")
            remaining = len(raw_ready) - 5
            if remaining > 0:
                lines.append(f"- ... {remaining} more prompt suite(s)")

    if status != "ok":
        lines.extend(["", "Next:"])
        if _manifest_has_changes(report):
            lines.append(f"- Regenerate manifest: {command}")
        first_missing = next((item for item in missing_suites if isinstance(item, dict)), None)
        if first_missing:
            lines.append(
                "- Build missing suite: "
                f"redline suite path/to/baseline.jsonl --out {first_missing.get('suite')}"
            )
        first_invalid = next((item for item in invalid_suites if isinstance(item, dict)), None)
        if first_invalid:
            lines.append(f"- Fix invalid suite: redline validate {first_invalid.get('suite')} --strict")
    return "\n".join(lines).rstrip() + "\n"


def _suite_status(*, missing: Sequence[object], invalid: Sequence[object]) -> str:
    if missing:
        return "missing_suites"
    if invalid:
        return "invalid_suites"
    return "ok"


def _eval_command(prompt: dict[str, object]) -> str:
    suite = quote(str(prompt.get("suite") or ""))
    path = quote(str(prompt.get("path") or ""))
    return f"redline eval {suite} --prompt {path}"


def _normalize_extensions(extensions: Sequence[str] | None) -> tuple[str, ...]:
    values = extensions or DEFAULT_PROMPT_EXTENSIONS
    normalized = []
    for extension in values:
        value = extension.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        normalized.append(value)
    if not normalized:
        raise ValueError("at least one prompt extension is required")
    return tuple(dict.fromkeys(normalized))


def _prompt_paths(root_path: Path, extensions: Sequence[str]) -> list[Path]:
    if root_path.is_file():
        if root_path.suffix.lower() not in extensions:
            return []
        return [root_path]
    return sorted(
        (
            path
            for path in root_path.rglob("*")
            if path.is_file()
            and path.suffix.lower() in extensions
            and not _has_hidden_relative_part(path.relative_to(root_path))
        ),
        key=lambda path: path.relative_to(root_path).as_posix(),
    )


def _prompt_record(path: Path, *, base: Path, root_path: Path, suite_dir: Path) -> dict[str, object]:
    relative = path.relative_to(base).as_posix()
    prompt_id = str(Path(relative).with_suffix("")).replace("\\", "/")
    suite = suite_dir / f"{prompt_id}.redline-suite.json"
    stat = path.stat()
    return {
        "id": prompt_id,
        "path": path.as_posix(),
        "relative_path": relative,
        "suite": suite.as_posix(),
        "sha256": _sha256(path),
        "bytes": stat.st_size,
        "root": root_path.as_posix(),
    }


def _has_hidden_relative_part(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _prompt_map(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    prompts = manifest.get("prompts")
    if not isinstance(prompts, list):
        return {}
    result = {}
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_id = prompt.get("id")
        if isinstance(prompt_id, str):
            result[prompt_id] = dict(prompt)
    return result


def _manifest_has_changes(report: dict[str, object]) -> bool:
    return any(
        isinstance(report.get(key), list) and bool(report.get(key))
        for key in ("added", "changed", "removed", "field_changes")
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
