#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
html2doc 图片本地化单元测试。

运行方式（在 tools/mdtools 目录下）：
    python -m unittest test_html2doc.py

依赖 markdownify / beautifulsoup4，下载逻辑通过 mock _download_image 隔离，
不发真实网络请求。
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import html2doc  # noqa: E402

# 模拟微信公众号文章正文：懒加载图片（data-src + 残留属性）
SAMPLE_HTML = """
<p>正文段落</p>
<img src="https://mmbiz.qpic.cn/mmbiz_jpg/abc123/640?wx_fmt=jpeg"
     data-src="https://mmbiz.qpic.cn/mmbiz_jpg/abc123/640?wx_fmt=jpeg"
     data-type="jpeg" data-ratio="0.66" data-w="1080" title="题图">
<p>结束</p>
"""


class TestLocalizeImages(unittest.TestCase):
    def _config(self, **overrides):
        cfg = {
            "localize_images": True,
            "media_dir": "/tmp/test_media",
            "media_prefix": "./media",
        }
        cfg.update(overrides)
        return cfg

    def test_localize_rewrites_src_to_relative_path(self):
        with mock.patch.object(html2doc, "_download_image", return_value="hash1.jpg") as dl:
            md = html2doc.html_to_markdown(SAMPLE_HTML, self._config())
        self.assertEqual(dl.call_count, 1)
        self.assertIn("./media/hash1.jpg", md)
        # 原始远程 URL 不应再出现
        self.assertNotIn("mmbiz.qpic.cn", md)

    def test_localize_prefers_data_src(self):
        html = '<img data-src="https://mmbiz.qlogo.cn/cover.png" data-ratio="1">'
        with mock.patch.object(
            html2doc, "_download_image", return_value="hash2.png"
        ) as dl:
            md = html2doc.html_to_markdown(html, self._config())
        dl.assert_called_once_with("https://mmbiz.qlogo.cn/cover.png", "/tmp/test_media")
        self.assertIn("./media/hash2.png", md)

    def test_download_failure_keeps_real_url_not_placeholder(self):
        # 微信真实标记：src 是懒加载占位 data-URI，data-src 才是真实图
        html = ('<img src="data:image/svg+xml,placeholder" title="t"'
                ' data-src="https://mmbiz.qpic.cn/real/640?wx_fmt=png">')
        with mock.patch.object(html2doc, "_download_image", return_value=None):
            md = html2doc.html_to_markdown(html, self._config())
        self.assertIn("https://mmbiz.qpic.cn/real/640", md)
        self.assertNotIn("data:image/svg+xml", md)

    def test_media_stats_recorded_into_config(self):
        html = ('<p><img src="https://mmbiz.qpic.cn/a/640?wx_fmt=png"></p>'
                '<p><img src="https://mmbiz.qpic.cn/b/640?wx_fmt=png"></p>')
        cfg = self._config()
        with mock.patch.object(
                html2doc, "_download_image", side_effect=["hash_ok.png", None]):
            html2doc.html_to_markdown(html, cfg)
        self.assertEqual(cfg.get("_media_stats"), {"localized": 1, "failed": 1})

    def test_remove_images_takes_precedence(self):
        with mock.patch.object(html2doc, "_download_image") as dl:
            md = html2doc.html_to_markdown(
                SAMPLE_HTML, self._config(remove_images=True))
        dl.assert_not_called()
        self.assertNotIn("![](./media/", md)

    def test_localize_without_media_dir_is_noop(self):
        md = html2doc.html_to_markdown(SAMPLE_HTML, {"localize_images": True})
        # 未提供 media_dir 时不本地化，保留原 URL
        self.assertIn("https://mmbiz.qpic.cn/mmbiz_jpg/abc123/640", md)

    def test_markdown_file_contains_media_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_path = os.path.join(tmp, "out.md")
            with mock.patch.object(
                html2doc, "_download_image", return_value="hash3.webp"):
                ok = html2doc.html_to_markdown_file(
                    SAMPLE_HTML, md_path, "测试标题", self._config(media_dir=tmp))
            self.assertTrue(ok)
            with open(md_path, encoding="utf-8") as f:
                content = f.read()
        self.assertIn("# 测试标题", content)
        self.assertIn("./media/hash3.webp", content)


class _FakeResponse:
    """模拟 requests.Response，隔离真实网络。"""

    def __init__(self, content=b"img-bytes", url=None, headers=None):
        self.content = content
        self.status_code = 200
        self.url = url  # requests 重定向后的最终 URL
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise html2doc.requests.HTTPError(str(self.status_code))


class TestDownloadImage(unittest.TestCase):
    def test_non_whitelisted_host_returns_none(self):
        # 非微信 CDN 域名直接拒绝，不应发起网络请求
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                html2doc._download_image("https://example.com/a.jpg", tmp))
            # 白名单外的 URL 不会创建任何文件
            self.assertEqual(os.listdir(tmp), [])

    def test_success_writes_file_and_reuses(self):
        url = "https://mmbiz.qpic.cn/abc/640"
        fake = _FakeResponse(url=url, headers={"Content-Type": "image/png"})
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                    html2doc.requests, "get", return_value=fake) as get:
                name1 = html2doc._download_image(url, tmp)
                name2 = html2doc._download_image(url, tmp)
            # 扩展名取自 Content-Type，且第二次命中本地文件不再发请求
            self.assertTrue(name1.endswith(".png"))
            self.assertEqual(name1, name2)
            self.assertEqual(get.call_count, 1)
            # 必须显式带 proxies 参数（走应用代理配置）
            self.assertIn("proxies", get.call_args.kwargs)

    def test_redirect_off_whitelist_discarded(self):
        # 白名单 URL 重定向到站外：字节不入库
        fake = _FakeResponse(url="https://evil.com/payload.png")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(html2doc.requests, "get", return_value=fake):
                self.assertIsNone(
                    html2doc._download_image("https://mmbiz.qpic.cn/a/640", tmp))
            self.assertEqual(os.listdir(tmp), [])


class TestImageExtFromUrl(unittest.TestCase):
    def test_path_extension(self):
        url = "https://mmbiz.qpic.cn/cover.png"
        self.assertEqual(html2doc._image_ext_from_url(url), ".png")

    def test_jpeg_normalized_to_jpg(self):
        self.assertEqual(
            html2doc._image_ext_from_url("https://mmbiz.qpic.cn/a.jpeg"), ".jpg")

    def test_wx_fmt_param(self):
        url = "https://mmbiz.qpic.cn/mmbiz_png/abc/640?wx_fmt=png"
        self.assertEqual(html2doc._image_ext_from_url(url), ".png")
        url = "https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg"
        self.assertEqual(html2doc._image_ext_from_url(url), ".jpg")

    def test_unknown_path_ext_falls_through(self):
        # .aspx 等非图片扩展名不信任，继续用 wx_fmt / Content-Type
        url = "https://mmbiz.qpic.cn/a.aspx?wx_fmt=png"
        self.assertEqual(html2doc._image_ext_from_url(url), ".png")
        url = "https://mmbiz.qpic.cn/a.aspx"
        self.assertEqual(html2doc._image_ext_from_url(url), ".jpg")

    def test_content_type_fallback(self):
        url = "https://mmbiz.qpic.cn/abc/640"
        self.assertEqual(
            html2doc._image_ext_from_url(url, "image/webp; charset=binary"), ".webp")

    def test_default_jpg(self):
        self.assertEqual(html2doc._image_ext_from_url("https://mmbiz.qpic.cn/abc"), ".jpg")


if __name__ == "__main__":
    unittest.main()
