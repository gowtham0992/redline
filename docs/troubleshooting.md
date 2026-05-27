# Troubleshooting

Use this when the first five minutes do not work. redline should fail with a
next command whenever possible; if it does not, file an issue with the command,
redline version, Python version, and sanitized output.

## `redline: command not found`

Confirm the package installed into the Python environment on your PATH:

```bash
python -m pip install redline-ai
python -m pip show redline-ai
python -m redline --version
```

If `python -m redline --version` works but `redline --version` does not, your
Python scripts directory is not on PATH. Use `python -m redline ...` or fix the
environment PATH.

## `redline demo` fails

Run the explicit module form and capture the version:

```bash
python -m redline --version
python -m redline demo --public --compact
```

If the failure mentions a permission error, rerun from a writable directory.
The demo writes only local files under `.redline/demo`.

## Dashboard does not open

`--open` uses Python's local browser integration. It can be a no-op on headless
CI, SSH sessions, containers, and remote agents. Write the file explicitly:

```bash
redline dashboard --reports-dir .redline/demo/reports --out .redline/dashboard.html
```

Then open `.redline/dashboard.html` from your local machine or upload it as a CI
artifact.

## Suite file not found

Generate and commit a suite before running `redline eval` or the GitHub Action:

```bash
redline suite logs/baseline.jsonl --out redline-suite.json
redline validate redline-suite.json --strict
```

If you use many prompt files, point `suite` at a prompt manifest:

```bash
redline prompts prompts/ --suite-dir suites --out redline-prompts.json --check --check-suites
```

## Suite validation fails

Run validation directly so the first structural error is visible:

```bash
redline validate redline-suite.json --strict
```

Common causes are hand-edited JSON, duplicate case IDs, missing baseline
responses, stale source hashes after regenerating logs, or prompt manifests that
point at missing suite files.

## GitHub Action cannot find the suite

The Action runs in CI against committed files. Make sure the suite or prompt
manifest exists in the repository and the action input points to it:

```yaml
uses: gowtham0992/redline@v0.2.1
with:
  suite: redline-suite.json
```

For prompt manifests, commit both `redline-prompts.json` and every mapped suite
under `suites/`.

## GitHub Action `extra-args` breaks

`extra-args` is a simple space-separated escape hatch for flags such as
`--profile review`. It cannot represent one argument that itself contains
spaces. Prefer `redline.json` for values with spaces, or add a dedicated Action
input before relying on complex `extra-args` values.

## Neutral does not mean safe

A neutral result means redline did not find a configured high-signal structural
change. It does not prove factual correctness, tone, hallucination safety,
policy compliance, or reasoning quality. Add explicit requirements or an
optional judge for those risks.
