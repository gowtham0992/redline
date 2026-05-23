#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

out_dir="${1:-${TMPDIR:-/tmp}/redline-demo-terminal-$(date +%s)}"
suite_path="$out_dir/redline-suite.json"

mkdir -p "$out_dir"

printf '$ redline demo --compact\n'
python -m redline demo --compact --out "$out_dir/demo"

printf '\n$ redline suite examples/baseline.jsonl --out %s\n' "$suite_path"
python -m redline suite examples/baseline.jsonl --out "$suite_path"

printf '\n$ redline diff %s examples/candidate.jsonl --compact --fail-on none\n' "$suite_path"
python -m redline diff "$suite_path" examples/candidate.jsonl --compact --fail-on none
