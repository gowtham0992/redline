import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from redline.cli import main
from redline.history import (
    format_history,
    format_markdown_history,
    history_entry,
    history_trend,
    parse_history_fail_on,
    should_fail_history,
)


class HistoryTests(unittest.TestCase):
    def test_history_entry_keeps_report_summary(self) -> None:
        entry = history_entry(
            {"summary": {"cases": 5, "regression": 2, "neutral": 3}},
            report_path="eval.json",
            label="prompt-v2",
            timestamp="2026-05-23T12:00:00Z",
        )

        self.assertEqual(entry["version"], "0.1")
        self.assertEqual(entry["report"], "eval.json")
        self.assertEqual(entry["label"], "prompt-v2")
        self.assertEqual(entry["summary"]["cases"], 5)
        self.assertEqual(entry["summary"]["regression"], 2)

    def test_format_history_prints_one_line_per_report(self) -> None:
        text = format_history(
            [
                {
                    "timestamp": "2026-05-23T12:00:00Z",
                    "label": "prompt-v2",
                    "report": "eval.json",
                    "summary": {"cases": 5, "regression": 2, "neutral": 3},
                }
            ]
        )

        self.assertIn("redline history", text)
        self.assertIn("Trend: BASELINE", text)
        self.assertIn("prompt-v2", text)
        self.assertIn("cases=5 regression=2 neutral=3", text)

    def test_history_trend_flags_worse_blocking_rate(self) -> None:
        trend = history_trend(
            [
                {
                    "timestamp": "2026-05-23T12:00:00Z",
                    "label": "prompt-v1",
                    "report": "eval-v1.json",
                    "summary": {"cases": 10, "regression": 1, "missing": 0, "changed": 2},
                },
                {
                    "timestamp": "2026-05-23T13:00:00Z",
                    "label": "prompt-v2",
                    "report": "eval-v2.json",
                    "summary": {"cases": 10, "regression": 2, "missing": 1, "changed": 3},
                },
            ]
        )

        self.assertEqual(trend["direction"], "worse")
        self.assertEqual(trend["latest"]["blocking"], 3)
        self.assertEqual(trend["delta"]["blocking"], 2)
        self.assertIn("investigate", trend["recommendation"])

    def test_format_history_prints_trend_before_rows(self) -> None:
        text = format_history(
            [
                {
                    "timestamp": "2026-05-23T12:00:00Z",
                    "label": "prompt-v1",
                    "report": "eval-v1.json",
                    "summary": {"cases": 10, "regression": 3, "missing": 0, "changed": 1},
                },
                {
                    "timestamp": "2026-05-23T13:00:00Z",
                    "label": "prompt-v2",
                    "report": "eval-v2.json",
                    "summary": {"cases": 10, "regression": 1, "missing": 0, "changed": 1},
                },
            ]
        )

        self.assertIn("Trend: BETTER", text)
        self.assertIn("blocking=1/10 (10.0%)", text)
        self.assertIn("blocking -2", text)

    def test_format_markdown_history_prints_report_table(self) -> None:
        text = format_markdown_history(
            [
                {
                    "timestamp": "2026-05-23T12:00:00Z",
                    "label": "prompt-v2",
                    "report": ".redline/reports/eval.json",
                    "summary": {"cases": 5, "regression": 2, "neutral": 3},
                }
            ]
        )

        self.assertIn("# redline history", text)
        self.assertIn("## Trend", text)
        self.assertIn("| Timestamp | Label | Report | Summary |", text)
        self.assertIn("prompt-v2", text)
        self.assertIn("cases=5 regression=2 neutral=3", text)

    def test_cli_appends_report_to_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "eval.json"
            history = root / "history.jsonl"
            report.write_text(
                json.dumps({"summary": {"cases": 2, "regression": 1, "neutral": 1}}),
                encoding="utf-8",
            )

            output = _run_cli(["history", str(report), "--label", "prompt-v2", "--out", str(history)])

            self.assertIn("Recorded", output)
            self.assertIn("prompt-v2", output)
            rows = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["summary"]["regression"], 1)

    def test_cli_json_includes_history_trend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history.jsonl"
            history.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "version": "0.1",
                                "timestamp": "2026-05-23T12:00:00Z",
                                "label": "prompt-v1",
                                "report": "eval-v1.json",
                                "summary": {"cases": 4, "regression": 2, "missing": 0},
                            }
                        ),
                        json.dumps(
                            {
                                "version": "0.1",
                                "timestamp": "2026-05-23T13:00:00Z",
                                "label": "prompt-v2",
                                "report": "eval-v2.json",
                                "summary": {"cases": 4, "regression": 1, "missing": 0},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            output = _run_cli(["history", "--out", str(history), "--json"])
            payload = json.loads(output)

        self.assertEqual(payload["trend"]["direction"], "better")
        self.assertEqual(payload["trend"]["delta"]["blocking"], -1)

    def test_parse_history_fail_on_accepts_directions_and_none(self) -> None:
        self.assertEqual(parse_history_fail_on("worse,more_changed"), {"worse", "more_changed"})
        self.assertEqual(parse_history_fail_on("none"), set())

    def test_parse_history_fail_on_rejects_unknown_direction(self) -> None:
        with self.assertRaisesRegex(ValueError, "history --fail-on"):
            parse_history_fail_on("regression")

    def test_should_fail_history_uses_trend_direction(self) -> None:
        trend = {"direction": "worse"}

        self.assertTrue(should_fail_history(trend, {"worse"}))
        self.assertFalse(should_fail_history(trend, {"better"}))

    def test_cli_history_fail_on_uses_trend_direction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history.jsonl"
            history.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "version": "0.1",
                                "timestamp": "2026-05-23T12:00:00Z",
                                "label": "prompt-v1",
                                "report": "eval-v1.json",
                                "summary": {"cases": 4, "regression": 0, "missing": 0},
                            }
                        ),
                        json.dumps(
                            {
                                "version": "0.1",
                                "timestamp": "2026-05-23T13:00:00Z",
                                "label": "prompt-v2",
                                "report": "eval-v2.json",
                                "summary": {"cases": 4, "regression": 1, "missing": 0},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["history", "--out", str(history), "--fail-on", "worse"])

        self.assertEqual(code, 1)
        self.assertIn("Trend: WORSE", output.getvalue())

    def test_cli_writes_markdown_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "eval.json"
            history = root / "history.jsonl"
            markdown = root / "history.md"
            report.write_text(
                json.dumps({"summary": {"cases": 2, "regression": 1, "neutral": 1}}),
                encoding="utf-8",
            )

            _run_cli(
                [
                    "history",
                    str(report),
                    "--label",
                    "prompt-v2",
                    "--out",
                    str(history),
                    "--out-md",
                    str(markdown),
                ]
            )

            text = markdown.read_text(encoding="utf-8")
            self.assertIn("# redline history", text)
            self.assertIn("prompt-v2", text)
            self.assertIn("regression=1", text)

    def test_cli_appends_markdown_history_to_github_summary(self) -> None:
        previous_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "eval.json"
            history = root / "history.jsonl"
            summary = root / "summary.md"
            report.write_text(
                json.dumps({"summary": {"cases": 2, "regression": 1, "neutral": 1}}),
                encoding="utf-8",
            )
            try:
                os.environ["GITHUB_STEP_SUMMARY"] = str(summary)

                _run_cli(
                    [
                        "history",
                        str(report),
                        "--label",
                        "prompt-v2",
                        "--out",
                        str(history),
                        "--github-summary",
                    ]
                )
            finally:
                if previous_summary is None:
                    os.environ.pop("GITHUB_STEP_SUMMARY", None)
                else:
                    os.environ["GITHUB_STEP_SUMMARY"] = previous_summary

            text = summary.read_text(encoding="utf-8")
            self.assertIn("# redline history", text)
            self.assertIn("prompt-v2", text)

    def test_cli_rejects_github_summary_without_env(self) -> None:
        previous_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        try:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            with tempfile.TemporaryDirectory() as directory:
                history = Path(directory) / "history.jsonl"
                history.write_text(
                    json.dumps(
                        {
                            "version": "0.1",
                            "timestamp": "2026-05-23T12:00:00Z",
                            "label": "prompt-v2",
                            "report": "eval.json",
                            "summary": {"cases": 2},
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                output = io.StringIO()
                error = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                    code = main(["history", "--out", str(history), "--github-summary"])
        finally:
            if previous_summary is not None:
                os.environ["GITHUB_STEP_SUMMARY"] = previous_summary

        self.assertEqual(code, 2)
        self.assertIn("--github-summary requires GITHUB_STEP_SUMMARY", error.getvalue())

    def test_cli_rejects_negative_limit(self) -> None:
        output = io.StringIO()
        error = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main(["history", "--limit", "-1"])

        self.assertEqual(code, 2)
        self.assertIn("history --limit must be 0 or greater", error.getvalue())


def _run_cli(args: list[str]) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(args)
    if code != 0:
        raise AssertionError(f"redline {' '.join(args)} exited {code}: {output.getvalue()}")
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
