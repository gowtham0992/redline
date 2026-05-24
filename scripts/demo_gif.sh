#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

out_dir="${1:-.redline/launch}"
gif_path="${2:-$out_dir/redline-demo.gif}"
transcript_path="$out_dir/redline-demo-transcript.txt"
cast_path="$out_dir/redline-demo.cast"
tape_path="$out_dir/redline-demo.tape"
run_dir="$out_dir/run"

mkdir -p "$out_dir"

if command -v vhs >/dev/null 2>&1; then
  cat > "$tape_path" <<TAPE
Output ${gif_path}
Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 720
Set Padding 18
Set TypingSpeed 40ms
Type "python -m redline demo --public --compact --out ${run_dir}/demo"
Enter
Sleep 5s
Type "python -m redline history ${run_dir}/demo/reports/public_diff.json --label public-demo --out ${run_dir}/history.jsonl --out-md ${run_dir}/history.md"
Enter
Sleep 2s
Type "python -m redline dashboard --reports-dir ${run_dir}/demo/reports --history ${run_dir}/history.jsonl --out ${run_dir}/dashboard.html"
Enter
Sleep 2s
TAPE
  vhs "$tape_path"
  printf 'Wrote %s\n' "$gif_path"
  printf 'Tape:  %s\n' "$tape_path"
  exit 0
fi

if command -v asciinema >/dev/null 2>&1 && command -v agg >/dev/null 2>&1; then
  asciinema rec --overwrite --command "bash scripts/demo_terminal.sh '$run_dir'" "$cast_path"
  agg "$cast_path" "$gif_path"
  printf 'Wrote %s\n' "$gif_path"
  printf 'Cast:  %s\n' "$cast_path"
  exit 0
fi

bash scripts/demo_terminal.sh "$run_dir" | tee "$transcript_path"
cat <<MSG

Demo GIF tools were not found, so redline wrote a transcript instead:
  $transcript_path

Install either:
  - VHS: https://github.com/charmbracelet/vhs
  - asciinema plus agg: https://github.com/asciinema/agg

Then rerun:
  bash scripts/demo_gif.sh $out_dir $gif_path
MSG
