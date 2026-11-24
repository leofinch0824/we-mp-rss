#!/usr/bin/env python3
"""校验 export_article.py 的导出产物（只读，仅标准库）。

用法：
    python3 .claude/skills/wx-export/scripts/verify_export.py <文章目录|导出根目录> [...]

传文章目录验单篇，传导出根目录则验其中的所有文章。检查：
- article.md 存在且非空
- meta.json 可解析，且 id 与目录名一致
- md 里引用的本地图片（./media/x）都真实存在
- md 里没有残留远程图片（![](http...) 说明该图本地化失败）
- media/ 下未被 md 引用的孤儿文件只警告，不算失败

stdout 最后一行是 JSON 摘要，过程信息走 stderr；全部通过 exit 0，否则 exit 1。
"""
import json
import re
import sys
from pathlib import Path

# shortcut: 只处理 Markdown 导出器生成的反引号代码和行内图片；支持任意 Markdown 时改用解析器。
IMG_RE = re.compile(
    r"^```[^\n]*\n[\s\S]*?^```[ \t]*$|(?<!`)`+[^`\n]+`+"
    r"|(?<!\\)!\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)",
    re.MULTILINE,
)


def is_article_dir(path: Path) -> bool:
    return path.is_dir() and any((path / name).exists() for name in ("article.md", "meta.json"))


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def collect_dirs(paths: list) -> list:
    """把参数展开成文章目录列表；根目录只下潜一层（导出布局固定）"""
    dirs = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if is_article_dir(p):
            dirs.append(p)
        elif p.is_dir():
            dirs.extend(sorted(d for d in p.iterdir() if is_article_dir(d)))
        else:
            raise SystemExit(f"路径不存在: {p}")
    return dirs


def verify_dir(d: Path) -> dict:
    c = {"md": False, "meta": False, "missing": [], "remote_images": [],
         "orphans": [], "images": 0, "meta_images": None}
    text = ""
    try:
        text = (d / "article.md").read_text(encoding="utf-8")
        c["md"] = bool(text.strip())
    except (OSError, UnicodeError) as e:
        c["md_error"] = str(e)
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        c["meta"] = isinstance(meta, dict) and meta.get("id") == d.name
        c["meta_images"] = meta.get("images") if isinstance(meta, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        c["meta_error"] = str(e)

    referenced = set()
    for ref in IMG_RE.findall(text):
        if not ref:
            continue
        ref = ref.strip("<>")
        if ref.startswith(("http://", "https://", "//")):
            c["remote_images"].append(ref)
            continue
        if ref.startswith("data:"):
            continue
        path = Path(ref.split("#", 1)[0].split("?", 1)[0])
        if path.parent != Path("media") or not (d / path).is_file():
            c["missing"].append(ref)
        else:
            referenced.add(path.name)

    media = d / "media"
    if media.is_dir():
        files = {f.name for f in media.iterdir() if f.is_file()}
        c["images"] = len(files)
        c["orphans"] = sorted(files - referenced)

    c["ok"] = c["md"] and c["meta"] and not c["missing"] and not c["remote_images"]
    return c


def main() -> int:
    if len(sys.argv) < 2:
        log(__doc__.strip().splitlines()[3].strip())  # 用法行
        return 2
    dirs = collect_dirs(sys.argv[1:])
    if not dirs:
        log("没有找到包含 article.md 或 meta.json 的文章目录")
        return 1

    results = []
    for d in dirs:
        c = verify_dir(d)
        results.append({"dir": str(d), **c})
        if c["ok"]:
            log(f"✓ {d.name}: {c['images']} 张图片全部本地化")
        else:
            log(f"✗ {d.name}: missing={len(c['missing'])} remote_images={len(c['remote_images'])} "
                f"md={c['md']} meta={c['meta']}")
        if c["orphans"]:
            log(f"  提示: media/ 有 {len(c['orphans'])} 个未被 md 引用的文件（仅警告）")
        if c.get("meta_error"):
            log(f"  meta.json 读取失败: {c['meta_error']}")

    print(json.dumps({"ok": all(r["ok"] for r in results), "articles": results},
                     ensure_ascii=False))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
