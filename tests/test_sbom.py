import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from redline import __version__
from redline.cli import main
from redline.sbom import build_sbom, format_sbom_report


class SbomTests(unittest.TestCase):
    def test_build_sbom_emits_cyclonedx_release_evidence(self) -> None:
        sbom = build_sbom(timestamp="2026-05-25T00:00:00+00:00")

        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.6")
        self.assertEqual(sbom["metadata"]["timestamp"], "2026-05-25T00:00:00+00:00")
        self.assertEqual(sbom["metadata"]["component"]["name"], "redline-ai")
        self.assertEqual(sbom["metadata"]["component"]["version"], __version__)
        properties = {
            item["name"]: item["value"]
            for item in sbom["properties"]
            if isinstance(item, dict)
        }
        self.assertEqual(properties["redline:local_first"], "true")
        self.assertEqual(properties["redline:telemetry"], "none")

    def test_format_sbom_report_is_release_review_friendly(self) -> None:
        output = format_sbom_report(build_sbom(timestamp="2026-05-25T00:00:00+00:00"))

        self.assertIn("redline sbom", output)
        self.assertIn("Format:                CycloneDX 1.6", output)
        self.assertIn(f"Package:               redline-ai {__version__}", output)
        self.assertIn("Telemetry:             none", output)
        self.assertIn("Local-first:           yes", output)

    def test_sbom_cli_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "redline-sbom.json"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["sbom", "--out", str(out)])

            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["bomFormat"], "CycloneDX")
            self.assertIn("Wrote", stdout.getvalue())

    def test_sbom_cli_can_print_json(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            code = main(["sbom", "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["metadata"]["component"]["name"], "redline-ai")


if __name__ == "__main__":
    unittest.main()
