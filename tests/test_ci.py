import unittest

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
        self.assertIn('cache: "pip"', workflow)
        self.assertIn('"**/*.jsonl"', workflow)
        self.assertIn('"redline-suite.json"', workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)


if __name__ == "__main__":
    unittest.main()
