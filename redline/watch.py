from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps
from inspect import iscoroutinefunction, signature
import json
from pathlib import Path
from shlex import quote
from time import monotonic, sleep
from typing import Any

from .features import behavior_signature
from .hashes import prompt_response_hash
from .io import (
    LogRecord,
    append_jsonl,
    iter_jsonl,
    read_jsonl_records,
    read_jsonl_records_from_offset,
    write_jsonl,
)
from .redact import DEFAULT_PLACEHOLDER, redact_object

DEFAULT_WATCH_LOG = ".redline/logs/prompts.jsonl"
READY_RECORDS = 5
READY_PATTERNS = 3


def watch(
    func: Callable[..., Any] | None = None,
    *,
    log: str | Path = DEFAULT_WATCH_LOG,
    prompt_arg: str | None = None,
    response_extractor: Callable[[Any], Any] | None = None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None = None,
    dedupe: bool = True,
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
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
                started = monotonic()
                response = await target(*args, **kwargs)
                latency_ms = _elapsed_ms(started)
                _append_function_observation(
                    target,
                    prompt,
                    response,
                    log=log,
                    response_extractor=response_extractor,
                    metadata=metadata,
                    args=args,
                    kwargs=kwargs,
                    latency_ms=latency_ms,
                    dedupe=dedupe,
                    redact=redact,
                    placeholder=placeholder,
                )
                return response

            return async_wrapper

        @wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            prompt = _prompt_from_call(target, args, kwargs, prompt_arg=prompt_arg)
            started = monotonic()
            response = target(*args, **kwargs)
            latency_ms = _elapsed_ms(started)
            _append_function_observation(
                target,
                prompt,
                response,
                log=log,
                response_extractor=response_extractor,
                metadata=metadata,
                args=args,
                kwargs=kwargs,
                latency_ms=latency_ms,
                dedupe=dedupe,
                redact=redact,
                placeholder=placeholder,
            )
            return response

        return wrapper

    if func is None:
        return decorate
    return decorate(func)


def patch_openai(
    client: Any | None = None,
    *,
    log: str | Path = DEFAULT_WATCH_LOG,
    response_extractor: Callable[[Any], Any] | None = None,
    dedupe: bool = True,
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    """Patch an OpenAI-compatible module or client to record local observations.

    Pass an OpenAI module or client instance, or omit ``client`` to import the
    installed ``openai`` module. The patch is dependency-free from redline's
    point of view and records only when it can infer a prompt from common
    ``messages``, ``input``, or ``prompt`` arguments.
    """

    target = client if client is not None else _import_openai_module()
    patched = []
    for path in ("chat.completions.create", "responses.create", "ChatCompletion.create"):
        if _patch_openai_path(
            target,
            path,
            log=log,
            response_extractor=response_extractor,
            dedupe=dedupe,
            redact=redact,
            placeholder=placeholder,
        ):
            patched.append(path)
    return {"provider": "openai", "log": str(log), "patched": patched}


def record(
    prompt: Any,
    response: Any,
    *,
    log: str | Path = DEFAULT_WATCH_LOG,
    source: str = "python:manual",
    source_line: int | None = None,
    metadata: dict[str, Any] | None = None,
    dedupe: bool = True,
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    """Append one prompt-response observation to a local JSONL log."""

    prompt_text = _stringify_value(prompt)
    response_text = _stringify_value(_response_value(response))
    merged_metadata = {**_provider_metadata(response), **(metadata or {})}
    redaction_counts: dict[str, int] = {}
    if redact:
        prompt_text = _redact_value(prompt_text, counts=redaction_counts, placeholder=placeholder)
        response_text = _redact_value(response_text, counts=redaction_counts, placeholder=placeholder)
        merged_metadata = redact_object(
            merged_metadata,
            counts=redaction_counts,
            placeholder=placeholder,
        )
    content_hash = prompt_response_hash(prompt_text, response_text)
    row = {
        "prompt": prompt_text,
        "response": response_text,
        "source": source,
        "source_line": source_line,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "metadata": merged_metadata,
        "content_hash": content_hash,
    }
    if redaction_counts:
        row["redactions"] = dict(sorted(redaction_counts.items()))
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
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    records = read_jsonl_records(source, input_field, output_field)
    rows = [
        _observed_row(
            record,
            source,
            input_field=input_field,
            output_field=output_field,
            redact=redact,
            placeholder=placeholder,
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
    redaction_counts = _rows_redaction_counts(rows)
    return {
        "source": str(source),
        "output": str(output),
        "records": len(rows),
        "records_seen": len(records),
        "skipped_duplicates": skipped_duplicates,
        "dedupe": dedupe,
        "mode": mode,
        "redactions": sum(redaction_counts.values()),
        "redaction_patterns": dict(sorted(redaction_counts.items())),
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
        "readiness": _readiness(unique_pairs, patterns_count, log=path),
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
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
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
    redaction_counts: dict[str, int] = {}
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
                redact=redact,
                placeholder=placeholder,
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
            _merge_counts(redaction_counts, _rows_redaction_counts(rows))
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
        "redactions": sum(redaction_counts.values()),
        "redaction_patterns": dict(sorted(redaction_counts.items())),
    }


def _observed_row(
    record: LogRecord,
    source: str | Path,
    *,
    input_field: str,
    output_field: str,
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    prompt = record.prompt
    response = record.response
    counts: dict[str, int] = {}
    if redact:
        prompt = _redact_value(prompt, counts=counts, placeholder=placeholder)
        response = _redact_value(response, counts=counts, placeholder=placeholder)
    row = {
        "prompt": prompt,
        "response": response,
        "source": str(source),
        "source_line": record.line_number,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": prompt_response_hash(prompt, response),
    }
    if redact and counts:
        row["redactions"] = dict(sorted(counts.items()))
    row.setdefault(input_field, prompt)
    row.setdefault(output_field, response)
    return row


def _readiness(records: int, patterns: int, *, log: str | Path) -> dict[str, Any]:
    log_arg = quote(str(log))
    ready = records >= READY_RECORDS and patterns >= READY_PATTERNS
    if ready:
        return {
            "ready": True,
            "message": "ready to generate suite",
            "next_step": f"redline suite {log_arg} --out redline-suite.json",
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
        "next_step": f"redline watch --log {log_arg} --follow",
        "minimum_records": READY_RECORDS,
        "minimum_behavior_patterns": READY_PATTERNS,
    }


def _append_function_observation(
    target: Callable[..., Any],
    prompt: Any,
    response: Any,
    *,
    log: str | Path,
    response_extractor: Callable[[Any], Any] | None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    latency_ms: int,
    dedupe: bool,
    redact: bool,
    placeholder: str,
) -> None:
    response_value = response_extractor(response) if response_extractor else response
    observation_metadata = {
        **_provider_metadata(response),
        **_function_metadata(target, metadata, args, kwargs, latency_ms=latency_ms),
    }
    record(
        prompt,
        response_value,
        log=log,
        source=_function_source(target),
        source_line=_function_line(target),
        metadata=observation_metadata,
        dedupe=dedupe,
        redact=redact,
        placeholder=placeholder,
    )


def _import_openai_module() -> Any:
    try:
        import openai  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on user environment.
        raise ValueError("OpenAI package not installed; pass an OpenAI-compatible client to patch_openai") from exc
    return openai


def _patch_openai_path(
    root: Any,
    path: str,
    *,
    log: str | Path,
    response_extractor: Callable[[Any], Any] | None,
    dedupe: bool,
    redact: bool,
    placeholder: str,
) -> bool:
    parent = _resolve_parent(root, path)
    if parent is None:
        return False
    name = path.rsplit(".", 1)[-1]
    original = getattr(parent, name, None)
    if not callable(original) or getattr(original, "__redline_patched__", False):
        return False

    if iscoroutinefunction(original):

        @wraps(original)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            prompt = _openai_prompt_from_call(args, kwargs)
            started = monotonic()
            response = await original(*args, **kwargs)
            _record_openai_observation(
                path,
                prompt,
                response,
                kwargs,
                log=log,
                response_extractor=response_extractor,
                latency_ms=_elapsed_ms(started),
                dedupe=dedupe,
                redact=redact,
                placeholder=placeholder,
            )
            return response

        wrapper: Callable[..., Any] = async_wrapper
    else:

        @wraps(original)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            prompt = _openai_prompt_from_call(args, kwargs)
            started = monotonic()
            response = original(*args, **kwargs)
            _record_openai_observation(
                path,
                prompt,
                response,
                kwargs,
                log=log,
                response_extractor=response_extractor,
                latency_ms=_elapsed_ms(started),
                dedupe=dedupe,
                redact=redact,
                placeholder=placeholder,
            )
            return response

        wrapper = sync_wrapper

    setattr(wrapper, "__redline_patched__", True)
    setattr(wrapper, "__redline_original__", original)
    setattr(parent, name, wrapper)
    return True


def _resolve_parent(root: Any, path: str) -> Any | None:
    current = root
    parts = path.split(".")
    for part in parts[:-1]:
        current = _field(current, part)
        if current is None:
            return None
    return current


def _record_openai_observation(
    operation: str,
    prompt: Any,
    response: Any,
    request_kwargs: dict[str, Any],
    *,
    log: str | Path,
    response_extractor: Callable[[Any], Any] | None,
    latency_ms: int,
    dedupe: bool,
    redact: bool,
    placeholder: str,
) -> None:
    if prompt is None:
        return
    response_value = response_extractor(response) if response_extractor else response
    metadata = {
        "provider": "openai",
        "operation": operation,
        "latency_ms": latency_ms,
    }
    model = request_kwargs.get("model")
    if isinstance(model, str) and model:
        metadata["request_model"] = model
    record(
        prompt,
        response_value,
        log=log,
        source=f"python:openai.{operation}",
        metadata=metadata,
        dedupe=dedupe,
        redact=redact,
        placeholder=placeholder,
    )


def _openai_prompt_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    for key in ("messages", "input", "prompt"):
        if key in kwargs:
            return _openai_prompt_value(kwargs[key])
    for value in args:
        prompt = _openai_prompt_value(value)
        if prompt is not None:
            return prompt
    return None


def _openai_prompt_value(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        messages = _openai_messages_text(value)
        return messages if messages is not None else value
    return value


def _openai_messages_text(messages: list[Any]) -> str | None:
    rows = []
    for message in messages:
        role = _field(message, "role")
        content = _field(message, "content")
        text = _openai_content_text(content)
        if not text:
            continue
        if isinstance(role, str) and role:
            rows.append(f"{role}: {text}")
        else:
            rows.append(text)
    return "\n".join(rows) if rows else None


def _openai_content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            text = _field(item, "text")
            if isinstance(text, str) and text:
                parts.append(text)
        return "\n".join(parts) if parts else None
    return None


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
    *,
    latency_ms: int,
) -> dict[str, Any]:
    row = {
        "module": str(getattr(target, "__module__", "")),
        "function": str(getattr(target, "__qualname__", getattr(target, "__name__", "<unknown>"))),
        "latency_ms": latency_ms,
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


def _redact_value(value: str, *, counts: dict[str, int], placeholder: str) -> str:
    redacted = redact_object(value, counts=counts, placeholder=placeholder)
    return redacted if isinstance(redacted, str) else _stringify_value(redacted)


def _merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def _rows_redaction_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        redactions = row.get("redactions")
        if isinstance(redactions, dict):
            for key, value in redactions.items():
                if isinstance(key, str) and isinstance(value, int):
                    counts[key] = counts.get(key, 0) + value
    return counts


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _response_value(value: Any) -> Any:
    provider_text = _provider_response_text(value)
    return provider_text if provider_text is not None else value


def _provider_response_text(value: Any) -> str | None:
    output_text = _field(value, "output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    choices = _field(value, "choices")
    if isinstance(choices, list) and choices:
        text = _choice_text(choices[0])
        if text:
            return text

    output = _field(value, "output")
    text = _blocks_text(output)
    if text:
        return text

    content = _field(value, "content")
    if isinstance(content, str) and not isinstance(value, dict):
        return content
    text = _blocks_text(content)
    if text:
        return text

    response = _field(value, "response")
    if isinstance(response, str) and not isinstance(value, dict):
        return response
    return None


def _choice_text(choice: Any) -> str | None:
    message = _field(choice, "message")
    content = _field(message, "content")
    if isinstance(content, str):
        return content
    text = _blocks_text(content)
    if text:
        return text
    return None


def _blocks_text(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    parts = []
    for item in value:
        text = _field(item, "text")
        if isinstance(text, str) and text:
            parts.append(text)
            continue
        content = _field(item, "content")
        nested = _blocks_text(content)
        if nested:
            parts.append(nested)
    return "\n".join(parts) if parts else None


def _provider_metadata(value: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in ("id", "model"):
        item = _field(value, field)
        if isinstance(item, str) and item:
            metadata[field] = item

    choices = _field(value, "choices")
    if isinstance(choices, list) and choices:
        finish_reason = _field(choices[0], "finish_reason")
        if isinstance(finish_reason, str) and finish_reason:
            metadata["finish_reason"] = finish_reason

    usage = _field(value, "usage")
    if usage is not None:
        for source, target in (
            ("prompt_tokens", "prompt_tokens"),
            ("completion_tokens", "completion_tokens"),
            ("input_tokens", "prompt_tokens"),
            ("output_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            count = _field(usage, source)
            if isinstance(count, int):
                metadata[target] = count
    return metadata


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _record_content_hash(record: LogRecord) -> str:
    content_hash = record.raw.get("content_hash")
    if isinstance(content_hash, str) and content_hash:
        return content_hash
    return prompt_response_hash(record.prompt, record.response)


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
            hashes.add(prompt_response_hash(_stringify_value(prompt), _stringify_value(response)))
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
