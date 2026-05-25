import unittest
from tempfile import TemporaryDirectory
from typing import Any

from redline.benchmark import (
    benchmark_prompt_manifest,
    benchmark_suite,
    format_benchmark_markdown,
    format_benchmark_report,
)
from redline.io import LogRecord, write_json
from redline.requirements import add_case_requirement
from redline.suite import build_suite


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_suite_estimates_parallel_eval_budget(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON", '{"ok": true}', {}),
                LogRecord(2, "Summarize", "- one\n- two", {}),
                LogRecord(3, "Draft reply", "Hello", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
            all_cases=True,
        )
        add_case_requirement(suite, suite["cases"][0]["id"], include=["ok"])

        report = benchmark_suite(
            suite,
            suite_path="suite.json",
            timeout_seconds=30,
            workers=2,
        )

        self.assertEqual(report["suite"], "suite.json")
        self.assertEqual(report["cases"], 3)
        self.assertEqual(report["mode"], "static_eval_budget_estimate")
        self.assertEqual(report["clusters"], 3)
        self.assertEqual(report["parallel_waves"], 2)
        self.assertEqual(report["worst_case_seconds"], 60)
        self.assertEqual(report["sequential_worst_case_seconds"], 90)
        self.assertIsNone(report["max_seconds"])
        self.assertTrue(report["within_budget"])
        self.assertEqual(report["requirements"], 1)
        self.assertEqual(report["status"], "ok")

    def test_benchmark_suite_can_enforce_max_seconds_budget(self) -> None:
        suite = {
            "summary": {"cases": 10, "clusters": 2, "records_seen": 10},
            "cases": [{"id": f"case_{index:03d}"} for index in range(10)],
        }

        report = benchmark_suite(suite, timeout_seconds=30, workers=1, max_seconds=120)

        self.assertFalse(report["within_budget"])
        self.assertEqual(report["max_seconds"], 120)
        self.assertEqual(report["recommended_workers_for_budget"], 3)
        self.assertEqual(report["status"], "warn")
        self.assertIn("Set --workers 3", " ".join(report["next_steps"]))

    def test_benchmark_prompt_manifest_aggregates_mapped_suites(self) -> None:
        with TemporaryDirectory() as temp_dir:
            first_suite_path = f"{temp_dir}/triage.redline-suite.json"
            second_suite_path = f"{temp_dir}/refunds.redline-suite.json"
            write_json(
                first_suite_path,
                {
                    "summary": {"cases": 5, "clusters": 2, "records_seen": 11},
                    "cases": [{"id": f"case_{index:03d}"} for index in range(5)],
                    "requirements": {"case_001": [{"include": ["owner"]}]},
                },
            )
            write_json(
                second_suite_path,
                {
                    "summary": {"cases": 4, "clusters": 3, "records_seen": 9},
                    "cases": [{"id": f"case_{index:03d}"} for index in range(4)],
                    "judgments": {"case_002": {"status": "expected"}},
                },
            )
            manifest = {
                "schema": "redline-prompt-manifest-v1",
                "prompts": [
                    {"id": "support/triage", "path": "prompts/support/triage.txt", "suite": first_suite_path},
                    {"id": "billing/refunds", "path": "prompts/billing/refunds.txt", "suite": second_suite_path},
                ],
            }

            report = benchmark_prompt_manifest(
                manifest,
                manifest_path="redline-prompts.json",
                timeout_seconds=10,
                workers=2,
                max_seconds=40,
            )

        self.assertTrue(report["is_prompt_manifest"])
        self.assertEqual(report["manifest"], "redline-prompts.json")
        self.assertEqual(report["prompt_count"], 2)
        self.assertEqual(report["suite_count"], 2)
        self.assertEqual(report["cases"], 9)
        self.assertEqual(report["clusters"], 5)
        self.assertEqual(report["records_seen"], 20)
        self.assertEqual(report["parallel_waves"], 5)
        self.assertEqual(report["worst_case_seconds"], 50)
        self.assertEqual(report["sequential_worst_case_seconds"], 90)
        self.assertFalse(report["within_budget"])
        self.assertEqual(report["recommended_workers_for_budget"], 3)
        self.assertEqual(report["requirements"], 1)
        self.assertEqual(report["judgments"], 1)
        self.assertEqual(len(report["prompt_suites"]), 2)

    def test_benchmark_warns_for_large_single_worker_suite(self) -> None:
        suite = {
            "summary": {"cases": 42, "clusters": 12, "records_seen": 42},
            "cases": [{"id": f"case_{index:03d}"} for index in range(42)],
        }

        report = benchmark_suite(suite, timeout_seconds=30, workers=1)

        self.assertEqual(report["status"], "warn")
        self.assertEqual(report["worst_case_seconds"], 1260)
        self.assertIn("Set workers", report["next_steps"][0])

    def test_format_benchmark_report_is_readable(self) -> None:
        output = format_benchmark_report(_sample_report())

        self.assertIn("redline benchmark", output)
        self.assertIn("Mode:                  static estimate; no replay commands are executed", output)
        self.assertIn("Worst-case eval budget: 5m 30s", output)
        self.assertIn("Sequential budget:     21m 0s", output)
        self.assertIn("Status:                OK", output)
        self.assertIn("Next:", output)

    def test_format_benchmark_markdown_is_summary_ready(self) -> None:
        report = _sample_report()
        report["max_seconds"] = 300
        report["within_budget"] = False
        report["recommended_workers_for_budget"] = 5
        report["status"] = "warn"
        output = format_benchmark_markdown(report)

        self.assertIn("## redline benchmark", output)
        self.assertIn("Static estimate; no replay commands are executed.", output)
        self.assertIn("| Worst-case eval budget | 5m 30s |", output)
        self.assertIn("| Max allowed budget | 5m 0s |", output)
        self.assertIn("| Budget check | FAIL |", output)
        self.assertIn("| Recommended workers | 5 |", output)
        self.assertIn("| Status | WARN |", output)
        self.assertIn("Add requirements to high-value cases.", output)

    def test_format_benchmark_report_includes_prompt_manifest_rows(self) -> None:
        report = _sample_report()
        report["is_prompt_manifest"] = True
        report["prompt_suites"] = [
            {
                "id": "support/triage",
                "path": "prompts/support/triage.txt",
                "suite": "suites/support/triage.redline-suite.json",
                "cases": 3,
                "parallel_waves": 2,
                "worst_case_seconds": 60,
            }
        ]

        text = format_benchmark_report(report)
        markdown = format_benchmark_markdown(report)

        self.assertIn("Prompt manifest", text)
        self.assertIn("Prompt suites:", text)
        self.assertIn("support/triage", text)
        self.assertIn("### Prompt suites", markdown)
        self.assertIn("suites/support/triage.redline-suite.json", markdown)

    def test_benchmark_reports_when_timeout_cannot_fit_budget(self) -> None:
        report = benchmark_suite(
            {"cases": [{"id": "case_001"}]},
            timeout_seconds=30,
            workers=1,
            max_seconds=10,
        )

        self.assertIsNone(report["recommended_workers_for_budget"])
        self.assertIn("even one parallel wave exceeds", " ".join(report["next_steps"]))

    def test_benchmark_rejects_invalid_workers_and_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "workers must be at least 1"):
            benchmark_suite({"cases": []}, workers=0)
        with self.assertRaisesRegex(ValueError, "timeout_seconds must be greater than 0"):
            benchmark_suite({"cases": []}, timeout_seconds=0)
        with self.assertRaisesRegex(ValueError, "max_seconds must be greater than 0"):
            benchmark_suite({"cases": []}, max_seconds=0)


def _sample_report() -> dict[str, Any]:
    return {
        "suite": "suite.json",
        "mode": "static_eval_budget_estimate",
        "cases": 42,
        "clusters": 12,
        "records_seen": 42,
        "workers": 4,
        "timeout_seconds": 30,
        "parallel_waves": 11,
        "worst_case_seconds": 330,
        "sequential_worst_case_seconds": 1260,
        "max_seconds": None,
        "within_budget": True,
        "requirements": 0,
        "judgments": 0,
        "size": "medium",
        "status": "ok",
        "next_steps": ["Add requirements to high-value cases."],
    }


if __name__ == "__main__":
    unittest.main()
