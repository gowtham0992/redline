import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from redline.cli import main
from redline.history import format_history, history_entry


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
