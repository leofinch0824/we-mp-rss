---
name: wx-export
description: 导出微信公众号文章为 Markdown 并将图片持久化到本地。当用户给出 mp.weixin.qq.com 文章链接并要求导出、保存、下载文章或文章图片时使用。
---

# 微信公众号文章导出

把一篇或多篇微信公众号文章导出为自包含的 Markdown（图片下载到本地 `media/`，相对路径引用）。

## 执行步骤

1. **收集链接**：从用户消息中提取所有 `mp.weixin.qq.com` 文章链接（`/s/...` 或带 `sn=` 参数的都支持）。没有链接时向用户要。

2. **确认本地服务在跑**：
   ```bash
   docker compose -f compose/docker-compose.dev.yaml ps --format "{{.Name}} {{.Status}}"
   ```
   若 `we-mp-rss-backend-dev` 不是 Up，先 `docker compose -f compose/docker-compose.dev.yaml up -d` 并等它健康（`docker logs -f we-mp-rss-backend-dev` 直到出现 startup complete，或轮询 `curl -s http://127.0.0.1:8001/api/v1/wx/sys_info`）。

3. **运行导出脚本**（在仓库根目录）：
   ```bash
   python3 scripts/export_article.py --url <链接1> [--url <链接2> ...] [--out <用户指定目录>]
   ```
   进度信息走 stderr 可忽略；**最后一行 stdout 是 JSON 摘要**，解析它。
   用户在消息里指定了保存位置（如"保存到 ~/Documents/wx"）→ 传 `--out`；未指定则省略，脚本默认输出到 `downloads/articles/`。

4. **按摘要汇报**：对每个条目给出 `id`（目录名）、标题、图片张数、落盘路径；`"updated": true` 表示覆盖了旧导出（幂等刷新）。`ok: false` 的条目单独说明 error。

## 输出布局（固定约定）

```
downloads/articles/<发布日期>-<文章sn>/
├── article.md   # 正文
├── meta.json    # 标题/URL/发布时间/统计
└── media/       # sha256 命名的图片
downloads/articles/index.json   # 索引，按 id 去重
```

## 常见错误

- **无法连接 API**：服务没起，回到第 2 步。
- **登录失败/401**：默认凭据 admin/admin@123 不对 → 让用户用 `.env` 里设置的 `USERNAME`/`PASSWORD`（或直接问用户），传 `--user/--password`。
- **"微信公众号授权已过期"**（脚本预检 `/sys_info/info` 的 `wx.login=false` 触发）：自动保活未启用，无法自动恢复。让用户打开 http://127.0.0.1:5173 重新扫码授权，完成后再重跑脚本。
- **抓取失败、提示登录状态**：微信后台会话中途失效，同上一条处理。
- **导出失败但抓取成功**：看 `docker logs we-mp-rss-backend-dev` 尾部，多为偶发网络问题，直接重跑一次。

## 备注

- 重复导出同一篇 = 原地刷新，不会产生副本；目录名由发布日期 + 微信侧永久 sn 组成，标题不参与命名。
- zip 双端自动清理：服务端下载后即删（`delete_after_download=true`）并清空打包残留目录，客户端解包后删临时 zip，不会留垃圾文件。
- 图片失败数会体现在后端日志/导出消息里；md 中保留远程 URL 兜底。
- 修改导出选项（如去链接、去图片）不属于本 skill 范围，让用户去前端工具页操作。
