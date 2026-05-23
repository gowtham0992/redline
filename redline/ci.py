from __future__ import annotations


def default_github_workflow() -> str:
    return """name: redline

on:
  pull_request:
    paths:
      - "prompts/**"
      - "**/*.jsonl"
      - "redline.json"
      - "redline-suite.json"
      - "redline.schema.json"

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install redline
        run: pip install -e .

      - name: Check redline setup
        run: python -m redline doctor --strict

      - name: Run redline eval
        run: |
          python -m redline eval \\
            --compact \\
            --github-summary \\
            --github-annotations \\
            --out-json .redline/reports/eval.json \\
            --out-md .redline/reports/eval.md \\
            --out-junit .redline/reports/eval.xml

      - name: Upload redline reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: redline-reports
          path: .redline/reports/
"""
