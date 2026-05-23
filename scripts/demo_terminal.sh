#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

out_dir="${1:-${TMPDIR:-/tmp}/redline-demo-terminal-$(date +%s)}"
suite_path="$out_dir/redline-suite.json"
history_path="$out_dir/history.jsonl"
history_markdown_path="$out_dir/history.md"

mkdir -p "$out_dir"

printf '$ redline demo --compact\n'
python -m redline demo --compact --out "$out_dir/demo"

printf '\n$ redline history %s --label demo --out %s --out-md %s\n' "$out_dir/demo/reports/diff.json" "$history_path" "$history_markdown_path"
python -m redline history "$out_dir/demo/reports/diff.json" \
  --label demo \
  --out "$history_path" \
  --out-md "$history_markdown_path"

printf '\n$ redline suite examples/baseline.jsonl --out %s\n' "$suite_path"
python -m redline suite examples/baseline.jsonl --out "$suite_path"

printf '\n$ redline diff %s examples/candidate.jsonl --compact --fail-on none\n' "$suite_path"
python -m redline diff "$suite_path" examples/candidate.jsonl --compact --fail-on none
