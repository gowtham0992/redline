import unittest

from redline.benchmark import benchmark_suite, format_benchmark_report
from redline.io import LogRecord
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
        self.assertEqual(report["clusters"], 3)
        self.assertEqual(report["parallel_waves"], 2)
        self.assertEqual(report["worst_case_seconds"], 60)
        self.assertEqual(report["sequential_worst_case_seconds"], 90)
        self.assertEqual(report["requirements"], 1)
        self.assertEqual(report["status"], "ok")

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
        output = format_benchmark_report(
            {
                "suite": "suite.json",
                "cases": 42,
                "clusters": 12,
                "records_seen": 42,
                "workers": 4,
                "timeout_seconds": 30,
                "parallel_waves": 11,
                "worst_case_seconds": 330,
                "sequential_worst_case_seconds": 1260,
                "requirements": 0,
                "judgments": 0,
                "size": "medium",
                "status": "ok",
                "next_steps": ["Add requirements to high-value cases."],
            }
        )

        self.assertIn("redline benchmark", output)
        self.assertIn("Worst-case eval budget: 5m 30s", output)
        self.assertIn("Sequential budget:     21m 0s", output)
        self.assertIn("Status:                OK", output)
        self.assertIn("Next:", output)

    def test_benchmark_rejects_invalid_workers_and_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "workers must be at least 1"):
            benchmark_suite({"cases": []}, workers=0)
        with self.assertRaisesRegex(ValueError, "timeout_seconds must be greater than 0"):
            benchmark_suite({"cases": []}, timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
