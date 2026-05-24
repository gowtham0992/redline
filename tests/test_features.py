import unittest

from redline.features import extract_features


class FeatureTests(unittest.TestCase):
    def test_extract_entities_keeps_names_and_acronyms(self) -> None:
        features = extract_features("Ada owns ACME support. Route Ada Lovelace to ACME support.")

        self.assertIn("Ada", features.entities)
        self.assertIn("Ada Lovelace", features.entities)
        self.assertIn("ACME", features.entities)
        self.assertNotIn("Route", features.entities)

    def test_extract_entities_ignores_sentence_starters_and_common_title_words(self) -> None:
        features = extract_features("The customer should read Docs before opening a Ticket.")

        self.assertNotIn("The", features.entities)
        self.assertNotIn("Docs", features.entities)
        self.assertNotIn("Ticket", features.entities)

    def test_extract_entities_ignores_common_table_headers(self) -> None:
        features = extract_features(
            "| Impact | Status | Owner | Next update |\n"
            "| --- | --- | --- | --- |\n"
            "| Search delayed | Mitigated | Search Platform | 09:30 UTC |"
        )

        self.assertNotIn("Impact", features.entities)
        self.assertNotIn("Owner", features.entities)
        self.assertNotIn("Next", features.entities)
        self.assertIn("Search Platform", features.entities)

    def test_extract_urls(self) -> None:
        features = extract_features("Read https://example.com/docs for details.")

        self.assertEqual(features.url_count, 1)
        self.assertEqual(features.urls, ("https://example.com/docs",))

    def test_extract_numbers_keeps_common_operational_formats(self) -> None:
        features = extract_features("ARR is $82,000, errors rose to 7%, and status is due at 09:30 UTC.")

        self.assertIn("82,000", features.numbers)
        self.assertIn("7%", features.numbers)
        self.assertIn("09:30", features.numbers)
        self.assertNotIn("000", features.numbers)

    def test_refusal_detection_ignores_supportive_apologies(self) -> None:
        features = extract_features("I'm sorry you're experiencing this. Try resetting your password.")

        self.assertFalse(features.refusal)
        self.assertEqual(features.shape, "prose")

    def test_refusal_detection_keeps_action_refusals(self) -> None:
        features = extract_features("Sorry, but I can't provide that information.")

        self.assertTrue(features.refusal)
        self.assertEqual(features.shape, "refusal")

    def test_refusal_detection_ignores_quoted_examples(self) -> None:
        features = extract_features(
            "Detect refusals with examples such as `I cannot fulfill` or `I am unable to help`."
        )

        self.assertFalse(features.refusal)
        self.assertEqual(features.shape, "prose")

    def test_refusal_detection_ignores_context_disclaimers(self) -> None:
        features = extract_features("I don't have enough context to answer confidently.")

        self.assertFalse(features.refusal)


if __name__ == "__main__":
    unittest.main()
