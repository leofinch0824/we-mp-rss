"""同目录 export_article.py 的离线回归测试（仅标准库，不需要服务/网络）。

覆盖 code review 确认过的缺陷点：
- 长链 sn 提取（/s?__biz=...&sn=...）
- 按文章 id 取元数据（不再依赖最新列表窗口）
- 坏 zip 转为 PipelineError（不裸抛 BadZipFile）
- index.json 损坏时备份+从 meta.json 重建（不静默丢历史）、原子写、同 id 去重

运行：在本文件所在目录执行 python3 -m unittest test_export_article
"""
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export_article as ea  # noqa: E402


def make_zip(path: Path, md_body: bytes = b"# title\n\n![x](./media/a.png)\n", media=("a.png",)):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("20260101_demo.md", md_body)
        for m in media:
            zf.writestr(f"media/{m}", b"IMGDATA")


class ExtractSnTest(TestCase):
    def test_short_path_form(self):
        self.assertEqual(ea.extract_sn("https://mp.weixin.qq.com/s/1Ng31oZZbMYSW0OOSZIsAA"), "1Ng31oZZbMYSW0OOSZIsAA")

    def test_long_query_form(self):
        self.assertEqual(
            ea.extract_sn("https://mp.weixin.qq.com/s?__biz=MzI1NQ==&mid=1&idx=1&sn=AbC_123-x&chksm=zz#rd"),
            "AbC_123-x",
        )

    def test_not_wechat(self):
        self.assertEqual(ea.extract_sn("https://example.com/a"), "")


class _FakeApi:
    def __init__(self, detail_response):
        self.detail_response = detail_response
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        return self.detail_response


class FindArticleMetaTest(TestCase):
    def test_uses_article_detail_endpoint(self):
        api = _FakeApi({"data": {"id": "FEATURED_ARTICLES-x", "publish_time": 1794494820, "title": "t"}})
        meta = ea.find_article_meta(api, "FEATURED_ARTICLES-x")
        self.assertEqual(meta["publish_time"], 1794494820)
        self.assertEqual(api.calls[0], "/articles/FEATURED_ARTICLES-x")

    def test_malformed_detail_returns_empty(self):
        self.assertEqual(ea.find_article_meta(_FakeApi({"data": None}), "x"), {})
        self.assertEqual(ea.find_article_meta(_FakeApi(None), "x"), {})


class PlaceArticleTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out_root = Path(self.tmp.name) / "articles"

    def tearDown(self):
        self.tmp.cleanup()

    def _zip(self):
        z = Path(self.tmp.name) / "demo.zip"
        make_zip(z)
        return z

    def test_dated_dir_from_publish_time(self):
        article = {"publish_time": 1794494820, "title": "T", "mp_name": "mp"}  # 2026-11-12
        meta = ea.place_article(self._zip(), "1Ng31oZZbMYSW0OOSZIsAA", "u", article, self.out_root)
        self.assertEqual(meta["id"], "20261112-1Ng31oZZbMYSW0OOSZIsAA")
        self.assertTrue((self.out_root / meta["id"] / "article.md").exists())
        self.assertTrue((self.out_root / meta["id"] / "media" / "a.png").exists())
        self.assertEqual(meta["images"], 1)

    def test_fallback_dir_without_sn(self):
        meta = ea.place_article(self._zip(), "", "u", {"title": "T"}, self.out_root)
        self.assertTrue(meta["id"].startswith("local-"))

    def test_bad_zip_raises_pipeline_error(self):
        bad = Path(self.tmp.name) / "bad.zip"
        bad.write_bytes(b"not a zip at all")
        with self.assertRaises(ea.PipelineError):
            ea.place_article(bad, "sn1", "u", {"title": "T"}, self.out_root)

    def test_truncated_zip_raises_pipeline_error(self):
        z = Path(self.tmp.name) / "ok.zip"
        make_zip(z)
        data = z.read_bytes()
        z.write_bytes(data[: len(data) // 2])
        with self.assertRaises(ea.PipelineError):
            ea.place_article(z, "sn1", "u", {"title": "T"}, self.out_root)


class UpdateIndexTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_article_dir(self, dir_name, title, publish_time):
        d = self.root / dir_name
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "id": dir_name, "title": title, "url": "u", "publish_time": publish_time,
            "exported_at": "2026-11-15T00:00:00", "images": 1,
        }), encoding="utf-8")

    def test_dedup_same_id(self):
        self._write_article_dir("20261112-snA", "A", 100)
        ea.update_index(self.root, {"id": "20261112-snA", "title": "A2", "url": "u",
                                    "publish_time": 100, "exported_at": "2026-11-16T00:00:00", "images": 2})
        entries = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "A2")

    def test_corrupt_index_backed_up_and_rebuilt(self):
        self._write_article_dir("20261112-snA", "A", 100)
        self._write_article_dir("20261111-snB", "B", 50)
        (self.root / "index.json").write_text("{ truncated json", encoding="utf-8")
        ea.update_index(self.root, {"id": "20261113-snC", "title": "C", "url": "u",
                                    "publish_time": 200, "exported_at": "2026-11-15T00:00:00", "images": 3})
        backups = list(self.root.glob("index.corrupt-*.json"))
        self.assertEqual(len(backups), 1, "损坏索引应被备份而非直接覆盖")
        entries = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        ids = {e["id"] for e in entries}
        self.assertEqual(ids, {"20261112-snA", "20261111-snB", "20261113-snC"}, "重建应保留全部历史文章")

    def test_atomic_write_no_tmp_left(self):
        ea.update_index(self.root, {"id": "x", "title": "t", "url": "u", "publish_time": 1,
                                    "exported_at": "2026-11-15T00:00:00", "images": 0})
        self.assertFalse((self.root / "index.json.tmp").exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
