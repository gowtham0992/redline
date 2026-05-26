# Security and privacy

redline is designed for local prompt-eval workflows. By default it reads local
JSONL logs, writes local suites and reports, and does not call any cloud model
or hosted service.

## Supported versions

This repository is pre-1.0. Security fixes land on `develop` first and are
included in the next tagged release when release packaging is cut.

## Data handling

- Keep private prompt logs, model outputs, customer data, and raw dogfood exports
  under `.redline/private/` or another ignored local path.
- Do not commit private logs, API keys, secrets, customer identifiers, or product
  vision drafts.
- Sanitize logs before attaching them to issues, PRs, release notes, screenshots,
  or demo GIFs.
- Prefer synthetic or minimized reproductions when reporting bugs.

## Network behavior

Core redline commands are local-only. Network calls happen only when you
explicitly configure a replay command, judge command, or runner template that
calls a provider, proxy, or application endpoint.

`RedlineMiddleware` and SDK watch snippets run inside your application process.
They still write locally, but they can observe prompts, request bodies, response
bodies, headers, and metadata that your app handles. Capture is bounded,
JSON-oriented, and redacted with best-effort common secret and PII patterns, but
that redaction is not a privacy boundary. Review logs before sharing them.

Before running third-party or copied runner scripts, inspect the command in
`redline.json` and the environment variables it needs:

```bash
redline doctor
redline runners
```

## Release evidence

Generate a CycloneDX SBOM from the installed package or checkout before security
review:

```bash
redline sbom --out redline-sbom.json
```

The SBOM records the redline package, runtime dependencies, local-first
guarantee, and telemetry status. `scripts/build_release.sh` writes the same SBOM
next to wheel and source distribution artifacts.

## Reporting a vulnerability

Use GitHub private vulnerability reporting if it is enabled for the repository.
If private reporting is unavailable, open a public issue with a minimal
description and no secrets, private prompts, raw outputs, customer data, or
exploit payloads. Ask for a private handoff channel before sharing sensitive
details.

For ordinary bugs, use the bug report template and include sanitized command
output plus `redline doctor` results.
