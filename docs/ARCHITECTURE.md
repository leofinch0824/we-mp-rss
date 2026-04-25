# WeMP-RSS 项目架构与接口文档

## 1. 项目概览

WeMP-RSS 是一个微信公众号文章采集与 RSS 订阅系统，基于 FastAPI 构建。核心功能包括：

- 微信公众号文章自动采集
- RSS/Atom/JSON Feed 生成
- 多渠道消息推送（钉钉、飞书、企业微信、Bark、自定义 Webhook）
- 分布式级联采集架构（父子节点）
- 文章内容清洗与过滤
- 用户认证与权限管理

**技术栈**: Python 3.x / FastAPI / SQLAlchemy / Playwright / APScheduler / Redis / Vue 3

---

## 2. 项目结构

```
we-mp-rss/
├── main.py                         # 入口：启动 Redis、认证、调度、服务
├── web.py                          # FastAPI 应用：中间件、路由注册、SPA 托管
├── config.example.yaml             # 配置模板
├── Dockerfile                      # 容器构建
├── requirements.txt                # 依赖清单
│
├── apis/                           # API 路由模块（17 个文件）
│   ├── ver.py                      #   API 版本前缀 /api/v1/wx
│   ├── base.py                     #   通用响应工具
│   ├── auth.py                     #   认证接口
│   ├── user.py                     #   用户管理
│   ├── article.py                  #   文章管理
│   ├── mps.py                      #   公众号管理
│   ├── rss.py                      #   RSS Feed 生成
│   ├── res.py                      #   图片反向代理
│   ├── config_management.py        #   运行时配置
│   ├── message_task.py             #   消息任务调度
│   ├── sys_info.py                 #   系统信息
│   ├── tags.py                     #   标签管理
│   ├── export.py                   #   导入/导出
│   ├── tools.py                    #   导出/图片工具
│   ├── cascade.py                  #   级联节点管理
│   ├── env_exception.py            #   环境异常统计
│   ├── filter_rule.py              #   HTML 过滤规则
│   ├── task_queue.py               #   任务队列监控
│   ├── proxy.py                    #   HTTP 代理
│   ├── github_update.py            #   Git 自更新
│   └── cache.py                    #   缓存管理
│
├── core/                           # 核心业务逻辑
│   ├── config.py                   #   配置加载（YAML + 环境变量插值）
│   ├── auth.py                     #   JWT/AK-SK/级联认证
│   ├── db.py                       #   数据库操作封装
│   ├── cache.py                    #   文件缓存（SHA256 键 + TTL）
│   ├── cascade.py                  #   级联管理器（父/子节点）
│   ├── rss.py                      #   RSS 生成引擎
│   ├── redis_client.py             #   Redis 客户端
│   ├── article_content.py          #   文章内容抓取（Web/API 双模式）
│   ├── article_lax.py              #   文章统计
│   ├── ws_manager.py               #   WebSocket 广播
│   ├── content_format.py           #   HTML→Text/Markdown 转换
│   ├── resource.py                 #   系统资源监控
│   ├── task.py                     #   APScheduler 封装
│   ├── queue.py                    #   任务队列（线程安全）
│   ├── thread.py                   #   可停止线程
│   ├── log.py                      #   日志配置
│   └── wx/                         #   微信数据采集编排
│
├── core/models/                    # SQLAlchemy ORM 模型
│   ├── base.py                     #   DataStatus + Base
│   ├── article.py                  #   Article（24 字段）
│   ├── feed.py                     #   Feed（公众号）
│   ├── user.py                     #   User（用户）
│   ├── message_task.py             #   MessageTask（消息任务）
│   ├── access_key.py               #   AccessKey（AK/SK）
│   ├── cascade_node.py             #   CascadeNode + CascadeSyncLog
│   ├── cascade_task_allocation.py  #   CascadeTaskAllocation
│   ├── filter_rule.py              #   FilterRule
│   ├── tags.py                     #   Tags
│   └── config_management.py        #   ConfigManagement
│
├── driver/                         # 认证与浏览器自动化
│   ├── base.py                     #   根据 auth_web 切换实现
│   ├── wx.py                       #   Playwright 登录（浏览器模式）
│   ├── wx_api.py                   #   HTTP 登录（API 模式）
│   ├── wxarticle.py                #   文章内容抓取器
│   ├── auth.py                     #   认证服务启动
│   ├── playwright_driver.py        #   Playwright 控制器
│   ├── cookies.py                  #   Cookie 过期检测
│   ├── store.py                    #   Cookie 加密存储
│   ├── token.py                    #   Token 存储
│   ├── success.py                  #   登录成功回调
│   ├── user_agent.py               #   UA 生成器
│   └── anti_crawler_config.py      #   反检测配置
│
├── jobs/                           # 后台任务与调度
│   ├── mps.py                      #   核心调度器
│   ├── article.py                  #   文章保存回调
│   ├── cascade_sync.py             #   子节点同步服务
│   ├── cascade_task_dispatcher.py  #   父节点任务分发
│   ├── cascade_init.py             #   级联初始化 CLI
│   ├── failauth.py                 #   认证过期通知
│   ├── fetch_no_article.py         #   无内容文章自动同步
│   ├── notice.py                   #   多渠道通知
│   ├── webhook.py                  #   Webhook 消息投递
│   └── taskmsg.py                  #   消息任务查询
│
├── tools/                          # 工具脚本
├── schemas/                        # Pydantic 模型
├── views/                          # 服务端页面路由
└── web_ui/                         # Vue 3 前端 SPA
```

---

## 3. 系统架构流程图

### 3.1 启动流程

```
main.py 启动
    │
    ├── 1. Windows 事件循环初始化（如需）
    │
    ├── 2. 启动 Redis（可选）
    │
    ├── 3. 启动认证服务 ──── driver/auth.py
    │       ├── Token 登录初始化
    │       └── 定时刷新 Cron（可选）
    │
    ├── 4. 启动级联同步服务（可选）──── jobs/cascade_sync.py
    │       └── 子节点：定时拉取 Feed/任务、发送心跳
    │
    ├── 5. 启动任务调度器 ──── jobs/mps.py::start_job()
    │       └── 注册每个 MessageTask 的 Cron 任务
    │
    ├── 6. 启动文章内容自动同步（可选）──── jobs/fetch_no_article.py
    │
    ├── 7. 启动文章统计刷新（可选）
    │
    └── 8. 启动 Uvicorn ──── web:app (port 8001)
            ├── CORS 中间件
            ├── AK/SK 中间件
            ├── 自定义 Header 中间件
            ├── 注册 16 个 API 子路由
            ├── 挂载静态文件
            └── 托管 Vue SPA
```

### 3.2 文章采集主流程

```
定时 Cron 触发 (APScheduler)
    │
    ▼
jobs/mps.py::add_job(mp_id)
    │
    ▼
TaskQueue 入队 ──── core/queue.py
    │
    ▼
jobs/mps.py::do_job(mp_id)
    │
    ├── driver/base.py → WX_API / WeChat_api
    │       │
    │       ▼
    │   获取公众号文章列表
    │       │
    │       ▼
    │   返回文章元数据列表
    │
    ▼
遍历新文章 → jobs/article.py::UpdateArticle()
    │
    ├── DB.add_article() 保存到数据库
    │
    └── 文章内容抓取（异步/后台）
            │
            ├── core/article_content.py::sync_article_content()
            │       │
            │       ├── "web" 模式: Playwright 渲染
            │       │       └── driver/wxarticle.py::WXArticleFetcher
            │       │
            │       └── "api" 模式: HTTP API 请求
            │               └── driver/wx_api.py::WeChatAPI
            │
            ├── HTML 修复 (tools/fix.py)
            ├── 过滤规则 (apis/filter_rule.py)
            └── 描述提取、状态更新

所有文章处理完成
    │
    ├── 发送 Webhook 通知 ──── jobs/webhook.py
    │       ├── 消息模板渲染
    │       └── HTTP POST 投递
    │
    └── 级联结果上报（如配置）──── core/cascade.py
```

### 3.3 认证流程

```
用户请求登录
    │
    ├── 浏览器模式 (auth_web=true)
    │       │
    │       ▼
    │   GET /api/v1/wx/auth/qr/code
    │       │
    │       ▼
    │   driver/wx.py::Wx 生成二维码
    │       │
    │       ▼
    │   GET /api/v1/wx/auth/qr/image  ← 返回二维码图片
    │       │
    │       ▼
    │   GET /api/v1/wx/auth/qr/status ← 轮询扫码状态
    │       │
    │       ├── 未扫码 → 继续等待
    │       ├── 已扫码 → 返回 Token
    │       └── 超时   → 重新生成
    │
    └── API 模式 (auth_web=false)
            │
            ▼
        driver/wx_api.py::WeChatAPI
            │
            ▼
        HTTP 请求微信 API 获取二维码
            │
            ▼
        轮询登录状态 → 返回 Token

登录成功
    │
    ├── driver/success.py::Success()
    │       ├── 提取 Token/Cookie
    │       ├── driver/store.py::KeyStore 加密存储
    │       ├── driver/token.py 持久化
    │       └── 发送通知
    │
    └── Cookie 自动刷新 Cron
```

### 3.4 级联分布式架构

```
┌─────────────────────────────────────────────────────┐
│                    父节点 (Gateway)                    │
│                                                       │
│  cascade.py::CascadeManager                          │
│  ├── 管理 MP 列表                                     │
│  ├── 创建任务分配 (CascadeTaskAllocation)              │
│  ├── 通知子节点 (push)                                │
│  └── 接收文章上传                                     │
│                                                       │
│  cascade_task_dispatcher.py::CascadeScheduleService   │
│  └── Cron 定时分发任务                                │
└─────────────┬───────────────┬───────────────────────┘
              │               │
     HTTP API │               │ HTTP API
              │               │
    ┌─────────▼──────┐ ┌─────▼──────────┐
    │   子节点 A      │ │   子节点 B      │
    │                  │ │                  │
    │ cascade_sync.py  │ │ cascade_sync.py  │
    │ ├── 拉取 Feed   │ │ ├── 拉取 Feed   │
    │ ├── 拉取任务    │ │ ├── 拉取任务    │
    │ ├── 认领任务    │ │ ├── 认领任务    │
    │ ├── 执行采集    │ │ ├── 执行采集    │
    │ ├── 上传文章    │ │ ├── 上传文章    │
    │ └── 发送心跳    │ │ └── 发送心跳    │
    └─────────────────┘ └─────────────────┘

任务生命周期:
  pending → claimed → executing → completed/failed/timeout

通信模型:
  Push: 父节点 POST /notify → 子节点立即拉取
  Pull: 子节点定时 GET /pending-tasks → 认领并执行
```

### 3.5 RSS Feed 生成流程

```
请求 RSS Feed
    │
    ▼
GET /api/v1/wx/feed/{feed_id}.{ext}
    │   ext: xml(默认) / atom / json
    │
    ▼
core/rss.py::RSS
    │
    ├── 检查文件缓存
    │       ├── 命中 → 直接返回
    │       └── 未命中 → 生成
    │
    ├── 从 DB 查询公众号文章列表
    │
    ├── 生成 Feed 内容
    │       ├── RSS 2.0 XML
    │       ├── Atom XML
    │       └── JSON Feed
    │
    ├── 写入文件缓存
    │
    └── 返回 Response
```

### 3.6 消息推送流程

```
文章采集完成 / 定时 Cron 触发
    │
    ▼
jobs/taskmsg.py::get_message_task()
    │
    ▼
jobs/webhook.py::web_hook()
    │
    ├── message_type=0 → 系统通知
    │       └── jobs/notice.py::sys_notice()
    │           ├── 钉钉 (DingTalk)
    │           ├── 飞书 (Feishu)
    │           ├── 企业微信
    │           ├── 自定义 Webhook
    │           └── Bark (iOS)
    │
    └── message_type=1 → Webhook 投递
            └── call_webhook()
                ├── 模板渲染 (Jinja2)
                ├── 内容格式转换
                └── HTTP POST (自定义 Headers/Cookies)
```

---

## 4. API 接口文档

**基础路径**: `/api/v1/wx`

### 4.1 认证接口 `/auth`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/auth/qr/code` | 生成微信登录二维码 | 无 |
| GET | `/auth/qr/image` | 获取二维码图片 | 无 |
| GET | `/auth/qr/status` | 轮询扫码状态 | 无 |
| POST | `/auth/login` | 账号密码登录 | 无 |
| POST | `/auth/token` | OAuth2 Token 获取 | 无 |
| POST | `/auth/logout` | 退出登录 | JWT |
| POST | `/auth/refresh` | 刷新 JWT Token | JWT |
| GET | `/auth/verify` | 验证 Token 有效性 | JWT |
| POST | `/auth/ak/create` | 创建 AK/SK 密钥对 | JWT/Admin |
| GET | `/auth/ak/list` | 列出 AK/SK 密钥 | JWT |
| PUT | `/auth/ak/{ak_id}` | 更新 AK/SK 密钥 | JWT/Admin |
| POST | `/auth/ak/{ak_id}/deactivate` | 停用 AK/SK 密钥 | JWT/Admin |
| DELETE | `/auth/ak/{ak_id}` | 删除 AK/SK 密钥 | JWT/Admin |
| POST | `/auth/password/reset-request` | 请求密码重置 | 无 |
| POST | `/auth/password/reset` | 执行密码重置 | 无 |
| POST | `/auth/switch` | 切换微信账号 | JWT |

### 4.2 用户接口 `/user`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/user/` | 获取当前用户信息 | JWT |
| GET | `/user/list` | 获取用户列表 | JWT/Admin |
| POST | `/user/` | 创建用户 | JWT/Admin |
| PUT | `/user/` | 更新用户信息 | JWT |
| PUT | `/user/password` | 修改密码 | JWT |
| POST | `/user/avatar` | 上传头像 | JWT |
| POST | `/user/upload` | 上传文件 | JWT |

### 4.3 文章接口 `/articles`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/articles/` | 文章列表（分页/筛选） | JWT/AK |
| POST | `/articles/` | 手动添加文章 | JWT |
| GET | `/articles/{id}` | 文章详情 | JWT/AK |
| DELETE | `/articles/{id}` | 删除文章 | JWT |
| PUT | `/articles/{id}/read` | 标记已读 | JWT |
| PUT | `/articles/{id}/favorite` | 标记收藏 | JWT |
| POST | `/articles/{id}/refresh` | 刷新文章内容（异步） | JWT |
| GET | `/articles/refresh/tasks/{task_id}` | 查询刷新任务状态 | JWT |
| GET | `/articles/{id}/next` | 获取下一篇文章 | JWT |
| GET | `/articles/{id}/prev` | 获取上一篇文章 | JWT |
| DELETE | `/articles/clean` | 清理孤立文章 | JWT |
| DELETE | `/articles/clean-old` | 清理旧文章 | JWT |
| DELETE | `/articles/clean_duplicate_articles` | 清理重复文章 | JWT |

### 4.4 公众号接口 `/mps`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/mps/` | 公众号列表 | JWT/AK |
| GET | `/mps/{mp_id}` | 公众号详情 | JWT/AK |
| POST | `/mps/` | 添加公众号 | JWT |
| DELETE | `/mps/{mp_id}` | 删除公众号 | JWT |
| PUT | `/mps/{mp_id}` | 更新公众号信息 | JWT |
| GET | `/mps/search/{kw}` | 搜索公众号 | JWT |
| POST | `/mps/by_article` | 通过文章链接添加公众号 | JWT |
| POST | `/mps/featured/article` | 添加精选文章（异步） | JWT |
| GET | `/mps/featured/article/tasks/{task_id}` | 查询精选文章任务状态 | JWT |
| GET | `/mps/update/{mp_id}` | 更新公众号文章 | JWT |

### 4.5 RSS/Feed 接口 `/rss` + `/feed`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/feed/{feed_id}.{ext}` | 获取 RSS Feed（xml/atom/json） | 无 |
| GET | `/feed/search/{kw}/{feed_id}.{ext}` | 搜索文章 Feed | 无 |
| GET | `/feed/tag/{tag_id}.{ext}` | 按标签过滤 Feed | 无 |
| GET | `/rss` | RSS 列表 | JWT |
| GET | `/rss/{feed_id}` | RSS 详情 | JWT |
| GET | `/rss/{feed_id}/api` | RSS API 数据 | JWT |
| GET | `/rss/fresh` | 刷新所有 RSS 缓存 | JWT |
| GET | `/rss/content/{content_id}` | 获取文章缓存内容 | 无 |
| ANY | `/rss/{feed_id}/fresh` | 刷新指定 RSS 缓存 | JWT |

### 4.6 资源代理 `/res`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| ANY | `/res/logo/{path:path}` | 反向代理微信 CDN 图片（域名限制） | 无 |

### 4.7 配置管理 `/configs`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/configs/` | 获取所有配置 | JWT/Admin |
| GET | `/configs/{key}` | 获取指定配置 | JWT |
| POST | `/configs/` | 创建配置项 | JWT/Admin |
| PUT | `/configs/{key}` | 更新配置项 | JWT/Admin |
| DELETE | `/configs/{key}` | 删除配置项 | JWT/Admin |

### 4.8 消息任务 `/message_tasks`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/message_tasks/` | 任务列表 | JWT |
| GET | `/message_tasks/{task_id}` | 任务详情 | JWT |
| POST | `/message_tasks/` | 创建消息任务 | JWT |
| PUT | `/message_tasks/{task_id}` | 更新消息任务 | JWT |
| DELETE | `/message_tasks/{task_id}` | 删除消息任务 | JWT |
| POST | `/message_tasks/message/test/{task_id}` | 测试发送消息 | JWT |
| GET | `/message_tasks/{task_id}/run` | 立即执行任务 | JWT |
| PUT | `/message_tasks/job/fresh` | 刷新调度任务 | JWT |

### 4.9 系统信息 `/sys`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/sys/base_info` | 系统基本信息 | JWT |
| GET | `/sys/resources` | 系统资源监控（CPU/内存/磁盘） | JWT |
| POST | `/sys/article/refresh` | 刷新文章统计 | JWT |
| GET | `/sys/info` | 系统综合信息 | JWT |

### 4.10 标签管理 `/tags`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/tags/` | 标签列表 | JWT/AK |
| POST | `/tags/` | 创建标签 | JWT |
| GET | `/tags/{tag_id}` | 标签详情 | JWT |
| PUT | `/tags/{tag_id}` | 更新标签 | JWT |
| DELETE | `/tags/{tag_id}` | 删除标签 | JWT |

### 4.11 导入导出 `/export`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/export/mps/export` | 导出公众号列表（CSV） | JWT |
| POST | `/export/mps/import` | 导入公众号（CSV） | JWT |
| GET | `/export/mps/opml` | 导出 OPML 订阅文件 | JWT |
| GET | `/export/tags` | 导出标签（CSV） | JWT |
| POST | `/export/tags/import` | 导入标签（CSV） | JWT |

### 4.12 工具接口 `/tools`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| POST | `/tools/export/articles` | 导出文章（md/docx/json/csv/pdf） | JWT |
| GET | `/tools/export/download` | 下载导出文件 | JWT |
| GET | `/tools/export/list` | 列出已导出文件 | JWT |
| DELETE | `/tools/export/delete` | 删除导出文件 | JWT |
| DELETE | `/tools/export/delete-by-query` | 按条件删除导出文件 | JWT |
| POST | `/tools/image/crop` | 图片裁剪 | JWT |
| GET | `/tools/image/download/{filename}` | 下载图片 | JWT |
| GET | `/tools/image/proxy` | 代理下载图片 | JWT |

### 4.13 级联管理 `/cascade`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| POST | `/cascade/nodes` | 创建节点 | JWT/Admin |
| GET | `/cascade/nodes` | 节点列表 | JWT |
| GET | `/cascade/nodes/{id}` | 节点详情 | JWT |
| PUT | `/cascade/nodes/{id}` | 更新节点 | JWT/Admin |
| DELETE | `/cascade/nodes/{id}` | 删除节点 | JWT/Admin |
| POST | `/cascade/nodes/{id}/credentials` | 生成节点凭证 | JWT/Admin |
| POST | `/cascade/nodes/{id}/test-connection` | 测试节点连接 | JWT |
| GET | `/cascade/feeds` | 获取 Feed 列表（子节点拉取） | AK/级联 |
| GET | `/cascade/message-tasks` | 获取消息任务（子节点拉取） | AK/级联 |
| POST | `/cascade/report-result` | 上报任务结果 | AK/级联 |
| POST | `/cascade/heartbeat` | 发送心跳 | AK/级联 |
| POST | `/cascade/notify` | 通知子节点 | AK/级联 |
| GET | `/cascade/sync-logs` | 同步日志 | JWT |
| GET | `/cascade/pending-tasks` | 获取待认领任务 | AK/级联 |
| POST | `/cascade/claim-task` | 认领任务 | AK/级联 |
| PUT | `/cascade/task-status` | 更新任务状态 | AK/级联 |
| POST | `/cascade/upload-articles` | 上传文章 | AK/级联 |
| POST | `/cascade/report-completion` | 报告完成 | AK/级联 |
| POST | `/cascade/dispatch-task` | 分发任务 | JWT/Admin |
| GET | `/cascade/allocations` | 任务分配列表 | JWT |
| POST | `/cascade/start-scheduler` | 启动调度器 | JWT/Admin |
| POST | `/cascade/stop-scheduler` | 停止调度器 | JWT/Admin |
| POST | `/cascade/reload-scheduler` | 重载调度器 | JWT/Admin |
| GET | `/cascade/feed-status` | Feed 状态 | JWT |
| GET | `/cascade/pending-allocations` | 待处理分配 | JWT |

### 4.14 环境异常 `/env-exception`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/env-exception/stats` | 按日期统计异常 | JWT |
| GET | `/env-exception/today` | 今日异常统计 | JWT |

### 4.15 过滤规则 `/filter-rules`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/filter-rules/` | 规则列表 | JWT |
| GET | `/filter-rules/{rule_id}` | 规则详情 | JWT |
| POST | `/filter-rules/` | 创建规则 | JWT |
| PUT | `/filter-rules/{rule_id}` | 更新规则 | JWT |
| DELETE | `/filter-rules/{rule_id}` | 删除规则 | JWT |
| GET | `/filter-rules/mp/{mp_id}/active` | 获取公众号活跃规则 | JWT/AK |

### 4.16 任务队列 `/task-queue`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/task-queue/status` | 队列状态总览 | JWT |
| GET | `/task-queue/main/status` | 主队列状态 | JWT |
| GET | `/task-queue/content/status` | 内容队列状态 | JWT |
| GET | `/task-queue/history` | 执行历史 | JWT |
| POST | `/task-queue/clear` | 清空队列 | JWT |
| POST | `/task-queue/history/clear` | 清空历史 | JWT |
| GET | `/task-queue/scheduler/status` | 调度器状态 | JWT |
| GET | `/task-queue/scheduler/jobs` | 调度任务列表 | JWT |
| WS | `/task-queue/ws` | WebSocket 实时状态推送 | JWT |

### 4.17 代理 `/proxy`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/proxy/{path:path}` | HTTP 代理（域名白名单） | JWT |
| OPTIONS | `/proxy/{path:path}` | CORS 预检 | 无 |
| POST | `/proxy/{path:path}` | HTTP POST 代理 | JWT |

### 4.18 自更新 `/github`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/github/status` | 更新状态 | JWT/Admin |
| POST | `/github/update` | 执行更新 | JWT/Admin |
| GET | `/github/commits` | 提交历史 | JWT |
| POST | `/github/rollback` | 回滚版本 | JWT/Admin |
| GET | `/github/branches` | 分支列表 | JWT |

### 4.19 缓存管理 `/cache`

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| DELETE | `/cache/clear` | 清空所有缓存 | JWT/Admin |
| DELETE | `/cache/clear/{pattern}` | 按前缀清空缓存 | JWT/Admin |

---

## 5. 认证体系

系统支持三种认证方式：

| 方式 | Header | 适用场景 |
|------|--------|----------|
| JWT | `Authorization: Bearer {token}` | 用户登录、前端交互 |
| AK/SK | `Authorization: AK-SK {key}:{secret}` | API 调用、服务间通信 |
| 级联认证 | AK/SK + 级联节点验证 | 父子节点间通信 |

**JWT 生命周期**:
- 登录 → 签发 Access Token
- `token_expire_minutes` 控制过期时间
- `/auth/refresh` 续签
- `/auth/verify` 验证有效性

**AK/SK 机制**:
- 管理员创建，绑定用户和权限
- 支持过期时间和启用/停用
- 中间件自动提取并注入请求状态

---

## 6. 数据库模型

| 模型 | 表名 | 核心字段 |
|------|------|----------|
| Article | articles | id, mp_id, title, url, content, content_html, publish_time, copyright_stat |
| Feed | feeds | id, mp_name, mp_cover, mp_intro, status, sync_time |
| User | users | username, password_hash, is_active, role, permissions, nickname, avatar |
| MessageTask | message_tasks | message_type, name, message_template, web_hook_url, cron_exp, status |
| MessageTask | message_tasks_logs | task_id, mps_id, update_count, log, status |
| AccessKey | access_keys | user_id, key, secret, name, permissions, is_active, expires_at |
| CascadeNode | cascade_nodes | node_type, name, api_url, api_key, api_secret_hash, parent_id, status |
| CascadeSyncLog | cascade_sync_logs | node_id, operation, direction, status, data_count |
| CascadeTaskAllocation | cascade_task_allocations | task_id, node_id, feed_ids, status, article_count |
| FilterRule | filter_rules | mp_id, rule_name, remove_ids, remove_classes, remove_selectors |
| Tags | tags | name, cover, intro, mps_id, status |
| ConfigManagement | config_management | config_key, config_value, description |

---

## 7. 中间件链

```
请求进入
    │
    ▼
CORSMiddleware          ← 允许所有来源
    │
    ▼
AKMiddleware            ← 提取 AK/SK Header
    │
    ▼
Custom Header Middleware ← 注入 X-Version, X-Powered-By
    │
    ▼
路由匹配 → 认证依赖注入（JWT/AK/级联）
    │
    ▼
业务处理
    │
    ▼
响应返回
```
