#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python_bin="${PYTHON:-python}"
work_dir="${1:-${TMPDIR:-/tmp}/redline-release-check-$(date +%s)-$$}"
wheel_dir="$work_dir/wheel"
venv_dir="$work_dir/venv"
smoke_dir="$work_dir/smoke"
pip_cache_dir="$work_dir/pip-cache"

mkdir -p "$wheel_dir" "$smoke_dir" "$pip_cache_dir"
export PIP_CACHE_DIR="$pip_cache_dir"
export PIP_DISABLE_PIP_VERSION_CHECK=1

printf 'release check work dir: %s\n\n' "$work_dir"

printf '$ %s -m unittest discover\n' "$python_bin"
"$python_bin" -m unittest discover

printf '\n$ %s -m compileall redline tests examples scripts\n' "$python_bin"
"$python_bin" -m compileall redline tests examples scripts

printf '\n$ %s -m ruff check .\n' "$python_bin"
"$python_bin" -m ruff check .

printf '\n$ %s -m mypy redline tests scripts examples\n' "$python_bin"
"$python_bin" -m mypy redline tests scripts examples

printf '\n$ git diff --check\n'
git diff --check

public_suite="$work_dir/public-dogfood-suite.json"
printf '\n$ %s -m redline suite examples/public_dogfood_baseline.jsonl --out %s --all-cases\n' "$python_bin" "$public_suite"
"$python_bin" -m redline suite examples/public_dogfood_baseline.jsonl --out "$public_suite" --all-cases

printf '\n$ %s -m redline diff %s examples/public_dogfood_candidate.jsonl --compact --fail-on none\n' "$python_bin" "$public_suite"
"$python_bin" -m redline diff "$public_suite" examples/public_dogfood_candidate.jsonl --compact --fail-on none

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

printf '\n$ %s -m pip install --no-deps --force-reinstall %s\n' "$venv_dir/bin/python" "$wheel_path"
"$venv_dir/bin/python" -m pip install --no-deps --force-reinstall "$wheel_path"

(
  cd "$smoke_dir"
  summary_path="$PWD/github-summary.md"
  printf '\n$ redline --version\n'
  "$venv_dir/bin/redline" --version

  printf '\n$ redline-mcp --help\n'
  "$venv_dir/bin/redline-mcp" --help

  printf '\n$ redline-mcp tools/list smoke\n'
  mcp_tools="$(printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' | "$venv_dir/bin/redline-mcp")"
  printf '%s\n' "$mcp_tools"
  case "$mcp_tools" in
    *redline_eval*) ;;
    *)
      echo "release check failed: redline-mcp tools/list did not include redline_eval" >&2
      exit 1
      ;;
  esac

  printf '\n$ redline-mcp prompts/list smoke\n'
  mcp_prompts="$(printf '{"jsonrpc":"2.0","id":2,"method":"prompts/list"}\n' | "$venv_dir/bin/redline-mcp")"
  printf '%s\n' "$mcp_prompts"
  case "$mcp_prompts" in
    *check_prompt_change*) ;;
    *)
      echo "release check failed: redline-mcp prompts/list did not include check_prompt_change" >&2
      exit 1
      ;;
  esac

  printf '\n$ redline\n'
  "$venv_dir/bin/redline"

  printf '\n$ redline demo --compact\n'
  "$venv_dir/bin/redline" demo --compact

  printf '\n$ redline demo --public --compact\n'
  "$venv_dir/bin/redline" demo --public --compact

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

  printf '\n$ redline compare .redline/demo/reports/diff.json .redline/demo/reports/public_diff.json --out-html compare.html --fail-on none\n'
  "$venv_dir/bin/redline" compare \
    .redline/demo/reports/diff.json \
    .redline/demo/reports/public_diff.json \
    --out-html compare.html \
    --fail-on none
  test -s compare.html

  printf '\n$ redline dashboard --reports-dir .redline/demo/reports --history history.jsonl --out dashboard.html\n'
  "$venv_dir/bin/redline" dashboard \
    --reports-dir .redline/demo/reports \
    --history history.jsonl \
    --out dashboard.html
  test -s dashboard.html

  printf '\n$ redline suite .redline/demo/baseline.jsonl --out all-suite.json --all-cases\n'
  "$venv_dir/bin/redline" suite .redline/demo/baseline.jsonl --out all-suite.json --all-cases

  printf '\n$ redline suite add all-suite.json --prompt "Pinned refund URL" --response "Refund policy: https://example.com/refunds" --include "https://example.com/refunds" --out pinned-suite.json\n'
  "$venv_dir/bin/redline" suite add all-suite.json \
    --prompt "Pinned refund URL" \
    --response "Refund policy: https://example.com/refunds" \
    --include "https://example.com/refunds" \
    --out pinned-suite.json

  printf '\n$ redline validate pinned-suite.json\n'
  "$venv_dir/bin/redline" validate pinned-suite.json

  printf '\n$ redline diff all-suite.json .redline/demo/candidate.jsonl --profile review --compact --out-html diff.html --fail-on none\n'
  "$venv_dir/bin/redline" diff all-suite.json .redline/demo/candidate.jsonl \
    --profile review \
    --compact \
    --out-html diff.html \
    --fail-on none
  test -s diff.html

  printf '\n$ redline runners\n'
  "$venv_dir/bin/redline" runners

  printf '\n$ redline judges\n'
  "$venv_dir/bin/redline" judges

  printf '\n$ redline sbom --out redline-sbom.json\n'
  "$venv_dir/bin/redline" sbom --out redline-sbom.json
  test -s redline-sbom.json

  printf '\n$ redline init --runner stdio --copy-runner\n'
  "$venv_dir/bin/redline" init --runner stdio --copy-runner

  printf '\n$ redline doctor\n'
  "$venv_dir/bin/redline" doctor
)

printf '\nrelease check passed\n'
