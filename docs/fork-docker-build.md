# 从 fork 源码构建并运行

要使用 **Markdown 导出时下载图片**和 `wx-export`，请从 fork 的 `feat/md-export-image-localization` 分支构建。入口 README 中的 `ghcr.io/rachelos/we-mp-rss:latest` 是上游发布镜像，不包含这个分支的改动。

## 1. 准备

需要 Git、运行中的 Docker 和 Docker Compose v2+。在新机器上执行：

```bash
git clone --branch feat/md-export-image-localization --single-branch https://github.com/leofinch0824/we-mp-rss.git
cd we-mp-rss
test -f .env || cp .env.example .env
test -f config.yaml || cp config.example.yaml config.yaml
```

如果已经克隆，先切到该分支并拉取更新，再从仓库根目录执行后续命令。首次启动前，在本地 `.env` 设置 `USERNAME` 和 `PASSWORD`；已有数据库的用户密码不会因修改 `.env` 自动更新。不要提交或分享 `.env`、`config.yaml`、`data/`。不使用代理时，将 `.env` 中示例的 `PROXY_URL` 留空。如需使用 Compose 的 sing-box 代理，在 `.env` 中填入 `PROXY_URL` 并设置 `PROXY_ENABLED=True`。

## 2. 构建并启动

```bash
docker compose -f compose/docker-compose.dev.yaml config --quiet
docker compose -f compose/docker-compose.dev.yaml build backend frontend
docker compose -f compose/docker-compose.dev.yaml up -d --no-build
docker compose -f compose/docker-compose.dev.yaml ps
```

- `backend` 和 `frontend` 由当前检出的源码构建，分别生成 `we-mp-rss-backend:dev` 和 `we-mp-rss-frontend:dev`；Redis 和 sing-box 使用现成镜像。首次构建需下载后端基础镜像、浏览器及 Python/Node 依赖，耗时较长。
- 这是**本机联调配置**：前后端仅绑定 `127.0.0.1`，并挂载当前工作树，SQLite 和会话数据保存在 `data/`。不要直接把这个栈暴露到公网。
- 更新分支后，可重新执行 `build backend frontend`，再执行 `up -d --no-build --force-recreate`。保留 `data/` 和 Compose 卷。

## 3. 验证并导出

后端启动后，下面两个请求应成功。若尚未就绪，用 `docker compose -f compose/docker-compose.dev.yaml logs --tail 100 backend frontend` 查看启动日志。

```bash
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8001/api/v1/wx/sys/base_info
curl --fail --silent --show-error --max-time 10 -o /dev/null http://127.0.0.1:5173/
```

1. 打开 [本机前端](http://127.0.0.1:5173/)，用应用账户登录，按界面提示用手机微信扫码授权。有效会话可尝试保活；已失效的会话仍需本人重新扫码。
2. 给 Agent 一篇公众号文章链接，请其按 [`wx-export` Skill](../.claude/skills/wx-export/SKILL.md) 导出；或在宿主机用 Python 3 运行脚本（先在当前终端把 `ARTICLE_URL` 设为要导出的文章链接）：

   ```bash
   python3 .claude/skills/wx-export/scripts/export_article.py --url "$ARTICLE_URL"
   ```

   如修改过应用账户，先在本地终端设置 `WEMPRSS_USER`、`WEMPRSS_PASS`。可加 `--out /path/to/output`，默认输出到 `~/Downloads/wx-articles/`。成功的文章目录包含 `article.md`、`meta.json` 和 `media/`；可用 Skill 中的校验脚本检查图片引用是否完整。
