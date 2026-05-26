import json
import tomllib
import unittest
from pathlib import Path


class PackagingTests(unittest.TestCase):
    def test_pyproject_declares_build_backend_and_cli_entrypoint(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertEqual(pyproject["project"]["name"], "redline-ai")
        self.assertEqual(pyproject["project"]["license"], "MIT")
        self.assertEqual(pyproject["project"]["scripts"]["redline"], "redline.cli:main")
        self.assertEqual(pyproject["project"]["scripts"]["redline-mcp"], "redline.mcp:main")
        self.assertIn("Generate eval suites", pyproject["project"]["description"])
        self.assertEqual(pyproject["project"]["urls"]["Repository"], "https://github.com/gowtham0992/redline")
        self.assertNotIn(
            "License :: OSI Approved :: MIT License",
            pyproject["project"]["classifiers"],
        )

    def test_dev_dependencies_include_release_tools(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]

        self.assertIn("build>=1.2", dev_dependencies)
        self.assertIn("setuptools>=68", dev_dependencies)
        self.assertIn("twine>=5", dev_dependencies)

    def test_package_is_marked_typed(self) -> None:
        self.assertTrue(Path("redline/py.typed").exists())
        manifest = Path("MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("include LICENSE", manifest)
        self.assertIn("redline py.typed", manifest)
        self.assertIn("action.yml", manifest)
        self.assertIn("server.json", manifest)
        self.assertIn("redline-suite.schema.json", manifest)
        self.assertIn("redline-report.schema.json", manifest)
        self.assertIn("redline/runner_templates", manifest)
        self.assertIn("redline/judge_template_files", manifest)
        self.assertIn("examples *.jsonl *.md", manifest)
        self.assertIn("docs *.md *.jsonl", manifest)
        self.assertIn("scripts *.py *.sh", manifest)
        self.assertIn("site *.html *.css *.png *.svg *.gif", manifest)

    def test_license_file_matches_package_metadata(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        license_text = Path("LICENSE").read_text(encoding="utf-8")

        self.assertEqual(pyproject["project"]["license"], "MIT")
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 Gowtham Sarveswaran", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)

    def test_shell_scripts_are_executable(self) -> None:
        for script_name in (
            "action_smoke.sh",
            "build_release.sh",
            "certify_release.sh",
            "demo_gif.sh",
            "demo_terminal.sh",
            "release_check.sh",
        ):
            with self.subTest(script=script_name):
                script = Path("scripts") / script_name

                self.assertTrue(script.exists())
                self.assertTrue(script.stat().st_mode & 0o111)

    def test_demo_recording_script_runs_compact_demo(self) -> None:
        script = Path("scripts/demo_terminal.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("redline launch demo", text)
        self.assertIn("redline demo --public --compact", text)
        self.assertIn("redline history", text)
        self.assertIn("--out-md", text)
        self.assertIn("redline dashboard", text)

    def test_demo_gif_script_records_or_writes_transcript(self) -> None:
        script = Path("scripts/demo_gif.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("redline-demo.gif", text)
        self.assertIn("vhs", text)
        self.assertIn("asciinema", text)
        self.assertIn("redline-demo-transcript.txt", text)
        self.assertIn("redline demo --public --compact", text)

    def test_release_check_builds_and_smokes_installed_wheel(self) -> None:
        script = Path("scripts/release_check.sh").read_text(encoding="utf-8")

        self.assertIn("-m unittest discover", script)
        self.assertIn("-m compileall redline tests examples scripts", script)
        self.assertIn("-m ruff check .", script)
        self.assertIn("-m mypy redline tests scripts examples", script)
        self.assertIn("git diff --check", script)
        self.assertIn("PIP_CACHE_DIR", script)
        self.assertIn("PIP_DISABLE_PIP_VERSION_CHECK=1", script)
        self.assertIn("-m ensurepip --upgrade", script)
        self.assertIn("examples/public_dogfood_baseline.jsonl", script)
        self.assertIn("examples/public_dogfood_candidate.jsonl", script)
        self.assertIn("-m pip wheel . --no-deps --no-build-isolation", script)
        self.assertIn("-m venv", script)
        self.assertIn("redline --version", script)
        self.assertIn("redline-mcp --help", script)
        self.assertIn("redline-mcp tools/list smoke", script)
        self.assertIn("redline-mcp prompts/list smoke", script)
        self.assertIn("check_prompt_change", script)
        self.assertIn("$ redline\\n", script)
        self.assertIn("redline demo --compact", script)
        self.assertIn("redline demo --public --compact", script)
        self.assertIn("redline prompts .redline/demo/prompts/v2.txt", script)
        self.assertIn("redline summary redline-prompts.json", script)
        self.assertIn("redline validate redline-prompts.json --strict", script)
        self.assertIn("redline benchmark redline-prompts.json", script)
        self.assertIn("manifest-benchmark.md", script)
        self.assertIn("redline eval redline-prompts.json", script)
        self.assertIn("--out-comment manifest-eval-comment.md", script)
        self.assertIn("manifest-eval.html", script)
        self.assertIn("redline history .redline/demo/reports/diff.json", script)
        self.assertIn("--out-md history.md", script)
        self.assertIn("redline compare .redline/demo/reports/diff.json", script)
        self.assertIn("--out-html compare.html", script)
        self.assertIn("redline dashboard --reports-dir .redline/demo/reports", script)
        self.assertIn("--github-summary", script)
        self.assertIn("--all-cases", script)
        self.assertIn("redline suite add all-suite.json", script)
        self.assertIn("redline validate pinned-suite.json", script)
        self.assertIn("--out-html diff.html", script)
        self.assertIn("--out-comment diff-comment.md", script)
        self.assertIn("--profile review", script)
        self.assertIn("redline judges", script)
        self.assertIn("redline doctor", script)

    def test_release_build_script_uses_fresh_output_dir(self) -> None:
        script = Path("scripts/build_release.sh").read_text(encoding="utf-8")

        self.assertIn("-m build --no-isolation --outdir", script)
        self.assertIn("output directory is not empty", script)
        self.assertIn("redline_ai-*.whl", script)
        self.assertIn("redline_ai-*.tar.gz", script)
        self.assertIn("-m twine check", script)

    def test_action_smoke_script_exercises_external_project_flow(self) -> None:
        script = Path("scripts/action_smoke.sh").read_text(encoding="utf-8")

        self.assertIn("external-project", script)
        self.assertIn("pip wheel", script)
        self.assertIn("--no-build-isolation", script)
        self.assertIn("pip install --no-deps", script)
        self.assertIn("redline suite baseline.jsonl", script)
        self.assertIn("redline doctor --strict", script)
        self.assertIn("redline validate redline-suite.json --strict", script)
        self.assertIn("redline eval", script)
        self.assertIn("--github-summary", script)
        self.assertIn("--out-comment .redline/reports/eval-comment.md", script)
        self.assertIn("--out-slack .redline/reports/eval.slack.json", script)
        self.assertIn("do not emit GitHub error", script)
        self.assertNotIn("--github-annotations", script)
        self.assertIn("expected redline eval to return 1", script)
        self.assertIn("redline history", script)
        self.assertIn("redline dashboard", script)

    def test_certify_release_script_runs_all_release_gates(self) -> None:
        script = Path("scripts/certify_release.sh").read_text(encoding="utf-8")

        self.assertIn("scripts/release_check.sh", script)
        self.assertIn("scripts/action_smoke.sh", script)
        self.assertIn("scripts/build_release.sh", script)
        self.assertIn("certification.txt", script)
        self.assertIn("git rev-parse --short HEAD", script)
        self.assertIn("git branch --show-current", script)
        self.assertIn("git status --porcelain", script)
        self.assertIn("worktree:", script)
        self.assertIn("release certification passed", script)

    def test_release_guide_documents_package_gate(self) -> None:
        guide = Path("docs/release.md").read_text(encoding="utf-8")

        self.assertIn("bash scripts/release_check.sh", guide)
        self.assertIn("bash scripts/action_smoke.sh", guide)
        self.assertIn("bash scripts/certify_release.sh", guide)
        self.assertIn("bash scripts/build_release.sh", guide)
        self.assertIn("docs/launch.md", guide)
        self.assertIn("docs/repository.md", guide)
        self.assertIn("Do not upload an ignored local `dist/*`", guide)
        self.assertIn("docs/dogfood.md", guide)
        self.assertIn("pyproject.toml", guide)
        self.assertIn("redline/__init__.py", guide)
        self.assertIn("CHANGELOG.md", guide)
        self.assertIn("git commit, branch, and clean/dirty worktree state", guide)
        self.assertIn('python -m pip install -e ".[dev]"', guide)
        self.assertIn("redline demo --compact", guide)
        self.assertIn("redline demo --public --compact", guide)
        self.assertIn("bash scripts/demo_gif.sh", guide)
        self.assertIn("redline init --runner stdio --copy-runner", guide)
        self.assertIn("MCP Registry", guide)
        self.assertIn("server.json", guide)
        self.assertIn("mcp-publisher publish", guide)

    def test_readme_marks_repo_only_script_commands(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("site/assets/redline-logo.svg", readme)
        self.assertIn("site/assets/redline-logo-dark.svg", readme)
        self.assertIn("https://gowtham0992.github.io/redline/assets/redline-product-demo.gif", readme)
        self.assertIn("Automatic eval suites from the prompt logs you already have", readme)
        self.assertIn("Product Promise", readme)
        self.assertIn("[![PyPI](https://img.shields.io/pypi/v/redline-ai.svg)](https://pypi.org/project/redline-ai/)", readme)
        self.assertIn("[![MCP Registry]", readme)
        self.assertIn("registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Fredline", readme)
        self.assertIn("[![License: MIT]", readme)
        self.assertIn("[![Stars](https://img.shields.io/github/stars/gowtham0992/redline?style=social)]", readme)
        self.assertIn('<a href="LICENSE">License</a>', readme)
        self.assertIn("python -m pip install redline-ai", readme)
        self.assertIn("redline judges", readme)
        self.assertIn("feature-level", readme)
        self.assertIn("From a repo checkout, record the public demo", readme)
        self.assertIn("scripts/normalize_ai_session_logs.py", readme)
        self.assertIn("actions/workflows/ci.yml/badge.svg?branch=main", readme)
        self.assertIn("actions/workflows/pages.yml/badge.svg?branch=main", readme)
        self.assertNotIn("redline.git@develop", readme)
        self.assertNotIn("branch=develop", readme)
        self.assertIn("python -m pytest -q", readme)
        self.assertIn("python -m ruff check .", readme)
        self.assertIn("python -m mypy redline tests scripts examples", readme)
        self.assertIn("redline-prompts.json --check --check-suites", readme)
        self.assertIn("redline summary redline-prompts.json", readme)
        self.assertIn("redline validate redline-prompts.json --strict", readme)
        self.assertIn("redline benchmark redline-prompts.json", readme)
        self.assertIn("--out-comment .redline/reports/diff-comment.md", readme)
        self.assertIn("--out-slack .redline/reports/diff.slack.json", readme)
        self.assertIn("concise PR-comment Markdown", readme)
        self.assertIn("Slack Block Kit JSON", readme)
        self.assertIn("prompt-level rollups", readme)
        self.assertIn("redline eval redline-prompts.json", readme)
        self.assertIn("prompt-manifest rollups", readme)
        self.assertIn("feature and prompt eval tables", readme)
        self.assertIn("point `suite` at `redline-prompts.json`", readme)
        self.assertIn("redline prompts --check --check-suites", readme)
        self.assertIn("redline eval suites/support/triage.redline-suite.json", readme)
        self.assertIn("prompt-level", readme)
        self.assertIn("review queue", readme)

    def test_private_product_docs_stay_ignored(self) -> None:
        ignore = Path(".gitignore").read_text(encoding="utf-8")

        self.assertIn("redline_product_vision*.docx", ignore)
        self.assertIn("ROADMAP.md", ignore)

    def test_changelog_mentions_release_ready_workflows(self) -> None:
        changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("Markdown history reports", changelog)
        self.assertIn("self-contained HTML", changelog)
        self.assertIn("GitHub step summaries", changelog)
        self.assertIn("suite generation commands", changelog)
        self.assertIn("review` diff profile", changelog)
        self.assertIn("suite --all-cases", changelog)
        self.assertIn("redline suite add", changelog)
        self.assertIn("redline dashboard", changelog)
        self.assertIn("dashboard reports table", changelog)
        self.assertIn("latest-report review queue", changelog)
        self.assertIn("redline compare", changelog)
        self.assertIn("human-readable behavior labels", changelog)
        self.assertIn("ready `redline eval", changelog)
        self.assertIn("concise PR-comment Markdown", changelog)
        self.assertIn("Summarize prompt manifests", changelog)
        self.assertIn("redline validate redline-prompts.json", changelog)
        self.assertIn("redline eval redline-prompts.json", changelog)
        self.assertIn("richer judge rubrics", changelog)
        self.assertIn("redline judges", changelog)
        self.assertIn("product-focused README", changelog)
        self.assertIn("redline-mcp", changelog)
        self.assertIn("MCP Registry metadata", changelog)
        self.assertIn("public alpha launch playbook", changelog)

    def test_launch_playbook_covers_assets_and_feedback(self) -> None:
        guide = Path("docs/launch.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("redline-demo.gif", guide)
        self.assertIn("https://gowtham0992.github.io/redline/assets/redline-product-demo.gif", guide)
        self.assertIn("python -m pip install redline-ai", guide)
        self.assertIn("Website Checklist", guide)
        self.assertIn("Demo GIF Storyboard", guide)
        self.assertIn("First 10 Feedback Loops", guide)
        self.assertIn("GitHub dogfood issue", guide)
        self.assertIn("false-negative", guide)
        self.assertIn("Do not add a desktop app", guide)
        self.assertIn("docs/launch.md", readme)

    def test_mcp_docs_explain_local_agent_server(self) -> None:
        guide = Path("docs/mcp.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("redline-mcp", guide)
        self.assertIn("local Model Context Protocol server", guide)
        self.assertIn("redline_doctor", guide)
        self.assertIn("redline_eval", guide)
        self.assertIn("redline_diff", guide)
        self.assertIn("check_prompt_change", guide)
        self.assertIn("build_suite_from_logs", guide)
        self.assertIn("redline_mark", guide)
        self.assertIn("allow_write: true", guide)
        self.assertIn("Baseline promotion commands", guide)
        self.assertIn("Exit code `1` means redline found blocking regressions", guide)
        self.assertIn("uvx --from redline-ai", guide)
        self.assertIn("io.github.gowtham0992/redline", guide)
        self.assertIn("docs/mcp.md", readme)

    def test_mcp_registry_manifest_matches_package_metadata(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        manifest = json.loads(Path("server.json").read_text(encoding="utf-8"))
        readme = Path("README.md").read_text(encoding="utf-8")
        init = Path("redline/__init__.py").read_text(encoding="utf-8")
        package = manifest["packages"][0]

        self.assertEqual(
            manifest["$schema"],
            "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        )
        self.assertEqual(manifest["name"], "io.github.gowtham0992/redline")
        self.assertLessEqual(len(manifest["description"]), 100)
        self.assertEqual(manifest["version"], pyproject["project"]["version"])
        self.assertIn(f'__version__ = "{manifest["version"]}"', init)
        self.assertIn("mcp-name: io.github.gowtham0992/redline", readme)
        self.assertEqual(package["registryType"], "pypi")
        self.assertEqual(package["registryBaseUrl"], "https://pypi.org")
        self.assertEqual(package["identifier"], pyproject["project"]["name"])
        self.assertEqual(package["version"], pyproject["project"]["version"])
        self.assertEqual(package["runtimeHint"], "uvx")
        self.assertEqual(package["transport"]["type"], "stdio")
        self.assertIn(
            {
                "type": "named",
                "name": "--from",
                "value": f'redline-ai=={pyproject["project"]["version"]}',
                "description": "Install the redline-ai package version that matches this registry entry.",
            },
            package["runtimeArguments"],
        )
        self.assertIn(
            {
                "type": "positional",
                "value": "redline-mcp",
                "description": "Run the redline MCP stdio entrypoint.",
            },
            package["runtimeArguments"],
        )

    def test_github_issue_templates_collect_bug_and_dogfood_feedback(self) -> None:
        bug = Path(".github/ISSUE_TEMPLATE/bug_report.yml").read_text(encoding="utf-8")
        dogfood = Path(".github/ISSUE_TEMPLATE/dogfood_feedback.yml").read_text(encoding="utf-8")
        config = Path(".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")

        self.assertIn("redline version", bug)
        self.assertIn("redline doctor", bug)
        self.assertIn("Dogfood feedback", dogfood)
        self.assertIn("What did redline catch?", dogfood)
        self.assertIn("Where did you hesitate?", dogfood)
        self.assertIn("blank_issues_enabled: true", config)

    def test_repository_ci_runs_full_release_gate(self) -> None:
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("pull_request:", workflow)
        self.assertIn("- develop", workflow)
        self.assertIn("- main", workflow)
        self.assertRegex(workflow, r"actions/checkout@v\d+")
        self.assertRegex(workflow, r"actions/setup-python@v\d+")
        self.assertIn('cache: "pip"', workflow)
        self.assertIn('python -m pip install -e ".[dev]"', workflow)
        self.assertIn("bash -n scripts/*.sh", workflow)
        self.assertIn("python -m pytest -q", workflow)
        self.assertIn("python -m ruff check .", workflow)
        self.assertIn("python -m mypy redline tests scripts examples", workflow)
        self.assertIn("bash scripts/action_smoke.sh", workflow)
        self.assertIn('bash scripts/build_release.sh "$RUNNER_TEMP/redline-dist"', workflow)

    def test_pages_workflow_deploys_public_site_from_main_only(self) -> None:
        workflow = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")

        self.assertIn("- main", workflow)
        self.assertNotIn("- develop", workflow)
        self.assertIn("path: site", workflow)

    def test_release_workflow_builds_artifacts_without_publishing(self) -> None:
        workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        guide = Path("docs/release.md").read_text(encoding="utf-8")

        self.assertIn("- \"v*\"", workflow)
        self.assertRegex(workflow, r"actions/setup-python@v\d+")
        self.assertIn('cache: "pip"', workflow)
        self.assertIn('python -m pip install -e ".[dev]"', workflow)
        self.assertIn('bash scripts/certify_release.sh "$RUNNER_TEMP/redline-certify"', workflow)
        self.assertRegex(workflow, r"actions/upload-artifact@v\d+")
        self.assertIn("redline-release-distributions", workflow)
        self.assertIn("redline-release-certification", workflow)
        self.assertNotIn("pypa/gh-action-pypi-publish", workflow)
        self.assertIn("Release Artifacts", guide)
        self.assertIn("It does not publish to PyPI", guide)

    def test_dependabot_tracks_actions_and_python_tooling(self) -> None:
        config = Path(".github/dependabot.yml").read_text(encoding="utf-8")

        self.assertIn('package-ecosystem: "github-actions"', config)
        self.assertIn('package-ecosystem: "pip"', config)
        self.assertEqual(config.count('target-branch: "develop"'), 2)
        self.assertEqual(config.count('interval: "weekly"'), 2)
        self.assertNotIn("labels:", config)

    def test_contributor_docs_require_dogfood_and_validation(self) -> None:
        guide = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
        template = Path(".github/pull_request_template.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn('python -m pip install -e ".[dev]"', guide)
        self.assertIn("python -m pytest -q", guide)
        self.assertIn("python -m ruff check .", guide)
        self.assertIn("python -m mypy redline tests scripts examples", guide)
        self.assertIn("bash scripts/action_smoke.sh /tmp/redline-action-smoke", guide)
        self.assertIn("bash scripts/build_release.sh /tmp/redline-dist", guide)
        self.assertIn("bash scripts/certify_release.sh /tmp/redline-certify", guide)
        self.assertIn("Command: redline demo --public --compact", guide)
        self.assertIn("A neutral result means", guide)
        self.assertIn("Do not commit private prompts", guide)
        self.assertIn("Dogfood evidence", template)
        self.assertIn("Trust boundary", template)
        self.assertIn("Private prompts", template)
        self.assertIn("CONTRIBUTING.md", readme)

    def test_repository_settings_document_launch_controls(self) -> None:
        guide = Path("docs/repository.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("Protect `develop` and `main`", guide)
        self.assertIn("Test and certify", guide)
        self.assertIn("Block force pushes", guide)
        self.assertIn("immutable `v*` release tags", guide)
        self.assertIn("private vulnerability reporting", guide)
        self.assertIn("Dependabot alerts", guide)
        self.assertIn(".github/workflows/pages.yml", guide)
        self.assertIn("on `main`", guide)
        self.assertIn("bash scripts/certify_release.sh /tmp/redline-certify-v0.1.0", guide)
        self.assertIn("docs/repository.md", readme)

    def test_security_policy_documents_local_privacy_boundary(self) -> None:
        policy = Path("SECURITY.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("does not call any cloud model", policy)
        self.assertIn(".redline/private/", policy)
        self.assertIn("Do not commit private logs", policy)
        self.assertIn("redline doctor", policy)
        self.assertIn("redline runners", policy)
        self.assertIn("GitHub private vulnerability reporting", policy)
        self.assertIn("SECURITY.md", readme)

    def test_dogfood_protocol_exercises_first_run_loop(self) -> None:
        guide = Path("docs/dogfood.md").read_text(encoding="utf-8")

        self.assertIn("redline demo", guide)
        self.assertIn("redline demo --public --compact", guide)
        self.assertIn("redline runners", guide)
        self.assertIn("redline init --runner stdio --copy-runner --github-action", guide)
        self.assertIn("redline suite .redline/demo/baseline.jsonl", guide)
        self.assertIn("examples/public_dogfood_baseline.jsonl", guide)
        self.assertIn("public_dogfood_sources.md", guide)
        self.assertIn("normalize_ai_session_logs.py", guide)
        self.assertIn("ai-session-dogfood-prompts.jsonl", guide)
        self.assertIn("severity: blocker | confusing | polish", guide)

    def test_public_dogfood_fixture_documents_source_inspiration(self) -> None:
        sources = Path("examples/public_dogfood_sources.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("synthetic", sources)
        self.assertIn("Databricks Dolly 15k", sources)
        self.assertIn("OpenAssistant OASST1", sources)
        self.assertIn("Anthropic HH-RLHF", sources)
        self.assertIn("WildChat", sources)
        self.assertIn("examples/public_dogfood_baseline.jsonl", readme)
        self.assertIn("examples/public_dogfood_candidate.jsonl", readme)

    def test_ai_session_prompt_set_has_ten_prompts(self) -> None:
        prompts = Path("docs/ai-session-dogfood-prompts.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(prompts), 10)
        self.assertTrue(all(json.loads(line)["prompt"] for line in prompts))

    def test_pyproject_includes_runner_templates(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("runner_templates/*", pyproject["tool"]["setuptools"]["package-data"]["redline"])
        self.assertIn("judge_template_files/*", pyproject["tool"]["setuptools"]["package-data"]["redline"])

    def test_readme_product_gif_is_committed(self) -> None:
        gif = Path("site/assets/redline-product-demo.gif")

        self.assertTrue(gif.exists())
        self.assertGreater(gif.stat().st_size, 100_000)
        self.assertLess(gif.stat().st_size, 1_000_000)


if __name__ == "__main__":
    unittest.main()
