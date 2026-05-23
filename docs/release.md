# Release Checklist

Use this checklist when preparing a public alpha release from `develop`.

## Preflight

- Work from a clean `develop` branch that is pushed to `origin/develop`.
- Update the version in `pyproject.toml` and `redline/__init__.py`.
- Update `CHANGELOG.md` with the user-visible changes.
- Run the packaged release gate:

```bash
bash scripts/release_check.sh
```

The release gate runs the unit suite, bytecode compilation, whitespace checks, a
wheel build, clean virtualenv install, `redline demo --compact`, runner listing,
`redline init --runner openai --copy-runner`, and `redline doctor`.

## Public Alpha Smoke

Run the first five minutes exactly like a new user. Use the full dogfood pass in
[docs/dogfood.md](dogfood.md) before tagging.

```bash
python -m pip install "git+https://github.com/gowtham0992/redline.git@develop"
redline demo
redline runners
redline init --runner openai --copy-runner
redline doctor
```

Confirm the demo ends with actionable next steps and catches the intentional
support-agent regressions.

## Tag

After the release gate and public-alpha smoke both pass:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Use a new tag for every public release. Do not move an existing release tag
after it has been pushed.

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
