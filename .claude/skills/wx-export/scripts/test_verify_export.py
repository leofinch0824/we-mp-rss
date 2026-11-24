"""导出目录校验的离线回归测试。"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase


class VerifyExportTest(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def article(self, name, markdown="# Title\n"):
        path = self.root / name
        path.mkdir()
        (path / "meta.json").write_text(json.dumps({"id": name}), encoding="utf-8")
        if markdown is not None:
            (path / "article.md").write_text(markdown, encoding="utf-8")
        return path

    def verify(self, path=None):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("verify_export.py")), str(path or self.root)],
            capture_output=True, text=True,
        )
        return proc.returncode, json.loads(proc.stdout)["articles"]

    def test_root_reports_missing_markdown_alongside_valid_article(self):
        self.article("a")
        self.article("b", None)
        status, articles = self.verify()
        self.assertEqual(status, 1)
        self.assertEqual([a["ok"] for a in articles], [True, False])
        self.assertFalse(articles[1]["md"])

    def test_invalid_metadata_does_not_abort_other_articles(self):
        (self.article("a") / "meta.json").write_bytes(b"\xff")
        (self.article("b") / "meta.json").write_text("{}", encoding="utf-8")
        self.article("c")
        status, articles = self.verify()
        self.assertEqual(status, 1)
        self.assertEqual([a["meta"] for a in articles], [False, False, True])
        self.assertIn("meta_error", articles[0])

    def test_generated_code_examples_are_not_image_references(self):
        path = self.article("a", "```md\n![code](code.png)\n```\n\n`![code](inline.png)`\n\n![a](./media/p.png)")
        (path / "media").mkdir()
        (path / "media/p.png").touch()
        status, articles = self.verify(path)
        self.assertEqual(status, 0)
        self.assertEqual(articles[0]["orphans"], [])

    def test_wrong_directory_and_remote_image_fail(self):
        path = self.article("a", "![a](./wrong/p.png)\n![b](https://example.invalid/p.png)")
        (path / "media").mkdir()
        (path / "media/p.png").touch()
        status, articles = self.verify(path)
        self.assertEqual(status, 1)
        self.assertEqual(articles[0]["missing"], ["./wrong/p.png"])
        self.assertEqual(articles[0]["remote_images"], ["https://example.invalid/p.png"])
