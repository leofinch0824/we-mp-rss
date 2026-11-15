#!/usr/bin/env python3
"""微信公众号文章导出流水线（API 模式）

给定一个/多个 mp.weixin.qq.com 文章链接，通过本地 we-mp-rss 服务完成：
抓取入库 → Markdown 导出（图片本地化）→ 下载解包 → 按唯一 ID 落盘。

落盘布局（每篇文章独立目录，单篇自包含、可整体拷走）：

    downloads/articles/
    ├── 20261112-1Ng31oZZbMYSW0OOSZIsAA/   # <发布日期>-<文章sn>
    │   ├── article.md                      # 正文，图片引用 ./media/...
    │   ├── meta.json                       # 标题/URL/公众号/时间/统计
    │   └── media/                          # 图片，sha256 命名
    └── index.json                          # 追加式索引，按 id 去重更新

唯一性设计：目录名由「文章发布日期 + 微信侧永久 sn」组成。
sn（/s/ 后那段）由微信生成、全局唯一且不变，因此：
- 同名标题/转载文章不会互相覆盖
- 同一文章重复导出 = 原地刷新（幂等），不产生副本
- 标题不参与文件名（标题可重复、含非法字符），检索走 index.json

仅依赖标准库。用法示例：

    python3 scripts/export_article.py --url https://mp.weixin.qq.com/s/xxxx
    python3 scripts/export_article.py --url A --url B --out /path/to/dir

凭据默认 admin/admin@123，可用 --user/--password 或环境变量 WEMPRSS_USER/WEMPRSS_PASS 覆盖。
"""
import argparse
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

FEATURED_MP_ID = "MP_WXS_FEATURED_ARTICLES"
DEFAULT_BASE = "http://127.0.0.1:8001/api/v1/wx"
REPO_ROOT = Path(__file__).resolve().parent.parent
POLL_INTERVAL = 2


class PipelineError(Exception):
    """流水线失败，message 可直接展示给用户"""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Api:
    """we-mp-rss REST 客户端（仅用到的几个端点）"""

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token = ""

    def _request(self, method: str, path: str, body=None, form=None, stream_to=None):
        url = f"{self.base}{path}"
        data = None
        headers = {}
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if stream_to is not None:
                    return shutil.copyfileobj(resp, stream_to)
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            # 后端错误统一在 detail 里带 message
            try:
                detail = json.loads(e.read().decode())
                msg = detail.get("detail", {}).get("message") or detail.get("message") or str(detail)
            except Exception:
                msg = e.reason
            raise PipelineError(f"HTTP {e.code} {path}: {msg}") from e
        except urllib.error.URLError as e:
            raise PipelineError(
                f"无法连接 {self.base}（服务未启动？docker compose -f compose/docker-compose.dev.yaml up -d）"
            ) from e
        except (OSError, http.client.HTTPException) as e:
            # 连接中断/响应中断（如服务正在重启）
            raise PipelineError(
                f"连接 {self.base} 中断（{type(e).__name__}: {e}），服务可能正在重启，稍后重试"
            ) from e

    def login(self, user: str, password: str) -> None:
        r = self._request("POST", "/auth/login", form={"username": user, "password": password})
        data = r.get("data") or {}
        if not data.get("access_token"):
            raise PipelineError(f"登录失败: {r.get('message')}")
        self.token = data["access_token"]

    def check_auth(self) -> bool:
        """检查微信公众号授权是否过期（/sys/info 的 wx.login，注意路由前缀是 /sys）"""
        try:
            r = self.get_json("/sys/info")
            wx = ((r or {}).get("data") or {}).get("wx") or {}
            return bool(wx.get("login"))
        except PipelineError:
            raise
        except Exception:
            # 状态接口异常不阻断导出，让后续抓取阶段暴露真实错误
            return True

    def post_json(self, path: str, body):
        return self._request("POST", path, body=body)

    def get_json(self, path: str):
        return self._request("GET", path)


def extract_sn(url: str) -> str:
    """提取微信文章永久标识 sn：优先 /s/<sn> 路径，其次 sn= 查询参数"""
    m = re.search(r"/s/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]sn=([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    return ""


def poll(fn, done, timeout: int, what: str):
    """轮询直到 done(结果) 为真；超时抛 PipelineError"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = fn()
        state = done(r)
        if state is not None:
            return state
        time.sleep(POLL_INTERVAL)
    raise PipelineError(f"等待{what}超时（{timeout}s）")


def submit_and_wait(api: Api, url: str, timeout: int) -> dict:
    """提交精选文章抓取任务并等待完成，返回任务结果（含文章 id/title）"""
    r = api.post_json("/mps/featured/article", {"url": url})
    task_id = (r.get("data") or {}).get("task_id")
    if not task_id:
        raise PipelineError(f"提交抓取任务失败: {r.get('message')}")

    def check():
        t = api.get_json(f"/mps/featured/article/tasks/{task_id}").get("data") or {}
        if t.get("status") == "success":
            return t
        if t.get("status") in ("failed", "error"):
            raise PipelineError(f"抓取失败: {t.get('message')}")
        return None

    return poll(check, lambda x: x, timeout, "文章抓取")


def find_article_meta(api: Api, article_id: str) -> dict:
    """按 id 取文章详情（含发布时间）。

    不走列表接口：列表按发布时间倒序取最新 N 条，导出老文章会拿不到
    元数据、退化成无日期目录名，重复导出还会产生跨天副本。
    """
    r = api.get_json(f"/articles/{urllib.parse.quote(article_id, safe='')}")
    row = (r or {}).get("data")
    return row if isinstance(row, dict) and row.get("id") else {}


def export_and_wait(api: Api, doc_id: str, timeout: int) -> str:
    """触发 Markdown+图片本地化导出，完成后返回导出 zip 文件名"""
    req = {
        "mp_id": FEATURED_MP_ID,
        "doc_id": [doc_id],
        "page_size": 10,
        "page_count": 1,
        "add_title": True,
        "remove_images": False,
        "remove_links": False,
        "localize_images": True,
        "export_md": True,
        "export_pdf": False,
        "export_docx": False,
        "export_json": False,
        "export_csv": False,
    }
    r = api.post_json("/tools/export/articles", req)
    job_id = (r.get("data") or {}).get("job_id")
    if not job_id:
        raise PipelineError(f"提交导出任务失败: {r.get('message')}")

    def check():
        j = api.get_json(f"/tools/export/status?job_id={job_id}").get("data") or {}
        if j.get("ok") is True:
            return os.path.basename(j.get("output_path") or "")
        if j.get("ok") is False:
            raise PipelineError(f"导出失败: {j.get('message')}")
        return None

    filename = poll(check, lambda x: x, timeout, "导出任务")
    if not filename:
        raise PipelineError("导出完成但未返回文件名")
    return filename


def download_zip(api: Api, filename: str, tmp_dir: Path) -> Path:
    """下载导出 zip 到调用方持有的临时目录（目录生命周期由调用方管理）"""
    path = tmp_dir / filename
    with open(path, "wb") as f:
        api._request("GET", f"/tools/export/download?mp_id={FEATURED_MP_ID}&filename={urllib.parse.quote(filename)}"
                     f"&delete_after_download=true",  # 下载完成即清理服务端 zip
                     stream_to=f)
    if path.stat().st_size < 100:
        raise PipelineError("下载的导出包异常（过小）")
    return path


def place_article(zip_path: Path, sn: str, url: str, article: dict, out_root: Path) -> dict:
    """解包并按 <发布日期>-<sn>/ 布局落盘，写 meta.json 与索引，返回摘要"""
    extract_dir = zip_path.parent / "unpacked"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    except (zipfile.BadZipFile, RuntimeError, OSError) as e:
        # 坏包/半截包（如下载中断）转为用户可读错误，不裸抛栈
        raise PipelineError(f"导出包解析失败（{type(e).__name__}），可能下载不完整，请重试") from e

    md_files = [p for p in extract_dir.glob("*.md")]
    if not md_files:
        raise PipelineError("导出包内未找到 Markdown 文件")
    md_file = max(md_files, key=lambda p: p.stat().st_size)

    publish_ts = article.get("publish_time")
    try:
        publish_ts = int(publish_ts) if publish_ts else 0
    except (TypeError, ValueError):
        publish_ts = 0
    date_prefix = (
        datetime.fromtimestamp(publish_ts).strftime("%Y%m%d") if publish_ts > 0
        else datetime.now().strftime("%Y%m%d")
    )
    fallback = f"local-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    dir_name = f"{date_prefix}-{sn}" if sn else fallback
    target = out_root / dir_name
    (target / "media").mkdir(parents=True, exist_ok=True)

    shutil.copyfile(md_file, target / "article.md")

    src_media = extract_dir / "media"
    images = 0
    media_bytes = 0
    if src_media.is_dir():
        for img in sorted(src_media.iterdir()):
            if not img.is_file():
                continue
            images += 1
            media_bytes += img.stat().st_size
            shutil.copyfile(img, target / "media" / img.name)

    exported_at = datetime.now().isoformat(timespec="seconds")
    meta = {
        "id": dir_name,
        "sn": sn,
        "title": article.get("title") or "",
        "url": url,
        "mp_name": article.get("mp_name") or "精选文章",
        "publish_time": publish_ts or None,
        "exported_at": exported_at,
        "images": images,
        "media_bytes": media_bytes,
        "md_bytes": (target / "article.md").stat().st_size,
    }
    (target / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    update_index(out_root, meta)

    return meta


def _rebuild_index(out_root: Path) -> list:
    """index.json 损坏时的兜底：从各文章目录的 meta.json 重建索引"""
    entries = []
    for meta_file in sorted(out_root.glob("*/meta.json")):
        try:
            m = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entries.append({
            "id": m.get("id") or meta_file.parent.name, "title": m.get("title", ""),
            "url": m.get("url", ""), "publish_time": m.get("publish_time"),
            "exported_at": m.get("exported_at", ""), "images": m.get("images", 0),
            "path": meta_file.parent.name,
        })
    return entries


def update_index(out_root: Path, meta: dict) -> None:
    """追加式索引：同 id 覆盖更新，保持时间倒序。

    索引损坏时不静默丢弃：先备份再从 meta.json 重建；写入用临时文件+原子替换，
    避免中断留下半截 index.json。
    """
    index_path = out_root / "index.json"
    entries = []
    if index_path.exists():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = loaded
        except (json.JSONDecodeError, OSError):
            backup = out_root / f"index.corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            try:
                os.replace(index_path, backup)
                log(f"警告: index.json 无法解析，已备份为 {backup.name}，将从 meta.json 重建索引")
            except OSError:
                pass
            entries = _rebuild_index(out_root)
    entries = [e for e in entries if e.get("id") != meta["id"]]
    entries.append({
        "id": meta["id"], "title": meta["title"], "url": meta["url"],
        "publish_time": meta["publish_time"], "exported_at": meta["exported_at"],
        "images": meta["images"], "path": meta["id"],
    })
    entries.sort(key=lambda e: (e.get("publish_time") or 0, e.get("exported_at") or ""), reverse=True)
    tmp = index_path.with_name("index.json.tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, index_path)


def export_one(api: Api, url: str, out_root: Path, timeout: int) -> dict:
    sn = extract_sn(url)
    log(f"[{url}] sn={sn or '<未识别，将用时间戳兜底>'}")

    task = submit_and_wait(api, url, timeout)
    article_id = task.get("id") or ""
    log(f"[{url}] 抓取完成: {task.get('title')} (id={article_id}, created={task.get('created')})")
    if not article_id:
        raise PipelineError("抓取完成但未返回文章 id")

    article = find_article_meta(api, article_id) or {}
    if not article.get("title"):
        article.setdefault("title", task.get("title") or "")

    existed = None
    if sn:
        date_prefix = datetime.now().strftime("%Y%m%d")
        publish_ts = article.get("publish_time")
        try:
            if publish_ts:
                date_prefix = datetime.fromtimestamp(int(publish_ts)).strftime("%Y%m%d")
        except (TypeError, ValueError):
            pass
        cand = out_root / f"{date_prefix}-{sn}"
        if cand.exists():
            existed = cand.name

    filename = export_and_wait(api, article_id, timeout)
    log(f"[{url}] 导出完成: {filename}")

    # 临时目录由本函数持有：成功失败都清理，不留半截 zip/解包残留
    tmp_dir = Path(tempfile.mkdtemp(prefix="wemprss_export_"))
    try:
        zip_path = download_zip(api, filename, tmp_dir)
        meta = place_article(zip_path, sn, url, article, out_root)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    meta["updated"] = bool(existed)
    log(f"[{url}] 落盘: {meta['id']}/ 图片 {meta['images']} 张"
        f"{'（覆盖旧导出）' if meta['updated'] else ''}")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="导出微信公众号文章为 Markdown（图片本地化）")
    parser.add_argument("--url", action="append", required=True, help="文章链接，可重复传多个")
    parser.add_argument("--out", default=str(REPO_ROOT / "downloads" / "articles"), help="输出根目录")
    parser.add_argument("--base", default=DEFAULT_BASE, help="API 基地址")
    parser.add_argument("--user", default=os.environ.get("WEMPRSS_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("WEMPRSS_PASS", "admin@123"))
    parser.add_argument("--timeout", type=int, default=300, help="单阶段轮询超时秒数")
    args = parser.parse_args()

    out_root = Path(args.out).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    ok = True
    try:
        api = Api(args.base)
        api.login(args.user, args.password)
        log(f"已登录 {args.base}，输出目录: {out_root}")
        if not api.check_auth():
            raise PipelineError(
                "微信公众号授权已过期（无可用会话），自动刷新未启用。"
                "请打开 http://127.0.0.1:5173 扫码重新授权后再导出。"
            )
        for url in args.url:
            try:
                results.append(export_one(api, url.strip(), out_root, args.timeout))
            except PipelineError as e:
                ok = False
                results.append({"ok": False, "url": url, "error": str(e)})
                log(f"[{url}] 失败: {e}")
    except PipelineError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": ok, "out_root": str(out_root), "articles": results}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
