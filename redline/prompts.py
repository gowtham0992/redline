from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

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
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        "root": root_path.as_posix(),
    }


def _has_hidden_relative_part(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
