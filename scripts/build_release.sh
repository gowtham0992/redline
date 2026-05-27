#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python_bin="${PYTHON:-python}"
dist_dir="${1:-${TMPDIR:-/tmp}/redline-dist-$(date +%s)-$$}"

if [ -e "$dist_dir" ]; then
  if [ -n "$(find "$dist_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "release build failed: output directory is not empty: $dist_dir" >&2
    echo "Pass a fresh directory so stale wheels cannot be uploaded." >&2
    exit 1
  fi
else
  mkdir -p "$dist_dir"
fi

printf 'release dist dir: %s\n\n' "$dist_dir"

printf '$ %s -m build --outdir %s\n' "$python_bin" "$dist_dir"
"$python_bin" -m build --outdir "$dist_dir"

wheel_files=("$dist_dir"/redline_ai-*.whl)
sdist_files=("$dist_dir"/redline_ai-*.tar.gz)
if [ ! -f "${wheel_files[0]}" ]; then
  echo "release build failed: no redline_ai wheel built in $dist_dir" >&2
  exit 1
fi
if [ ! -f "${sdist_files[0]}" ]; then
  echo "release build failed: no redline_ai source distribution built in $dist_dir" >&2
  exit 1
fi

printf '\n$ %s -m twine check %s/*\n' "$python_bin" "$dist_dir"
"$python_bin" -m twine check "$dist_dir"/*

sbom_path="$dist_dir/redline-sbom.json"
printf '\n$ %s -m redline sbom --out %s\n' "$python_bin" "$sbom_path"
"$python_bin" -m redline sbom --out "$sbom_path"
test -s "$sbom_path"

printf '\nrelease artifacts:\n'
for artifact in "$dist_dir"/*; do
  printf -- '- %s\n' "$artifact"
done

printf '\nupload with:\n'
printf 'python -m twine upload %s/redline_ai-*.whl %s/redline_ai-*.tar.gz\n' "$dist_dir" "$dist_dir"
