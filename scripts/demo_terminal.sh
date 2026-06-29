#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

out_dir="${1:-${TMPDIR:-/tmp}/redline-demo-terminal-$(date +%s)}"
history_path="$out_dir/history.jsonl"
history_markdown_path="$out_dir/history.md"
dashboard_path="$out_dir/dashboard.html"
demo_dir="$out_dir/demo"

mkdir -p "$out_dir"

printf 'redline launch demo\n'
printf 'A shorter candidate prompt sounds cleaner, then drops production details.\n\n'

printf '$ redline demo --public --compact\n'
python -m redline demo --public --compact --out "$demo_dir"

printf '\n$ redline history %s --label public-demo --out %s --out-md %s\n' "$demo_dir/reports/public_diff.json" "$history_path" "$history_markdown_path"
python -m redline history "$demo_dir/reports/public_diff.json" \
  --label public-demo \
  --out "$history_path" \
  --out-md "$history_markdown_path"

printf '\n$ redline app --reports-dir %s --history %s --no-open --out %s\n' "$demo_dir/reports" "$history_path" "$dashboard_path"
python -m redline app \
  --reports-dir "$demo_dir/reports" \
  --history "$history_path" \
  --no-open \
  --out "$dashboard_path"

printf '\nArtifacts:\n'
printf '%s\n' "- HTML report: $demo_dir/reports/public_diff.html"
printf '%s\n' "- Dashboard:   $dashboard_path"
