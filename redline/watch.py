from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps
from hashlib import sha256
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
READY_RECORDS = 5
READY_PATTERNS = 3


def watch(
    func: Callable[..., Any] | None = None,
    *,
    log: str | Path = DEFAULT_WATCH_LOG,
    prompt_arg: str | None = None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None = None,
    dedupe: bool = True,
) -> Callable[..., Any]:
    """Record prompt-response pairs from a Python function.

    The wrapped function should receive a prompt-like argument and return the
    response text or structured response value. Nothing leaves disk; records are
    appended to the local JSONL log. Exact prompt-response duplicates are
    skipped by default.
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
                    dedupe=dedupe,
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
                dedupe=dedupe,
            )
            return response

        return wrapper

    if func is None:
        return decorate
    return decorate(func)


def record(
    prompt: Any,
    response: Any,
    *,
    log: str | Path = DEFAULT_WATCH_LOG,
    source: str = "python:manual",
    source_line: int | None = None,
    metadata: dict[str, Any] | None = None,
    dedupe: bool = True,
) -> dict[str, Any]:
    """Append one prompt-response observation to a local JSONL log."""

    prompt_text = _stringify_value(prompt)
    response_text = _stringify_value(response)
    content_hash = _content_hash(prompt_text, response_text)
    row = {
        "prompt": prompt_text,
        "response": response_text,
        "source": source,
        "source_line": source_line,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "content_hash": content_hash,
    }
    if dedupe and content_hash in _existing_content_hashes(log):
        return {**row, "recorded": False}
    append_jsonl(log, [row])
    return {**row, "recorded": True}


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
    content_hashes = {_record_content_hash(record) for record in records}
    signatures = {
        behavior_signature(record.prompt, record.response)
        for record in records
    }
    sources = {
        str(record.raw.get("source"))
        for record in records
        if record.raw.get("source")
    }
    records_count = len(records)
    unique_pairs = len(content_hashes)
    patterns_count = len(signatures)
    return {
        "log": str(path),
        "records": records_count,
        "unique_prompt_response_pairs": unique_pairs,
        "duplicate_prompt_response_pairs": records_count - unique_pairs,
        "sources": len(sources),
        "behavior_patterns": patterns_count,
        "first_observed_at": observed_at[0] if observed_at else None,
        "last_observed_at": observed_at[-1] if observed_at else None,
        "readiness": _readiness(unique_pairs, patterns_count),
    }


def format_watch_stats(stats: dict[str, Any]) -> str:
    lines = [
        "redline watch",
        "",
        f"Log:               {stats['log']}",
        f"Records:           {stats['records']}",
        f"Unique pairs:      {stats['unique_prompt_response_pairs']}",
        f"Duplicate pairs:   {stats['duplicate_prompt_response_pairs']}",
        f"Sources:           {stats['sources']}",
        f"Behavior patterns: {stats['behavior_patterns']}",
    ]
    if stats["first_observed_at"] or stats["last_observed_at"]:
        lines.append(f"First observed:    {stats['first_observed_at'] or '<unknown>'}")
        lines.append(f"Last observed:     {stats['last_observed_at'] or '<unknown>'}")
    readiness = stats.get("readiness")
    if isinstance(readiness, dict):
        lines.append(f"Readiness:         {readiness['message']}")
        lines.append(f"Next:              {readiness['next_step']}")
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
        "content_hash": _content_hash(record.prompt, record.response),
    }
    row.setdefault(input_field, record.prompt)
    row.setdefault(output_field, record.response)
    return row


def _readiness(records: int, patterns: int) -> dict[str, Any]:
    ready = records >= READY_RECORDS and patterns >= READY_PATTERNS
    if ready:
        return {
            "ready": True,
            "message": "ready to generate suite",
            "next_step": "redline suite",
            "minimum_records": READY_RECORDS,
            "minimum_behavior_patterns": READY_PATTERNS,
        }
    needs = []
    if records < READY_RECORDS:
        needs.append(f"{READY_RECORDS - records} more record(s)")
    if patterns < READY_PATTERNS:
        needs.append(f"{READY_PATTERNS - patterns} more behavior pattern(s)")
    return {
        "ready": False,
        "message": "collect more evidence: " + ", ".join(needs),
        "next_step": "redline watch --follow",
        "minimum_records": READY_RECORDS,
        "minimum_behavior_patterns": READY_PATTERNS,
    }


def _append_function_observation(
    target: Callable[..., Any],
    prompt: Any,
    response: Any,
    *,
    log: str | Path,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    dedupe: bool,
) -> None:
    record(
        prompt,
        response,
        log=log,
        source=_function_source(target),
        source_line=_function_line(target),
        metadata=_function_metadata(target, metadata, args, kwargs),
        dedupe=dedupe,
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


def _content_hash(prompt: str, response: str) -> str:
    payload = json.dumps(
        {"prompt": prompt, "response": response},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _record_content_hash(record: LogRecord) -> str:
    content_hash = record.raw.get("content_hash")
    if isinstance(content_hash, str) and content_hash:
        return content_hash
    return _content_hash(record.prompt, record.response)


def _existing_content_hashes(path: str | Path) -> set[str]:
    target = Path(path)
    if not target.exists():
        return set()
    hashes: set[str] = set()
    for _, row in iter_jsonl(target):
        content_hash = row.get("content_hash")
        if isinstance(content_hash, str) and content_hash:
            hashes.add(content_hash)
            continue
        prompt = row.get("prompt")
        response = row.get("response")
        if prompt is not None and response is not None:
            hashes.add(_content_hash(_stringify_value(prompt), _stringify_value(response)))
    return hashes


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
