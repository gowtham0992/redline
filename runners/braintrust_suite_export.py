#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, TextIO


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a redline suite as Braintrust-friendly dataset JSONL."
    )
    parser.add_argument("suite", help="redline suite JSON file")
    parser.add_argument("--out", help="output JSONL file; defaults to stdout")
    parser.add_argument("--input-key", default="input", help="Braintrust input field name")
    parser.add_argument("--expected-key", default="expected", help="Braintrust expected-output field name")
    args = parser.parse_args()

    suite = _read_suite(args.suite)
    rows = list(
        export_braintrust_rows(
            suite,
            input_key=args.input_key,
            expected_key=args.expected_key,
        )
    )
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            _write_rows(rows, handle)
    else:
        _write_rows(rows, sys.stdout)
    return 0


def export_braintrust_rows(
    suite: dict[str, Any],
    *,
    input_key: str = "input",
    expected_key: str = "expected",
) -> Iterable[dict[str, Any]]:
    cases = suite.get("cases")
    if not isinstance(cases, list):
        raise SystemExit("suite missing cases array")
    for case in cases:
        if not isinstance(case, dict):
            continue
        metadata = {
            "redline_case_id": str(case.get("id") or ""),
            "redline_cluster": str(case.get("cluster") or ""),
            "redline_owner": str(case.get("owner") or ""),
            "redline_source": str(case.get("source") or suite.get("source") or ""),
        }
        source_line = case.get("source_line")
        if source_line is not None:
            metadata["redline_source_line"] = source_line
        yield {
            input_key: str(case.get("prompt") or ""),
            expected_key: str(case.get("baseline_response") or ""),
            "metadata": {key: value for key, value in metadata.items() if value not in {"", None}},
        }


def _read_suite(path: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{path} not found") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} expected a redline suite JSON object")
    return payload


def _write_rows(rows: Iterable[dict[str, Any]], handle: TextIO) -> None:
    for row in rows:
        json.dump(row, handle, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
