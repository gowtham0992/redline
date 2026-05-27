# Repository Settings

Use this checklist before a public alpha announcement. These settings are not
stored in git, so keep this file as the source of truth for how the GitHub repo
should be configured.

## Branches

Protect `develop` and `main`.

Required status checks:

- `Test and certify` from `.github/workflows/ci.yml`

Recommended branch rules:

- Require pull requests before merging.
- Require branches to be up to date before merging.
- Require conversation resolution before merging.
- Block force pushes.
- Block deletions.
- Use linear history if the repository keeps squash/rebase-only merges.

`develop` is the active product branch. `main` should stay stable and should
only receive release-ready changes or explicit user-approved syncs from
`develop`.

## Tags and Releases

Use immutable `v*` release tags. After a tag is pushed, do not move it. If a
release needs a fix, cut a new patch tag.

Before tagging, run:

```bash
bash scripts/certify_release.sh /tmp/redline-certify-v0.2.1
```

Build and upload PyPI artifacts from the exact tagged commit, using a fresh
output directory.

## Security

Enable GitHub private vulnerability reporting when available. Keep Dependabot alerts
enabled for GitHub Actions and Python packaging metadata.

Do not ask users to attach raw prompt logs to public issues. Use sanitized or
synthetic reproductions and point reporters to `SECURITY.md` for sensitive
reports.

## License

Keep the repository license visible as MIT in `LICENSE`, `pyproject.toml`, the
README badge, the PyPI package metadata, and the GitHub Pages resource links.

## GitHub Pages

Deploy Pages from `site/` through `.github/workflows/pages.yml` on `main`.
The site should link to the GitHub repo, CI status, contributor guide, security
policy, MIT license, and the quickstart.

## Launch Check

Before posting publicly:

```bash
git status --short --branch
bash scripts/certify_release.sh /tmp/redline-certify-v0.2.1
bash scripts/demo_gif.sh .redline/launch .redline/launch/redline-demo.gif
```

Confirm the working tree is clean, `main` is pushed, the release gate passed,
and the demo GIF or transcript is generated from the same code users will
install.
