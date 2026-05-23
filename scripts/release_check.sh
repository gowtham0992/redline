#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python_bin="${PYTHON:-python}"
work_dir="${1:-${TMPDIR:-/tmp}/redline-release-check-$(date +%s)-$$}"
wheel_dir="$work_dir/wheel"
venv_dir="$work_dir/venv"
smoke_dir="$work_dir/smoke"

mkdir -p "$wheel_dir" "$smoke_dir"

printf 'release check work dir: %s\n\n' "$work_dir"

printf '$ %s -m unittest discover\n' "$python_bin"
"$python_bin" -m unittest discover

printf '\n$ %s -m compileall redline tests examples\n' "$python_bin"
"$python_bin" -m compileall redline tests examples

printf '\n$ git diff --check\n'
git diff --check

printf '\n$ %s -m pip wheel . --no-deps --no-build-isolation -w %s\n' "$python_bin" "$wheel_dir"
"$python_bin" -m pip wheel . --no-deps --no-build-isolation -w "$wheel_dir"
wheel_files=("$wheel_dir"/*.whl)
wheel_path="${wheel_files[0]}"
if [ ! -f "$wheel_path" ]; then
  echo "release check failed: no wheel built in $wheel_dir" >&2
  exit 1
fi

printf '\n$ %s -m venv %s\n' "$python_bin" "$venv_dir"
"$python_bin" -m venv "$venv_dir"

printf '\n$ %s -m pip install --no-deps %s\n' "$venv_dir/bin/python" "$wheel_path"
"$venv_dir/bin/python" -m pip install --no-deps "$wheel_path"

(
  cd "$smoke_dir"
  summary_path="$PWD/github-summary.md"
  printf '\n$ redline --version\n'
  "$venv_dir/bin/redline" --version

  printf '\n$ redline\n'
  "$venv_dir/bin/redline"

  printf '\n$ redline demo --compact\n'
  "$venv_dir/bin/redline" demo --compact

  printf '\n$ GITHUB_STEP_SUMMARY=github-summary.md redline history .redline/demo/reports/diff.json --label demo --out history.jsonl --out-md history.md --github-summary\n'
  GITHUB_STEP_SUMMARY="$summary_path" "$venv_dir/bin/redline" history \
    .redline/demo/reports/diff.json \
    --label demo \
    --out history.jsonl \
    --out-md history.md \
    --github-summary

  test -s history.md
  test -s "$summary_path"

  printf '\n$ redline history --out history.jsonl\n'
  "$venv_dir/bin/redline" history --out history.jsonl

  printf '\n$ redline suite .redline/demo/baseline.jsonl --out all-suite.json --all-cases\n'
  "$venv_dir/bin/redline" suite .redline/demo/baseline.jsonl --out all-suite.json --all-cases

  printf '\n$ redline diff all-suite.json .redline/demo/candidate.jsonl --profile review --compact --fail-on none\n'
  "$venv_dir/bin/redline" diff all-suite.json .redline/demo/candidate.jsonl --profile review --compact --fail-on none

  printf '\n$ redline runners\n'
  "$venv_dir/bin/redline" runners

  printf '\n$ redline init --runner openai --copy-runner\n'
  "$venv_dir/bin/redline" init --runner openai --copy-runner

  printf '\n$ redline doctor\n'
  "$venv_dir/bin/redline" doctor
)

printf '\nrelease check passed\n'
