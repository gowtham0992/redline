import unittest

from redline.labels import behavior_label


class LabelsTests(unittest.TestCase):
    def test_behavior_label_expands_known_signature_parts(self) -> None:
        label = behavior_label("structured_json|json|short|json:dict:owner,priority")

        self.assertEqual(
            label,
            "structured JSON prompt -> JSON response (short; JSON dict keys: owner, priority)",
        )

    def test_behavior_label_preserves_unrecognized_short_signature(self) -> None:
        self.assertEqual(behavior_label("custom"), "custom")


if __name__ == "__main__":
    unittest.main()
