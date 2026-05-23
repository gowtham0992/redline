import unittest

from redline.features import extract_features


class FeatureTests(unittest.TestCase):
    def test_extract_entities_keeps_names_and_acronyms(self) -> None:
        features = extract_features("Route Ada Lovelace to ACME support.")

        self.assertIn("Ada Lovelace", features.entities)
        self.assertIn("ACME", features.entities)
        self.assertNotIn("Route", features.entities)


if __name__ == "__main__":
    unittest.main()
