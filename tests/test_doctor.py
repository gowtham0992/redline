import unittest

from redline.doctor import doctor_report, format_doctor_report


class DoctorTests(unittest.TestCase):
    def test_doctor_report_warns_for_missing_config_and_suite(self) -> None:
        report = doctor_report(
            config_path="missing.json",
            config={},
            suite=None,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["warnings"], 3)

    def test_doctor_report_errors_for_unreadable_suite(self) -> None:
        report = doctor_report(
            config_path="redline.json",
            config={"suite": ".redline/suite.json"},
            suite=None,
            suite_error="invalid JSON",
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["errors"], 1)

    def test_format_doctor_report_is_readable(self) -> None:
        report = doctor_report(
            config_path="redline.json",
            config={"replay": "python runner.py"},
            suite={"cases": [{}, {}]},
        )

        output = format_doctor_report(report)

        self.assertIn("redline doctor", output)
        self.assertIn("suite: found", output)
        self.assertIn("replay: configured", output)


if __name__ == "__main__":
    unittest.main()
