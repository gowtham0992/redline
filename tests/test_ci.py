import unittest
from pathlib import Path

from redline.ci import default_github_workflow


class CiTests(unittest.TestCase):
    def test_default_github_workflow_runs_eval_with_pr_outputs(self) -> None:
        workflow = default_github_workflow()

        self.assertIn("python -m redline doctor --strict", workflow)
        self.assertIn("python -m redline validate --strict", workflow)
        self.assertIn("python -m redline eval", workflow)
        self.assertIn("--compact", workflow)
        self.assertIn("--github-summary", workflow)
        self.assertIn("--github-annotations", workflow)
        self.assertIn("--out-html .redline/reports/eval.html", workflow)
        self.assertIn('cache: "pip"', workflow)
        self.assertIn('"**/*.jsonl"', workflow)
        self.assertIn('"redline-suite.json"', workflow)
        self.assertIn('"redline-suite.schema.json"', workflow)
        self.assertIn("python -m redline compare", workflow)
        self.assertIn(".redline/reports/eval-before.json", workflow)
        self.assertIn("--out-md .redline/reports/compare.md", workflow)
        self.assertIn("--out-html .redline/reports/compare.html", workflow)
        self.assertIn("--fail-on worse,new", workflow)
        self.assertIn("python -m redline history", workflow)
        self.assertIn('--label "${{ github.sha }}"', workflow)
        self.assertIn(".redline/history.jsonl", workflow)
        self.assertIn("--out-md .redline/history.md", workflow)
        self.assertIn(".redline/history.md", workflow)
        self.assertIn("python -m redline dashboard --out .redline/dashboard.html", workflow)
        self.assertIn(".redline/dashboard.html", workflow)
        self.assertIn("--github-summary", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)

    def test_example_workflow_matches_generated_default(self) -> None:
        workflow = Path("examples/github-action.yml").read_text(encoding="utf-8")

        self.assertEqual(workflow, default_github_workflow())


if __name__ == "__main__":
    unittest.main()
