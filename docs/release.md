# Release Checklist

Use this checklist when preparing a public alpha release from `develop`.
After this checklist passes, use [docs/launch.md](launch.md) for the public
alpha post, demo GIF, and first feedback loops. Use
[docs/repository.md](repository.md) to verify GitHub branch protection, tag,
security, and Pages settings before announcing.

## Preflight

- Work from a clean `develop` branch that is pushed to `origin/develop`.
- Update the version in `pyproject.toml` and `redline/__init__.py`.
- Update `CHANGELOG.md` with the user-visible changes.
- Run the packaged release gate:

```bash
bash scripts/release_check.sh
```

The release gate runs the unit suite, bytecode compilation, whitespace checks, a
Ruff lint, mypy type checking, a wheel build, clean virtualenv install,
`redline demo --compact`, runner listing, `redline init --runner stdio
--copy-runner`, and `redline doctor`. Run it from an environment where
`python -m pip install -e ".[dev]"` has already completed.

## Demo GIF

Record the launch GIF from a clean checkout after the release gate passes:

```bash
bash scripts/demo_gif.sh .redline/launch .redline/launch/redline-demo.gif
```

The script uses VHS when available, falls back to `asciinema` plus `agg`, and
writes `.redline/launch/redline-demo-transcript.txt` when neither recorder is
installed. Keep generated GIFs under `.redline/launch/` until the release post
or README asset path is chosen.

## Public Alpha Smoke

Run the first five minutes exactly like a new user. Use the full dogfood pass in
[docs/dogfood.md](dogfood.md) before tagging.

```bash
python -m pip install "git+https://github.com/gowtham0992/redline.git@develop"
redline demo
redline demo --public --compact
redline dashboard --reports-dir .redline/demo/reports --out .redline/dashboard.html
redline runners
redline init --runner stdio --copy-runner
redline doctor
```

Confirm the demo ends with actionable next steps, shows the mark/accept review
loop, and catches the intentional support-agent regressions. Confirm the
dashboard opens as a self-contained local report index. Confirm the
public-pattern proof works from the installed package without relying on
repo-local `examples/` paths.

Run the local external-project Action smoke before relying on the composite
GitHub Action from another repo:

```bash
bash scripts/action_smoke.sh
```

This creates a temporary project outside the redline checkout, installs the
package there, runs the same doctor/validate/eval/report/history/dashboard flow
that the composite action uses, and verifies the generated artifacts.

To run the package gate, external-project Action smoke, release build, and
`twine check` as one certification pass:

```bash
bash scripts/certify_release.sh /tmp/redline-certify-v0.1.0
```

The certification summary records the git commit, branch, and clean/dirty worktree state.
Release evidence can be traced back to the exact code that was tested.

## Tag

After the release gate and public-alpha smoke both pass:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Use a new tag for every public release. Do not move an existing release tag
after it has been pushed. Pushing a `v*` tag also runs the Release Artifacts
workflow, which certifies the release and uploads the wheel, source
distribution, and certification summary as GitHub Actions artifacts.
It does not publish to PyPI.

## Publish

For a PyPI release, build into a fresh output directory from the same commit
that was tagged. Do not upload an ignored local `dist/*`; it can contain stale
dogfood artifacts from earlier builds.

```bash
bash scripts/build_release.sh /tmp/redline-dist-v0.1.0
python -m twine upload /tmp/redline-dist-v0.1.0/*
```

Then install in a fresh environment and run:

```bash
redline --version
redline demo --compact
```
