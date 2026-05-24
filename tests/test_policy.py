import unittest

from redline.policy import DEFAULT_FAIL_ON, parse_fail_on, should_fail


class PolicyTests(unittest.TestCase):
    def test_parse_default_fail_on(self) -> None:
        self.assertEqual(parse_fail_on(None), DEFAULT_FAIL_ON)
        self.assertEqual(parse_fail_on(""), DEFAULT_FAIL_ON)

    def test_parse_none_disables_failures(self) -> None:
        self.assertEqual(parse_fail_on("none"), ())

    def test_parse_custom_statuses(self) -> None:
        self.assertEqual(parse_fail_on("regression, changed"), ("regression", "changed"))

    def test_parse_invalid_status_fails(self) -> None:
        with self.assertRaises(ValueError):
            parse_fail_on("bad")

    def test_should_fail_uses_selected_statuses(self) -> None:
        result = {"summary": {"regression": 0, "changed": 1}}

        self.assertFalse(should_fail(result, ("regression",)))
        self.assertTrue(should_fail(result, ("changed",)))


if __name__ == "__main__":
    unittest.main()
