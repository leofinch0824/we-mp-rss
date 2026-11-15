#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML to Markdown Converter Tool

This module provides a tool for converting HTML content to Markdown format.
It uses the markdownify library for conversion with additional preprocessing
and postprocessing to handle special cases.

Usage Examples:
    # 从HTML字符串转换
    from tools.mdtools.html2doc import html_to_markdown
    markdown_content = html_to_markdown(html_content)
    
    # 保存到文件
    html_to_markdown_file(html_content, 'output.md')

Author: AI Assistant
Date: 2025/04/15
"""

import os
import re
import hashlib
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup

try:
    from markdownify import markdownify as md
except ImportError:
    raise ImportError("请安装 markdownify 库: pip install markdownify")


def html_to_markdown(html_content: str, 
                    config: Optional[Dict[str, Any]] = None) -> str:
    """
    将 HTML 内容转换为 Markdown
    
    Args:
        html_content: HTML 内容
        config: 配置选项，支持：
            - heading_style: 标题样式 ("ATX" 或 "underlined")
            - bullets: 列表符号 (默认 "-*+")
            - strip: 要移除的标签列表
            - escape_asterisks: 是否转义星号
            - escape_underscores: 是否转义下划线
            - localize_images: 是否把微信图片下载到本地 media 目录并改写为相对路径引用
            - media_dir: 图片保存目录（localize_images 为 True 时必填）
            - media_prefix: Markdown 中的引用前缀（默认 "./media"）
            - _media_stats:（输出项）本地化统计 {'localized': n, 'failed': n}，
              localize_images 开启时转换结束后回写到调用方传入的 config 字典

    Returns:
        Markdown 内容
    """
    if not html_content:
        return ""

    # 默认配置
    default_config = {
        'heading_style': 'ATX',
        'bullets': '-*+',
        'strip': [],
        'escape_asterisks': False,
        'escape_underscores': False,
        'remove_images': False,
        'remove_links': False,
        'localize_images': False,
        'media_dir': None,
        'media_prefix': './media',
    }
    
    if config:
        default_config.update(config)
    
    try:
        # 预处理 HTML
        processed_html = _preprocess_html(html_content, default_config)
        
        # 转换为 Markdown
        markdown_content = md(
            processed_html,
            heading_style=default_config['heading_style'],
            bullets=default_config['bullets'],
            strip=default_config['strip'],
            escape_asterisks=default_config['escape_asterisks'],
            escape_underscores=default_config['escape_underscores']
        )
        
        # 后处理 Markdown
        markdown_content = _postprocess_markdown(markdown_content)

        # 把本地化统计回写给调用方（见 config 文档中的 _media_stats）
        if isinstance(config, dict) and '_media_stats' in default_config:
            config['_media_stats'] = default_config['_media_stats']

        return markdown_content
        
    except Exception as e:
        print(f"HTML 转 Markdown 失败: {e}")
        return ""


# 仅允许下载微信公众号图片 CDN（与 apis/res.py 反向代理白名单保持一致）
_IMAGE_HOST_WHITELIST = ("mmbiz.qpic.cn", "mmbiz.qlogo.cn", "mmecoa.qpic.cn")

_CONTENT_TYPE_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

# URL 路径里出现的扩展名只信任这些，其余（如 .aspx）继续走 wx_fmt / Content-Type
_KNOWN_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp"}

_proxies_cache: Optional[Dict[str, str]] = None
_proxies_loaded = False


def _get_proxies() -> Optional[Dict[str, str]]:
    """读取应用级代理配置（与 core/wx/base.py 行为一致），供图片下载使用。

    数据中心部署直连微信 CDN 会被封（singbox sidecar 即为此设计），
    这类环境下不走代理的下载必然全部失败。
    """
    global _proxies_cache, _proxies_loaded
    if not _proxies_loaded:
        _proxies_loaded = True
        try:
            from core.config import cfg
            if cfg.get("proxy.enabled", False):
                proxy_url = cfg.get("proxy.http_url", "")
                if proxy_url:
                    _proxies_cache = {"http": proxy_url, "https": proxy_url}
        except Exception:
            _proxies_cache = None
    return _proxies_cache


def _image_ext_from_url(img_url: str, content_type: Optional[str] = None) -> str:
    """从 URL 路径、wx_fmt 参数、Content-Type 依次推断图片扩展名，默认 .jpg。"""
    from urllib.parse import urlparse, parse_qs

    path_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
    if path_ext in _KNOWN_IMAGE_EXTS:
        return ".jpg" if path_ext == ".jpeg" else path_ext

    # 微信 CDN 图片多数没有扩展名，真实格式放在 wx_fmt 查询参数里
    wx_fmt = (parse_qs(urlparse(img_url).query).get("wx_fmt") or [""])[0].lower()
    if wx_fmt:
        if wx_fmt == "jpeg":
            return ".jpg"
        ext = "." + wx_fmt
        if ext in _CONTENT_TYPE_EXT_MAP.values():
            return ext

    if content_type:
        return _CONTENT_TYPE_EXT_MAP.get(
            content_type.split(";")[0].strip().lower(), ".jpg")

    return ".jpg"


def _download_image(img_url: str, media_dir: str) -> Optional[str]:
    """下载图片到 media_dir，文件名取 URL 的 sha256（幂等、跨文章去重）。

    Returns:
        成功返回文件名（不含目录），失败或域名不在白名单返回 None。
    """
    from urllib.parse import urlparse

    try:
        if urlparse(img_url).netloc not in _IMAGE_HOST_WHITELIST:
            return None

        os.makedirs(media_dir, exist_ok=True)
        file_stem = hashlib.sha256(img_url.encode("utf-8")).hexdigest()
        # 命中已下载文件则直接复用（主要发生在同批次导出内；
        # 注意导出打包后源文件会被清理，跨批次复用仅在打包失败时存在）
        for existing in os.listdir(media_dir):
            if existing.startswith(file_stem):
                return existing

        response = requests.get(img_url, timeout=10, proxies=_get_proxies())
        response.raise_for_status()
        if not response.content:
            return None

        # requests 默认跟随重定向，落点可能已离开白名单域名
        if urlparse(response.url).netloc not in _IMAGE_HOST_WHITELIST:
            return None

        ext = _image_ext_from_url(img_url, response.headers.get("Content-Type"))
        file_path = os.path.join(media_dir, file_stem + ext)
        with open(file_path, "wb") as f:
            f.write(response.content)
        return file_stem + ext
    except Exception as e:
        print(f"下载图片失败 {img_url}: {e}")
        return None


def _localize_images(soup, media_dir: str, media_prefix: str) -> tuple:
    """把正文中的微信图片下载到本地，src 改写为相对路径引用。

    下载前先把真实 URL（data-src 优先）提升到 src：微信文章里 src 常是
    懒加载占位图（data-URI），这样下载失败时留下的是原始远程 URL。

    Returns:
        (成功本地化数量, 下载失败数量)。
    """
    localized = 0
    failed = 0
    for img in soup.find_all('img'):
        img_url = img.get('data-src') or img.get('src')
        if not img_url or not img_url.startswith(('http://', 'https://')):
            continue

        img['src'] = img_url

        file_name = _download_image(img_url, media_dir)
        if file_name:
            img['src'] = f"{media_prefix}/{file_name}"
            if 'title' in img.attrs and 'alt' not in img.attrs:
                img['alt'] = img['title']
            # 清理懒加载残留属性，避免与本地化后的 src 不一致
            for attr in ('data-src', 'data-type', 'data-ratio', 'data-w'):
                if img.has_attr(attr):
                    del img[attr]
            localized += 1
        else:
            failed += 1
    return localized, failed


def _preprocess_html(html_content: str, config: Dict[str, Any]) -> str:
    """
    预处理 HTML 内容
    
    Args:
        html_content: 原始 HTML 内容
        config: 配置选项
        
    Returns:
        处理后的 HTML 内容
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除不需要的标签
        for tag in soup.find_all(['span', 'font', 'div']):
            tag.unwrap()
        
        # 移除样式和类属性
        for tag in soup.find_all(True):
            if 'style' in tag.attrs:
                del tag.attrs['style']
            if 'class' in tag.attrs:
                del tag.attrs['class']
            if 'data-pm-slice' in tag.attrs:
                del tag.attrs['data-pm-slice']
            if 'data-title' in tag.attrs:
                del tag.attrs['data-title']
        
        # 处理图片
        if config.get('remove_images', False):
            for img in soup.find_all('img'):
                img.decompose()
        elif config.get('localize_images', False) and config.get('media_dir'):
            # 下载图片到本地 media 目录，引用改写为相对路径
            localized, failed = _localize_images(
                soup,
                media_dir=config['media_dir'],
                media_prefix=config.get('media_prefix', './media'),
            )
            config['_media_stats'] = {'localized': localized, 'failed': failed}
        else:
            # 保留图片的 title 属性作为 alt
            for img in soup.find_all('img'):
                if 'title' in img.attrs and 'alt' not in img.attrs:
                    img['alt'] = img['title']
        
        # 处理链接
        if config.get('remove_links', False):
            for a in soup.find_all('a'):
                a.unwrap()
        
        content = str(soup)
        
        # 替换 p 标签中的换行符
        content = re.sub(
            r'(<p[^>]*>)([\s\S]*?)(</p>)',
            lambda m: m.group(1) + re.sub(r'\n', '', m.group(2)) + m.group(3),
            content
        )
        
        # 清理多余换行
        content = re.sub(r'\n\s*\n\s*\n+', '\n', content)
        
        return content
        
    except Exception as e:
        print(f"HTML 预处理失败: {e}")
        return html_content


def _postprocess_markdown(markdown_content: str) -> str:
    """
    后处理 Markdown 内容
    
    Args:
        markdown_content: 原始 Markdown 内容
        
    Returns:
        处理后的 Markdown 内容
    """
    try:
        # 清理多余换行
        markdown_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', markdown_content)
        
        # 移除多余的星号（可能是转换错误）
        markdown_content = re.sub(r'\*{3,}', '**', markdown_content)
        
        # 确保标题前后有空行
        markdown_content = re.sub(r'([^\n])\n(#{1,6} )', r'\1\n\n\2', markdown_content)
        markdown_content = re.sub(r'(#{1,6} [^\n]+)\n([^\n#])', r'\1\n\n\2', markdown_content)
        
        return markdown_content.strip()
        
    except Exception as e:
        print(f"Markdown 后处理失败: {e}")
        return markdown_content


def html_to_markdown_file(html_content: str, 
                         output_file: str,
                         document_title: Optional[str] = None,
                         config: Optional[Dict[str, Any]] = None) -> bool:
    """
    将 HTML 转换为 Markdown 并保存到文件
    
    Args:
        html_content: HTML 内容
        output_file: 输出的 Markdown 文件路径
        document_title: 文档标题（将添加到文件开头）
        config: 配置选项
        
    Returns:
        是否成功
    """
    try:
        # 转换为 Markdown
        markdown_content = html_to_markdown(html_content, config)
        
        # 添加标题
        if document_title:
            markdown_content = f"# {document_title}\n\n{markdown_content}"
        
        # 保存文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"Markdown 文件已保存: {output_file}")
        return True
        
    except Exception as e:
        print(f"保存 Markdown 文件失败: {e}")
        return False


# 配置预设
DEFAULT_CONFIG = {
    'heading_style': 'ATX',
    'bullets': '-*+',
    'escape_asterisks': False,
    'escape_underscores': False,
}

# 简洁配置（移除图片和链接）
CLEAN_CONFIG = {
    'heading_style': 'ATX',
    'bullets': '-*+',
    'remove_images': True,
    'remove_links': True,
}


if __name__ == '__main__':
    # 测试示例
    test_html = """
    <h1>标题测试</h1>
    <p>这是一个 <strong>粗体</strong> 和 <em>斜体</em> 的示例。</p>
    <h2>列表示例</h2>
    <ul>
        <li>项目 1</li>
        <li>项目 2</li>
    </ul>
    <h2>代码示例</h2>
    <pre><code>def hello_world():
    print("Hello, World!")</code></pre>
    <h2>表格示例</h2>
    <table>
        <tr><th>列1</th><th>列2</th></tr>
        <tr><td>A</td><td>B</td></tr>
    </table>
    """
    
    markdown = html_to_markdown(test_html)
    print("转换结果：")
    print(markdown)
