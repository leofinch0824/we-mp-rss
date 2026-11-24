---
name: wx-export
description: 导出微信公众号文章为 Markdown 并把图片下载到本地（图片本地化），得到可直接离线阅读、整体拷走的文章目录。当用户给出 mp.weixin.qq.com 链接，或要求保存/导出/下载/备份/归档公众号或微信文章、把文章转成 markdown/md、下载文章图片时使用；用户只贴了公众号链接没说做什么，也应主动使用本 skill 导出。Use when the user shares a mp.weixin.qq.com article URL or asks to export, save, download, archive, or back up a WeChat public-account article or its images, even if they only paste the link.
---

# 微信公众号文章导出

把用户给的公众号文章导出为自包含 Markdown：正文是 `article.md`，图片下载到同目录 `media/` 并用相对路径引用，整个目录可以直接拷走离线阅读。
流水线和校验脚本都在本 skill 的 `scripts/` 下（仅标准库，走本地 we-mp-rss API）。命令里的 `<skill_dir>` 指加载本 skill 时给出的 Base directory（项目内安装是 `<repo>/.claude/skills/wx-export`，全局安装是 `~/.claude/skills/wx-export`；没给出就用本 SKILL.md 所在目录）。脚本不依赖当前工作目录，也不改服务端代码。

## 流程

1. **收集链接。** 从消息里提取所有 `mp.weixin.qq.com` 链接；`/s/<sn>` 短链和 `/s?__biz=...&sn=...` 长链都支持。没有链接就问用户要，不要猜。

2. **运行导出**（多个链接重复传 `--url`）：
   ```bash
   python3 "<skill_dir>/scripts/export_article.py" --url <链接> [--url <链接2> ...] [--out <目录>]
   ```
   - 用户指定了保存位置（如"存到 ~/Documents/wx"）→ 传 `--out`；没指定则默认 `~/Downloads/wx-articles/`。
   - 过程日志走 stderr；**stdout 最后一行是 JSON 摘要**，按它判断结果。
   - 脚本会自行检查服务连通、登录（`--user/--password`，或环境变量 `WEMPRSS_USER/WEMPRSS_PASS`）和微信授权；失败时 exit 1 且 JSON 带 `error`。服务不在默认 `127.0.0.1:8001` 时传 `--base`。
   - 报错不要盲目重跑，按 `references/troubleshooting.md` 的症状表判断（多数是服务没起或微信授权过期）。

3. **校验产物。** 把本次成功的文章目录传给校验脚本（可一次传多个）：
   ```bash
   python3 "<skill_dir>/scripts/verify_export.py" "<out_root>/<id>" [...]
   ```
   退出码 0 即通过。非 0 时看 JSON：`missing` 是被 md 引用却丢失的图片文件，`remote_images` 是下载失败、md 里保留了远程 URL 的图片——通常是网络抖动或微信 CDN 限流，重跑第 2 步即可（幂等补齐）；连续失败再查 troubleshooting。

4. **汇报。** 每篇按下面的格式给出；`ok: false` 的条目单独说明 `error` 和下一步建议：

   ```text
   已导出 <N> 篇到 <out_root>：
   - <标题>
     id: <id>
     图片: <images> 张
     路径: <绝对路径>[（已覆盖旧导出）]
   ```

## 输出约定

```text
<out_root>/<发布日期>-<文章sn>/
├── article.md    # 正文，图片引用 ./media/<sha256>.<ext>
├── meta.json     # id/title/url/mp_name/publish_time/exported_at/images/media_bytes/md_bytes
└── media/        # 图片，按原始 URL 的 SHA-256 命名
<out_root>/index.json   # 索引，按 id 去重、按发布时间倒序
```

目录名用「发布日期 + 微信 sn」而不是标题：sn 全局唯一且不变，所以同名标题/转载不会互相覆盖；同一篇重复导出 = 原地刷新（摘要里 `updated: true`），不产生副本。标题只存在于 `meta.json` 和索引里。

`index.json` 是原子写入的；万一被外部损坏，下次导出会先备份为 `index.corrupt-<时间戳>.json`，再从各 `meta.json` 重建。不要手工"修复"索引或 meta。

## 边界

- 只处理用户给出的单篇/多篇文章链接。按公众号批量导出全部文章、PDF/DOCX/CSV 导出、去链接/去图片等选项属于前端工具页，引导用户去那里操作。
- 默认写到 `~/Downloads/wx-articles/`；除非用户明确要求，不要用 `--out` 往仓库里写。导出产物一律不要 commit。

## 维护

改动 `scripts/` 里的脚本后，跑同目录的离线回归测试（不需要服务/网络）：

```bash
cd "<skill_dir>/scripts" && python3 -m unittest discover
```
