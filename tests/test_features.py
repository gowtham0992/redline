import unittest

from redline.features import extract_features


class FeatureTests(unittest.TestCase):
    def test_extract_entities_keeps_names_and_acronyms(self) -> None:
        features = extract_features("Route Ada Lovelace to ACME support.")

        self.assertIn("Ada Lovelace", features.entities)
        self.assertIn("ACME", features.entities)
        self.assertNotIn("Route", features.entities)

    def test_extract_urls(self) -> None:
        features = extract_features("Read https://example.com/docs for details.")

        self.assertEqual(features.url_count, 1)
        self.assertEqual(features.urls, ("https://example.com/docs",))


if __name__ == "__main__":
    unittest.main()
