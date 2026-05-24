from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps
from inspect import iscoroutinefunction, signature
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from .features import behavior_signature
from .io import (
    LogRecord,
    append_jsonl,
    iter_jsonl,
    read_jsonl_records,
    read_jsonl_records_from_offset,
    write_jsonl,
)

DEFAULT_WATCH_LOG = ".redline/logs/prompts.jsonl"


def watch(
    func: Callable[..., Any] | None = None,
    *,
    log: str | Path = DEFAULT_WATCH_LOG,
    prompt_arg: str | None = None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None = None,
) -> Callable[..., Any]:
    """Record prompt-response pairs from a Python function.

    The wrapped function should receive a prompt-like argument and return the
    response text or structured response value. Nothing leaves disk; records are
    appended to the local JSONL log.
    """

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        if iscoroutinefunction(target):

            @wraps(target)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                prompt = _prompt_from_call(target, args, kwargs, prompt_arg=prompt_arg)
                response = await target(*args, **kwargs)
                _append_function_observation(
                    target,
                    prompt,
                    response,
                    log=log,
                    metadata=metadata,
                    args=args,
                    kwargs=kwargs,
                )
                return response

            return async_wrapper

        @wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            prompt = _prompt_from_call(target, args, kwargs, prompt_arg=prompt_arg)
            response = target(*args, **kwargs)
            _append_function_observation(
                target,
                prompt,
                response,
                log=log,
                metadata=metadata,
                args=args,
                kwargs=kwargs,
            )
            return response

        return wrapper

    if func is None:
        return decorate
    return decorate(func)


def collect_log(
    source: str | Path,
    *,
    output: str | Path,
    input_field: str = "prompt",
    output_field: str = "response",
    append: bool = True,
    dedupe: bool = True,
) -> dict[str, Any]:
    records = read_jsonl_records(source, input_field, output_field)
    rows = [
        _observed_row(
            record,
            source,
            input_field=input_field,
            output_field=output_field,
        )
        for record in records
    ]
    skipped_duplicates = 0
    if dedupe:
        existing_keys = _existing_keys(output) if append else set()
        pending = []
        for row in rows:
            key = _row_key(row)
            if key and key in existing_keys:
                skipped_duplicates += 1
                continue
            if key:
                existing_keys.add(key)
            pending.append(row)
        rows = pending

    if append:
        append_jsonl(output, rows)
        mode = "appended"
    else:
        write_jsonl(output, rows)
        mode = "wrote"
    return {
        "source": str(source),
        "output": str(output),
        "records": len(rows),
        "records_seen": len(records),
        "skipped_duplicates": skipped_duplicates,
        "dedupe": dedupe,
        "mode": mode,
    }


def watch_stats(
    path: str | Path,
    *,
    input_field: str = "prompt",
    output_field: str = "response",
) -> dict[str, Any]:
    records = read_jsonl_records(path, input_field, output_field)
    observed_at = sorted(
        str(record.raw["observed_at"])
        for record in records
        if isinstance(record.raw.get("observed_at"), str)
    )
    signatures = {
        behavior_signature(record.prompt, record.response)
        for record in records
    }
    sources = {
        str(record.raw.get("source"))
        for record in records
        if record.raw.get("source")
    }
    return {
        "log": str(path),
        "records": len(records),
        "sources": len(sources),
        "behavior_patterns": len(signatures),
        "first_observed_at": observed_at[0] if observed_at else None,
        "last_observed_at": observed_at[-1] if observed_at else None,
    }


def format_watch_stats(stats: dict[str, Any]) -> str:
    lines = [
        "redline watch",
        "",
        f"Log:               {stats['log']}",
        f"Records:           {stats['records']}",
        f"Sources:           {stats['sources']}",
        f"Behavior patterns: {stats['behavior_patterns']}",
    ]
    if stats["first_observed_at"] or stats["last_observed_at"]:
        lines.append(f"First observed:    {stats['first_observed_at'] or '<unknown>'}")
        lines.append(f"Last observed:     {stats['last_observed_at'] or '<unknown>'}")
    return "\n".join(lines) + "\n"


def format_follow_records(rows: list[dict[str, Any]]) -> str:
    lines = []
    for row in rows:
        source_line = row.get("source_line")
        line = f"line {source_line}" if source_line is not None else "line ?"
        prompt = _preview(str(row.get("prompt", "")))
        lines.append(f"+ {line}: {prompt}")
    return "\n".join(lines) + ("\n" if lines else "")


def follow_log(
    source: str | Path,
    *,
    output: str | Path,
    input_field: str = "prompt",
    output_field: str = "response",
    poll_interval: float = 1.0,
    max_records: int | None = None,
    idle_timeout: float | None = None,
    dedupe: bool = True,
    replace: bool = False,
    on_records: Callable[[list[dict[str, Any]]], None] | None = None,
) -> dict[str, Any]:
    if poll_interval < 0:
        raise ValueError("poll_interval must be at least 0")
    if max_records is not None and max_records < 1:
        raise ValueError("max_records must be at least 1")
    if idle_timeout is not None and idle_timeout < 0:
        raise ValueError("idle_timeout must be at least 0")

    collected = 0
    seen = 0
    skipped = 0
    iterations = 0
    idle_started: float | None = None
    append = not replace
    offset = 0
    next_line_number = 1
    existing_keys = _existing_keys(output) if append and dedupe else set()
    if replace:
        write_jsonl(output, [])

    while True:
        read_limit = None
        if max_records is not None:
            read_limit = max_records - collected
            if read_limit <= 0:
                break
        records, offset, next_line_number = read_jsonl_records_from_offset(
            source,
            input_field,
            output_field,
            offset=offset,
            start_line_number=next_line_number,
            max_records=read_limit,
        )
        rows = [
            _observed_row(
                record,
                source,
                input_field=input_field,
                output_field=output_field,
            )
            for record in records
        ]
        skipped_duplicates = 0
        if dedupe:
            pending = []
            for row in rows:
                key = _row_key(row)
                if key and key in existing_keys:
                    skipped_duplicates += 1
                    continue
                if key:
                    existing_keys.add(key)
                pending.append(row)
            rows = pending
        if rows:
            append_jsonl(output, rows)
            if on_records is not None:
                on_records(rows)

        iterations += 1
        collected += len(rows)
        seen += len(records)
        skipped += skipped_duplicates

        if max_records is not None and collected >= max_records:
            break

        if rows:
            idle_started = None
        elif idle_timeout is not None:
            if idle_started is None:
                idle_started = monotonic()
            if monotonic() - idle_started >= idle_timeout:
                break

        sleep(poll_interval)

    return {
        "source": str(source),
        "output": str(output),
        "records": collected,
        "records_seen": seen,
        "skipped_duplicates": skipped,
        "dedupe": dedupe,
        "mode": "followed",
        "iterations": iterations,
    }


def _observed_row(
    record: LogRecord,
    source: str | Path,
    *,
    input_field: str,
    output_field: str,
) -> dict[str, Any]:
    row = {
        "prompt": record.prompt,
        "response": record.response,
        "source": str(source),
        "source_line": record.line_number,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    row.setdefault(input_field, record.prompt)
    row.setdefault(output_field, record.response)
    return row


def _append_function_observation(
    target: Callable[..., Any],
    prompt: Any,
    response: Any,
    *,
    log: str | Path,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    append_jsonl(
        log,
        [
            {
                "prompt": _stringify_value(prompt),
                "response": _stringify_value(response),
                "source": _function_source(target),
                "source_line": _function_line(target),
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "metadata": _function_metadata(target, metadata, args, kwargs),
            }
        ],
    )


def _prompt_from_call(
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    prompt_arg: str | None,
) -> Any:
    bound = signature(target).bind_partial(*args, **kwargs)
    if prompt_arg:
        if prompt_arg in bound.arguments:
            return bound.arguments[prompt_arg]
        raise ValueError(f"prompt argument {prompt_arg!r} not found; pass prompt_arg=... for this function")
    for name in ("prompt", "input", "message", "query"):
        if name in bound.arguments:
            return bound.arguments[name]
    if args:
        parameters = list(signature(target).parameters)
        if parameters and parameters[0] in {"self", "cls"} and len(args) > 1:
            return args[1]
        return args[0]
    if len(kwargs) == 1:
        return next(iter(kwargs.values()))
    raise ValueError("could not infer prompt argument; use @watch(prompt_arg='...')")


def _function_metadata(
    target: Callable[..., Any],
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    row = {
        "module": str(getattr(target, "__module__", "")),
        "function": str(getattr(target, "__qualname__", getattr(target, "__name__", "<unknown>"))),
    }
    if metadata is None:
        return row
    extra = metadata(*args, **kwargs) if callable(metadata) else metadata
    if not isinstance(extra, dict):
        raise ValueError("watch metadata must be a dict")
    return {**row, **extra}


def _function_source(target: Callable[..., Any]) -> str:
    module = str(getattr(target, "__module__", ""))
    name = str(getattr(target, "__qualname__", getattr(target, "__name__", "<unknown>")))
    return f"python:{module}.{name}" if module else f"python:{name}"


def _function_line(target: Callable[..., Any]) -> int | None:
    code = getattr(target, "__code__", None)
    line = getattr(code, "co_firstlineno", None)
    return line if isinstance(line, int) else None


def _stringify_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return str(value)


def _existing_keys(path: str | Path) -> set[tuple[str, str]]:
    target = Path(path)
    if not target.exists():
        return set()
    keys = set()
    for _, row in iter_jsonl(target):
        key = _row_key(row)
        if key:
            keys.add(key)
    return keys


def _row_key(row: dict[str, Any]) -> tuple[str, str] | None:
    source = row.get("source")
    source_line = row.get("source_line")
    if source is None or source_line is None:
        return None
    return str(source), str(source_line)


def _preview(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."
