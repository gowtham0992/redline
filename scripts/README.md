# Scripts

These helpers are for maintainers and release validation. They are not included
in the PyPI source distribution.

| Script | Purpose |
| --- | --- |
| `action_smoke.sh` | Build a wheel, install it into a temporary external project, and run the Action-like flow end to end. |
| `build_release.sh` | Build wheel/sdist artifacts, run `twine check`, and write SBOM release evidence. |
| `certify_release.sh` | Run package gate, Action smoke, release build, and certification summary. |
| `demo_gif.sh` | Record or write transcript artifacts for the launch demo. |
| `demo_terminal.sh` | Drive the public demo terminal story. |
| `normalize_ai_session_logs.py` | Normalize private AI assistant session exports for local dogfood. |
| `release_check.sh` | Run tests, static checks, build/install smoke, public demo, MCP smoke, and manifest eval proof. |

Generated outputs should go under `/tmp` or `.redline/private/` unless a release
guide explicitly says to attach them as artifacts.
