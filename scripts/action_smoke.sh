#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-python}"
work_dir="${1:-${TMPDIR:-/tmp}/redline-action-smoke-$(date +%s)-$$}"
venv_dir="$work_dir/venv"
project_dir="$work_dir/external-project"
pip_cache_dir="$work_dir/pip-cache"
wheel_dir="$work_dir/wheel"

mkdir -p "$project_dir" "$pip_cache_dir" "$wheel_dir"
export PIP_CACHE_DIR="$pip_cache_dir"
export PIP_DISABLE_PIP_VERSION_CHECK=1

printf 'action smoke work dir: %s\n\n' "$work_dir"

printf '$ %s -m venv %s\n' "$python_bin" "$venv_dir"
"$python_bin" -m venv "$venv_dir"

printf '\n$ %s -m pip wheel %s --no-deps --no-build-isolation -w %s\n' "$python_bin" "$repo_root" "$wheel_dir"
"$python_bin" -m pip wheel "$repo_root" --no-deps --no-build-isolation -w "$wheel_dir"
wheel_files=("$wheel_dir"/redline_ai-*.whl)
wheel_path="${wheel_files[0]}"
if [ ! -f "$wheel_path" ]; then
  echo "action smoke failed: no wheel built in $wheel_dir" >&2
  exit 1
fi

printf '\n$ %s -m pip install --no-deps --force-reinstall %s\n' "$venv_dir/bin/python" "$wheel_path"
"$venv_dir/bin/python" -m pip install --no-deps --force-reinstall "$wheel_path"

cd "$project_dir"

cat > baseline.jsonl <<'JSONL'
{"prompt":"Return JSON with keys owner and priority for ticket INV-1042.","response":"{\"owner\":\"Billing Ops\",\"priority\":\"high\"}"}
{"prompt":"Summarize the incident as a Markdown table with columns Impact and Owner.","response":"| Impact | Owner |\n| --- | --- |\n| Search latency over 900ms | Search Platform |"}
JSONL

cat > replay_candidate.py <<'PY'
import sys

prompt = sys.stdin.read()
if "JSON" in prompt:
    print("Billing issue.")
elif "Markdown table" in prompt:
    print("Search latency is elevated.")
else:
    print(prompt)
PY

cat > redline.json <<'JSON'
{
  "$schema": "https://raw.githubusercontent.com/gowtham0992/redline/main/redline.schema.json",
  "suite": "redline-suite.json",
  "input_field": "prompt",
  "output_field": "response",
  "fail_on": ["regression", "missing"],
  "reports": {
    "json": ".redline/reports/{command}.json",
    "markdown": ".redline/reports/{command}.md",
    "comment": ".redline/reports/{command}-comment.md",
    "html": ".redline/reports/{command}.html",
    "junit": ".redline/reports/{command}.xml"
  },
  "runs": {
    "candidate": ".redline/runs/candidate.jsonl",
    "metadata": ".redline/runs/replay.json"
  },
  "replay": "python replay_candidate.py"
}
JSON

printf '\n$ redline suite baseline.jsonl --out redline-suite.json --all-cases\n'
"$venv_dir/bin/redline" suite baseline.jsonl --out redline-suite.json --all-cases

printf '\n$ redline doctor --strict\n'
"$venv_dir/bin/redline" doctor --strict

printf '\n$ redline validate redline-suite.json --strict\n'
"$venv_dir/bin/redline" validate redline-suite.json --strict

summary_path="$project_dir/github-summary.md"
printf '\n$ redline budget redline-suite.json --measure-local --github-summary --out-json .redline/reports/benchmark.json --out-md .redline/reports/benchmark.md\n'
GITHUB_STEP_SUMMARY="$summary_path" "$venv_dir/bin/redline" budget redline-suite.json \
  --measure-local \
  --github-summary \
  --out-json .redline/reports/benchmark.json \
  --out-md .redline/reports/benchmark.md

printf '\n$ redline eval --compact --github-summary\n'
set +e
# The smoke intentionally creates regressions; do not emit GitHub error
# annotations from a passing CI job.
GITHUB_STEP_SUMMARY="$summary_path" "$venv_dir/bin/redline" eval \
  --compact \
  --github-summary \
  --out-json .redline/reports/eval.json \
  --out-md .redline/reports/eval.md \
  --out-comment .redline/reports/eval-comment.md \
  --out-html .redline/reports/eval.html \
  --out-junit .redline/reports/eval.xml \
  --out-slack .redline/reports/eval.slack.json
eval_status=$?
set -e
if [ "$eval_status" -ne 1 ]; then
  echo "action smoke failed: expected redline eval to return 1 for regressions, got $eval_status" >&2
  exit 1
fi

test -s .redline/reports/eval.json
test -s .redline/reports/benchmark.json
test -s .redline/reports/benchmark.md
test -s .redline/reports/eval.md
test -s .redline/reports/eval-comment.md
test -s .redline/reports/eval.html
test -s .redline/reports/eval.xml
test -s .redline/reports/eval.slack.json
test -s "$summary_path"

printf '\n$ redline history .redline/reports/eval.json --label action-smoke --out .redline/history.jsonl --out-md .redline/history.md --github-summary --fail-on none\n'
GITHUB_STEP_SUMMARY="$summary_path" "$venv_dir/bin/redline" history \
  .redline/reports/eval.json \
  --label action-smoke \
  --out .redline/history.jsonl \
  --out-md .redline/history.md \
  --github-summary \
  --fail-on none

printf '\n$ redline audit --verify --out-checkpoint .redline/audit-checkpoint.json\n'
"$venv_dir/bin/redline" audit --verify --out-checkpoint .redline/audit-checkpoint.json

printf '\n$ redline dashboard --out .redline/dashboard.html\n'
"$venv_dir/bin/redline" dashboard --out .redline/dashboard.html

test -s .redline/history.jsonl
test -s .redline/history.md
test -s .redline/dashboard.html
grep -q "Benchmark Evidence" .redline/dashboard.html
test -s .redline/audit-checkpoint.json

printf '\naction smoke passed\n'
