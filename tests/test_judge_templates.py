import os
import tempfile
import unittest
from pathlib import Path

from redline.judge_templates import (
    copy_all_judge_templates,
    copy_judge_template,
    format_judge_templates,
    judge_templates,
)


class JudgeTemplateTests(unittest.TestCase):
    def test_judge_templates_list_core_set(self) -> None:
        templates = judge_templates()
        ids = {template["id"] for template in templates}

        self.assertIn("local", ids)
        self.assertIn("openai", ids)
        self.assertIn("anthropic", ids)
        self.assertIn("litellm", ids)
        self.assertIn("support-rubric", ids)
        self.assertIn("extraction-rubric", ids)
        self.assertIn("safety-rubric", ids)

    def test_format_judge_templates_prints_commands_and_rubrics(self) -> None:
        output = format_judge_templates()

        self.assertIn("redline judges", output)
        self.assertIn("Judges are optional", output)
        self.assertIn("OpenAI judge", output)
        self.assertIn("./judges/openai_judge.sh", output)
        self.assertIn("Support-agent rubric", output)
        self.assertIn("REDLINE_JUDGE_RUBRIC=judges/support_rubric.md", output)

    def test_packaged_judge_templates_match_repo_examples(self) -> None:
        pairs = {
            "judge_changed.py": Path("examples/judge_changed.py"),
            "openai_judge.sh": Path("examples/openai_judge.sh"),
            "anthropic_judge.sh": Path("examples/anthropic_judge.sh"),
            "litellm_judge.sh": Path("examples/litellm_judge.sh"),
            "support_rubric.md": Path("examples/judges/support_rubric.md"),
            "extraction_rubric.md": Path("examples/judges/extraction_rubric.md"),
            "safety_rubric.md": Path("examples/judges/safety_rubric.md"),
        }

        for template_name, repo_file in pairs.items():
            with self.subTest(template=template_name):
                template_file = Path("redline") / "judge_template_files" / template_name
                self.assertEqual(
                    template_file.read_text(encoding="utf-8"),
                    repo_file.read_text(encoding="utf-8"),
                )

    def test_copy_model_judge_template_writes_executable_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "judges" / "openai_judge.sh"

            result = copy_judge_template("openai", output=str(output))

            self.assertEqual(result["id"], "openai")
            self.assertEqual(result["path"], str(output))
            self.assertIn("OPENAI_API_KEY", result["setup"])
            self.assertIn("redline init --judge", result["next"])
            self.assertTrue(output.exists())
            self.assertIn("OPENAI_API_KEY", output.read_text(encoding="utf-8"))
            self.assertTrue(output.stat().st_mode & 0o111)

    def test_copy_local_judge_template_returns_python_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "judge_changed.py"

            result = copy_judge_template("local", output=str(output))

            self.assertEqual(result["kind"], "judge")
            self.assertEqual(result["command"], f"python {output}")
            self.assertIn("redline init --judge", result["next"])
            self.assertTrue(output.stat().st_mode & 0o111)

    def test_copy_rubric_template_returns_rubric_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "support.md"

            result = copy_judge_template("support-rubric", output=str(output))

            self.assertEqual(result["kind"], "rubric")
            self.assertEqual(result["command"], "")
            self.assertIn("REDLINE_JUDGE_RUBRIC", result["next"])
            self.assertIn("redline diff", result["next"])
            self.assertIn("Regression", output.read_text(encoding="utf-8"))

    def test_copy_judge_template_refuses_existing_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "openai_judge.sh"
            output.write_text("existing\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "already exists"):
                copy_judge_template("openai", output=str(output))

    def test_copy_all_judge_templates_writes_each_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                results = copy_all_judge_templates()

                self.assertEqual(len(results), len(judge_templates()))
                for template in judge_templates():
                    self.assertTrue(Path(template["file"]).exists())
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
