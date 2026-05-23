import unittest

from redline.io import LogRecord
from redline.suite import build_suite


class SuiteTests(unittest.TestCase):
    def test_build_suite_groups_behavioral_clusters(self) -> None:
        records = [
            LogRecord(1, "Return JSON for Ada", '{"name":"Ada"}', {}),
            LogRecord(2, "Return JSON for Bob", '{"name":"Bob"}', {}),
            LogRecord(3, "Summarize in bullets", "- one\n- two", {}),
        ]

        suite = build_suite(
            records,
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        self.assertEqual(suite["summary"]["records_seen"], 3)
        self.assertEqual(suite["summary"]["cases"], 2)
        self.assertEqual(suite["summary"]["clusters"], 2)
        self.assertTrue(all("baseline_response" in case for case in suite["cases"]))


if __name__ == "__main__":
    unittest.main()
