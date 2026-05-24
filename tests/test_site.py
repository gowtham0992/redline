import unittest
from html.parser import HTMLParser
from pathlib import Path


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "a":
            self.links.append(values.get("href", ""))
        if tag == "img":
            self.images.append((values.get("src", ""), values.get("alt", "")))
        if tag == "link" and values.get("rel") == "stylesheet":
            self.stylesheets.append(values.get("href", ""))


class GitHubPagesSiteTests(unittest.TestCase):
    def test_site_homepage_has_launch_copy_and_product_paths(self) -> None:
        html = Path("site/index.html").read_text(encoding="utf-8")

        self.assertIn("<h1>redline</h1>", html)
        self.assertIn("redline demo --compact", html)
        self.assertIn("redline eval --prompt prompts/v2.txt", html)
        self.assertIn("No cloud", html)
        self.assertIn("Optional judges", html)
        self.assertIn("GitHub Pages", Path(".github/workflows/pages.yml").read_text(encoding="utf-8"))

    def test_site_links_stylesheet_and_preview_image(self) -> None:
        parser = _SiteParser()
        parser.feed(Path("site/index.html").read_text(encoding="utf-8"))

        self.assertIn("styles.css", parser.stylesheets)
        self.assertIn("https://github.com/gowtham0992/redline", parser.links)
        self.assertIn(
            ("assets/redline-preview.png", "redline terminal and dashboard preview showing four prompt regressions caught"),
            parser.images,
        )

    def test_preview_image_is_committed_png_asset(self) -> None:
        image = Path("site/assets/redline-preview.png")

        self.assertTrue(image.exists())
        self.assertGreater(image.stat().st_size, 20_000)
        self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_site_css_uses_responsive_static_layout(self) -> None:
        css = Path("site/styles.css").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn("grid-template-columns", css)
        self.assertIn("border-radius: 8px", css)
        self.assertNotIn("letter-spacing: -", css)
        self.assertNotIn("font-size: clamp(", css)

    def test_pages_workflow_deploys_site_directory_from_develop(self) -> None:
        workflow = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")

        self.assertIn("- develop", workflow)
        self.assertIn("actions/upload-pages-artifact@v3", workflow)
        self.assertIn("path: site", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)


if __name__ == "__main__":
    unittest.main()
