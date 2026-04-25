# WeRSS API 接口分类梳理

本文档用于沉淀当前运行实例的后端接口分类，方便后续测试、联调和问题排查。

- 在线文档入口：`http://localhost:8001/api/docs#/`
- OpenAPI 地址：`http://localhost:8001/api/openapi.json`
- 路由主入口：`web.py`
- 统计基准：当前运行实例的 OpenAPI 文档，而不是仅按 `apis/*.py` 文件名推断

## 1. 总览

当前实例一共暴露了两层接口：

- 核心业务接口：`131` 个，统一挂在 `/api/v1/wx/*`
- 外围接口：`21` 个，分布在 `/rss/*`、`/feed/*`、`/static/res/*`、`/views/*`

按“后续联调”视角，可以整理为 `9` 大类、共 `152` 个唯一接口。

说明：

- OpenAPI 中总 tag 计数会高于 `152`，因为 `/views/*` 页面路由被同时打上了 `网页预览 / 首页 / 文章 / 文章详情 / 标签 / 公众号` 等多个 tag。
- 本文按“唯一接口”统计，不重复计数。

## 2. 九大类接口

| 分类 | 接口数 | 主要路径 | 主要功能 |
| --- | ---: | --- | --- |
| 1. 身份认证与访问控制 | 24 | `/api/v1/wx/auth/*` `/api/v1/wx/user*` | 登录、登出、Token、二维码登录、密码重置、AK/SK、用户资料 |
| 2. 公众号订阅与文章生命周期 | 23 | `/api/v1/wx/mps/*` `/api/v1/wx/articles*` | 搜索/新增公众号、更新文章、文章详情、收藏/已读、清理、刷新 |
| 3. RSS 与 Feed 对外分发 | 9 | `/rss/*` `/feed/*` | RSS 列表、单公众号 RSS、内容缓存、按 feed/tag/search 输出订阅源 |
| 4. 标签、过滤规则与配置治理 | 16 | `/api/v1/wx/tags*` `/api/v1/wx/filter-rules*` `/api/v1/wx/configs*` | 标签管理、过滤规则管理、运行配置管理 |
| 5. 消息通知与任务调度 | 16 | `/api/v1/wx/message_tasks*` `/api/v1/wx/task-queue*` | 消息任务 CRUD、测试消息、调度器状态、任务历史、队列状态 |
| 6. 级联系统与多节点协同 | 25 | `/api/v1/wx/cascade/*` | 节点管理、任务分发、认领、上报、同步日志、调度启停 |
| 7. 系统运维、环境观测与代码更新 | 11 | `/api/v1/wx/sys/*` `/api/v1/wx/env-exception/*` `/api/v1/wx/github/*` | 资源监控、系统信息、环境异常统计、GitHub 更新/回滚 |
| 8. 工具、导入导出与代理辅助能力 | 21 | `/api/v1/wx/export/*` `/api/v1/wx/tools/*` `/api/v1/wx/proxy/*` `/static/res/*` | 公众号/标签导入导出、文章导出、图片处理、代理转发、资源反向代理 |
| 9. 网页预览接口 | 7 | `/views/*` | 服务端页面预览，给文章页、标签页、首页等场景使用 |

## 3. 分类详解

### 3.1 身份认证与访问控制

对应源码：

- `apis/auth.py`
- `apis/user.py`
- 认证中间件与统一挂载：`web.py`

主要功能：

- 用户名密码登录、Token 获取、Token 刷新、Token 校验
- 二维码登录全流程：获取二维码、二维码图片、扫码状态、扫码完成
- 密码找回：请求验证码、重置密码
- 微信账号切换
- Access Key / Secret Key 管理：创建、列表、更新、停用、删除
- 用户资料：查询当前用户、修改资料、修改密码、头像上传、用户列表、添加用户

代表接口：

- `POST /api/v1/wx/auth/login`
- `POST /api/v1/wx/auth/token`
- `POST /api/v1/wx/auth/refresh`
- `GET /api/v1/wx/auth/verify`
- `GET /api/v1/wx/auth/qr/code`
- `POST /api/v1/wx/auth/ak/create`
- `GET /api/v1/wx/user`
- `PUT /api/v1/wx/user/password`

联调关注点：

- 是否支持 `Bearer Token` 与 `AK-SK` 两种访问方式
- 二维码登录流程是否依赖当前微信授权状态
- 用户相关接口是否有管理员权限边界

### 3.2 公众号订阅与文章生命周期

对应源码：

- `apis/mps.py`
- `apis/article.py`

主要功能：

- 搜索公众号、添加公众号、删除公众号、更新订阅状态
- 通过文章链接反查公众号
- 添加精选文章、查询精选文章任务
- 手动触发某公众号文章更新
- 获取文章列表、文章详情、上一篇/下一篇
- 刷新单篇文章正文
- 改变文章已读/收藏状态
- 清理孤儿文章、旧文章、重复文章

代表接口：

- `GET /api/v1/wx/mps`
- `POST /api/v1/wx/mps`
- `GET /api/v1/wx/mps/search/{kw}`
- `GET /api/v1/wx/mps/update/{mp_id}`
- `GET /api/v1/wx/articles`
- `GET /api/v1/wx/articles/{article_id}`
- `POST /api/v1/wx/articles/{article_id}/refresh`
- `PUT /api/v1/wx/articles/{article_id}/read`
- `PUT /api/v1/wx/articles/{article_id}/favorite`

联调关注点：

- 公众号搜索与文章抓取高度依赖当前授权态和微信侧返回
- 部分操作是异步任务，需配合任务状态接口或延时轮询验证
- 清理接口会改动真实数据，测试环境应先确认隔离

### 3.3 RSS 与 Feed 对外分发

对应源码：

- `apis/rss.py`

主要功能：

- 获取 RSS 列表
- 手动刷新 RSS 列表或单个 feed
- 获取单公众号 RSS 数据
- 获取缓存内容
- 对外输出 feed 订阅源，支持按 feed、tag、search 维度访问

代表接口：

- `GET /rss`
- `GET /rss/fresh`
- `GET /rss/{feed_id}`
- `GET /rss/{feed_id}/api`
- `GET /feed/{feed_id}.{ext}`
- `GET /feed/tag/{tag_id}.{ext}`
- `GET /feed/search/{kw}/{feed_id}.{ext}`

联调关注点：

- 这部分更偏“消费接口”，调用方往往不是前端后台，而是 RSS 客户端
- `feed` 路由格式里会带扩展名，例如 `.xml`

### 3.4 标签、过滤规则与配置治理

对应源码：

- `apis/tags.py`
- `apis/filter_rule.py`
- `apis/config_management.py`

主要功能：

- 标签 CRUD
- 过滤规则 CRUD
- 查询某公众号的启用规则
- 配置项 CRUD

代表接口：

- `GET /api/v1/wx/tags`
- `POST /api/v1/wx/tags`
- `GET /api/v1/wx/filter-rules`
- `GET /api/v1/wx/filter-rules/mp/{mp_id}/active`
- `GET /api/v1/wx/configs`
- `PUT /api/v1/wx/configs/{config_key}`

联调关注点：

- 适合作为后台基础配置联调的第二阶段
- 配置接口会影响运行行为，测试时要记录变更前后值

### 3.5 消息通知与任务调度

对应源码：

- `apis/message_task.py`
- `apis/task_queue.py`

主要功能：

- 消息任务列表、详情、创建、更新、删除
- 测试消息发送
- 手动执行单个消息任务
- 重载任务
- 主队列和内容补抓队列状态
- 调度器状态与作业列表
- 历史记录查看与清空
- 队列清空

代表接口：

- `GET /api/v1/wx/message_tasks`
- `POST /api/v1/wx/message_tasks`
- `POST /api/v1/wx/message_tasks/message/test/{task_id}`
- `GET /api/v1/wx/message_tasks/{task_id}/run`
- `GET /api/v1/wx/task-queue/status`
- `GET /api/v1/wx/task-queue/scheduler/jobs`

联调关注点：

- 这类接口既涉及 DB，也涉及 Redis/内存中的任务状态
- 执行类接口要关注是否立即返回，还是异步入队后轮询状态

### 3.6 级联系统与多节点协同

对应源码：

- `apis/cascade.py`

主要功能：

- 级联节点 CRUD
- 节点凭证生成与连接测试
- 心跳
- 从父节点拉取公众号、消息任务、待处理任务
- 手动任务分发、任务认领、状态更新、结果上报
- 子节点上传文章到网关
- 同步日志与任务分配查看
- 调度器启停与重载

代表接口：

- `POST /api/v1/wx/cascade/nodes`
- `GET /api/v1/wx/cascade/nodes`
- `POST /api/v1/wx/cascade/nodes/{node_id}/credentials`
- `POST /api/v1/wx/cascade/heartbeat`
- `POST /api/v1/wx/cascade/claim-task`
- `POST /api/v1/wx/cascade/report-result`
- `POST /api/v1/wx/cascade/upload-articles`

联调关注点：

- 这是一个独立的大子系统，建议单独成组测试
- 很多接口假设存在“父节点 / 子节点 / 调度器”上下文，不适合与基础后台接口混测

### 3.7 系统运维、环境观测与代码更新

对应源码：

- `apis/sys_info.py`
- `apis/env_exception.py`
- `apis/github_update.py`

主要功能：

- 常规信息、系统信息、资源使用情况
- 手动刷新文章统计
- 环境异常统计与今日异常统计
- GitHub 仓库状态、更新、回滚、提交历史、分支列表

代表接口：

- `GET /api/v1/wx/sys/base_info`
- `GET /api/v1/wx/sys/resources`
- `POST /api/v1/wx/sys/article/refresh`
- `GET /api/v1/wx/env-exception/stats`
- `GET /api/v1/wx/github/status`
- `POST /api/v1/wx/github/update`

联调关注点：

- `github/*` 接口具有明显运维属性，测试前要确认当前运行环境是否允许真实更新或回滚
- `sys/*` 与 `env-exception/*` 很适合做健康检查与监控看板接入

### 3.8 工具、导入导出与代理辅助能力

对应源码：

- `apis/export.py`
- `apis/tools.py`
- `apis/proxy.py`
- `apis/res.py`

主要功能：

- 公众号与标签导入导出
- OPML 导出
- 文章导出、导出文件列表、下载、删除
- 图片裁剪、图片下载、远程图片代理
- 通用代理转发
- 静态资源反向代理

代表接口：

- `GET /api/v1/wx/export/mps/export`
- `POST /api/v1/wx/export/mps/import`
- `GET /api/v1/wx/export/tags`
- `POST /api/v1/wx/tools/export/articles`
- `GET /api/v1/wx/tools/export/download`
- `POST /api/v1/wx/tools/image/crop`
- `GET /api/v1/wx/proxy/{path}`
- `GET /static/res/logo/{path}`

联调关注点：

- 这类接口要特别关注文件系统、下载 header、跨域与代理目标白名单
- 资源代理和通用代理更适合作为“辅助联调能力”，不是主业务第一批接口

### 3.9 网页预览接口

对应源码：

- `views/*`
- 路由挂载见 `web.py`

主要功能：

- 首页
- 标签页
- 公众号页
- 文章列表页
- 文章详情页
- 打印页

代表接口：

- `GET /views/home`
- `GET /views/tags`
- `GET /views/tag/{tag_id}`
- `GET /views/mps`
- `GET /views/articles`
- `GET /views/article/{article_id}`
- `GET /views/print/{article_id}`

联调关注点：

- 这部分不是纯后端 JSON API，而是服务端页面输出
- 文档里会额外显示 `首页 / 文章 / 文章详情 / 标签 / 公众号` 等 tag，本质上都属于这 7 个页面路由

## 4. 当前未纳入运行实例的接口文件

仓库里虽然存在以下文件，但当前运行实例没有在 `web.py` 中挂载：

- `apis/cache.py`
- `apis/ver.py`

因此，它们不属于当前实际可调的接口范围。

## 5. 建议的联调顺序

如果后面要做测试与前后端联调，建议按这个顺序推进：

1. 身份认证与访问控制
2. 公众号订阅与文章生命周期
3. 标签、过滤规则与配置治理
4. 消息通知与任务调度
5. 系统运维、环境观测与代码更新
6. RSS 与 Feed 对外分发
7. 工具、导入导出与代理辅助能力
8. 级联系统与多节点协同
9. 网页预览接口

原因：

- 前 1 到 5 类构成后台主业务闭环
- RSS/Feed 更偏对外消费端
- 工具和代理更偏辅助能力
- 级联系统依赖额外拓扑，不适合放在最前面

## 6. 关键源码入口

- 路由总入口：`web.py`
- 认证：`apis/auth.py`
- 用户：`apis/user.py`
- 公众号：`apis/mps.py`
- 文章：`apis/article.py`
- 标签：`apis/tags.py`
- 过滤规则：`apis/filter_rule.py`
- 配置管理：`apis/config_management.py`
- 消息任务：`apis/message_task.py`
- 任务队列：`apis/task_queue.py`
- 系统信息：`apis/sys_info.py`
- 导出：`apis/export.py`
- 工具：`apis/tools.py`
- 代理：`apis/proxy.py`
- 资源反向代理：`apis/res.py`
- RSS / Feed：`apis/rss.py`
- 级联：`apis/cascade.py`
- 环境异常统计：`apis/env_exception.py`
- GitHub 更新：`apis/github_update.py`

