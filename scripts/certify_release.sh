#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

work_dir="${1:-${TMPDIR:-/tmp}/redline-certify-$(date +%s)-$$}"
python_bin="${PYTHON:-python}"
release_check_dir="$work_dir/release-check"
action_smoke_dir="$work_dir/action-smoke"
dist_dir="$work_dir/dist"
summary_path="$work_dir/certification.txt"
git_commit="$(git rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
git_branch="$(git branch --show-current 2>/dev/null || printf 'unknown')"
if [ -z "$git_branch" ]; then
  git_branch="detached"
fi
if [ -n "$(git status --porcelain 2>/dev/null || true)" ]; then
  git_state="dirty"
else
  git_state="clean"
fi

mkdir -p "$work_dir"

printf 'redline release certification\n' | tee "$summary_path"
printf 'commit: %s\n' "$git_commit" | tee -a "$summary_path"
printf 'branch: %s\n' "$git_branch" | tee -a "$summary_path"
printf 'worktree: %s\n' "$git_state" | tee -a "$summary_path"
printf 'work dir: %s\n\n' "$work_dir" | tee -a "$summary_path"

printf '$ PYTHON=%s bash scripts/release_check.sh %s\n' "$python_bin" "$release_check_dir" | tee -a "$summary_path"
PYTHON="$python_bin" bash scripts/release_check.sh "$release_check_dir"
printf 'release_check: passed\n\n' | tee -a "$summary_path"

printf '$ PYTHON=%s bash scripts/action_smoke.sh %s\n' "$python_bin" "$action_smoke_dir" | tee -a "$summary_path"
PYTHON="$python_bin" bash scripts/action_smoke.sh "$action_smoke_dir"
printf 'action_smoke: passed\n\n' | tee -a "$summary_path"

printf '$ PYTHON=%s bash scripts/build_release.sh %s\n' "$python_bin" "$dist_dir" | tee -a "$summary_path"
PYTHON="$python_bin" bash scripts/build_release.sh "$dist_dir"
printf 'build_release: passed\n\n' | tee -a "$summary_path"

printf 'certification artifacts:\n' | tee -a "$summary_path"
printf -- '- release check: %s\n' "$release_check_dir" | tee -a "$summary_path"
printf -- '- action smoke:  %s\n' "$action_smoke_dir" | tee -a "$summary_path"
printf -- '- dist:          %s\n' "$dist_dir" | tee -a "$summary_path"
printf -- '- summary:       %s\n' "$summary_path" | tee -a "$summary_path"

printf '\nrelease certification passed\n'
