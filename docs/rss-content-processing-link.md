# we-mp-rss RSS 正文处理链路记录

本文档用于记录当前已经讨论并达成结论的 RSS 消费与正文获取链路，后续会继续在此基础上补充时序、异常处理、接口契约和下游处理策略。

## 1. 场景背景

当前有两个系统：

- `we-mp-rss`：负责采集微信公众号文章并对外暴露 RSS / REST API
- 另一个业务项目：订阅 `we-mp-rss` 生成的单公众号 RSS，并对文章做进一步加工处理

目标不是消费“所有公众号的总 RSS”，而是消费“某一个具体公众号的 RSS URL”。

## 2. 当前确定的目标链路

目标链路如下：

1. 另一个项目订阅某个公众号的单独 RSS URL
2. 从 RSS 中获取该公众号最新 `5` 篇文章
3. 从 RSS 中拿到基础字段：
   - 文章 ID
   - 文章标题
   - 发布时间
   - 原文链接
   - 摘要
4. 以“RSS 首次发现时间”为基准，等待约 `10` 分钟
5. 由另一个项目主动调用 `we-mp-rss` 的 REST API 触发正文刷新
6. 刷新完成后，再获取文章详情
7. 基于正文内容、图片链接、HTML 格式和清洗情况，决定下游是否需要二次加工

## 3. 已确认的核心结论

### 3.1 RSS 正文为空，不代表系统不支持正文

`content:encoded` 为空的主要原因不是 RSS 本身不支持正文，而是：

- 文章首次入库时默认可以只保存元信息，不抓正文
- 之后再由后台自动补抓任务或手动刷新接口补正文

## 3.2 当前正文来源不是 `content_html`，而是 `content`

当前 `we-mp-rss` 的 RSS 输出正文主要来自文章表中的 `content` 字段，而不是 `content_html`。

也就是说：

- `RSS / Feed` 输出正文：主要看 `article.content`
- `article.content_html`：是另一个更强处理版本，适合后续 API 详情获取时使用

## 3.3 `content` 是 HTML，不是纯文本

当前正文抓取逻辑会从微信页面中取正文区域 HTML，再做一定程度清理后写入 `content`。

因此：

- `content` 默认应视为 `HTML 片段`
- 不能按纯文本处理
- 如果后续要提取纯文本，需要下游自行做文本化处理

## 3.4 图片链接通常会保留在正文中

当前正文中如果存在图片：

- `content` 中通常仍会保留 `<img>` 标签或相关背景图片引用
- 图片 URL 一般仍是微信 CDN 或外部绝对链接
- 不应假设图片已被替换成本地静态代理链接

因此，下游处理时需要自行判断：

- 是否保留图片
- 是否下载图片
- 是否替换图片 URL

## 3.5 `content` 和 `content_html` 的处理层级不同

当前可以这样理解：

- `content`
  - 更接近原始正文 HTML
  - 有基本清理和过滤规则应用
  - 适合作为“原始可读 HTML”使用

- `content_html`
  - 经过更进一步整理
  - 更适合直接渲染或做稳定 HTML 后处理

后续另一个项目如需稳定消费正文，优先建议使用文章详情 API 返回的 `content_html`。

## 4. 当前决定采用的方案

经过讨论，当前确定采用下面的组合方案：

### 方案主体：由另一个项目主动驱动正文刷新

即：

1. 先通过 RSS 发现最新文章
2. 按“RSS 首次发现时间”延迟 `10` 分钟
3. 再调用 `we-mp-rss` 的文章刷新接口主动拉正文
4. 轮询刷新任务状态
5. 获取文章详情

这样做的原因：

- 时序更可控
- 每篇文章有明确的刷新触发点
- 可以做失败重试
- 不依赖 `we-mp-rss` 内部自动补抓任务的扫描时机

### 方案兜底：保留 `we-mp-rss` 自身自动补抓机制

`we-mp-rss` 本身的自动补抓任务继续保留，但只作为后台兜底，不作为你们主链路的时序依赖。

## 5. 当前保留的 we-mp-rss 自动补抓策略

当前已经确定：

- 保留 `we-mp-rss` 自带正文自动补抓
- 但自动补抓间隔不需要太短
- 将自动补抓间隔调整为 `30` 分钟

当前配置约定：

```env
GATHER.CONTENT=False
GATHER.CONTENT_AUTO_CHECK=True
GATHER.CONTENT_AUTO_INTERVAL=30
```

含义：

- `GATHER.CONTENT=False`
  - 首次采集公众号文章时，不强制同步抓正文
- `GATHER.CONTENT_AUTO_CHECK=True`
  - 启用后台自动补抓正文任务
- `GATHER.CONTENT_AUTO_INTERVAL=30`
  - 后台每 `30` 分钟扫描一次未抓正文文章并尝试补抓

## 6. 推荐调用链路

### 6.1 RSS 发现层

推荐订阅：

```text
GET /feed/{feed_id}.xml?limit=5
GET /feed/{feed_id}.json?limit=5
```

推荐用途：

- `xml / rss`：兼容标准 RSS 消费器
- `json`：更适合作为内部系统对接格式

RSS/Feed 发现阶段建议只拿这些字段：

- `id`
- `title`
- `link`
- `pubDate` / `updated`
- `description`
- `feed.id`
- `feed.name`

### 6.1.1 对另一个项目的推荐输入策略

虽然 `we-mp-rss` 同时提供 XML/RSS 与 JSON 两种单公众号 Feed 输出，但对于另一个项目，当前更推荐以下做法：

#### 对外输入层

继续接受用户提供的 RSS URL，例如：

```text
http://localhost:8001/feed/MP_WXS_3941633310.rss?limit=5
```

这样做的好处是：

- 用户认知上仍然是标准 RSS 地址
- 兼容外部系统已有的 RSS URL 配置习惯

#### 对内消费层

如果识别出该链接属于 `we-mp-rss` 生成的单公众号 Feed，则内部自动转换为：

```text
http://localhost:8001/feed/MP_WXS_3941633310.json?limit=5
```

并保留原有查询参数，如：

- `limit`
- `offset`
- 其他后续扩展参数

### 6.1.2 为什么内部更推荐消费 `.json`

当前结论是：

- 对用户：可以继续暴露 `.rss`
- 对你们自己的程序：更推荐内部改用 `.json`

原因如下：

1. XML/RSS 更适合“订阅协议”，不适合“内部字段消费”
2. JSON 更适合直接读取结构化字段
3. XML 解析需要额外处理：
   - namespace
   - `content:encoded`
   - CDATA
   - HTML 实体转义
4. JSON 对后续链路更顺手：
   - 发现文章
   - 提取 `article_id`
   - 延迟调度
   - 调用正文刷新接口
   - 获取文章详情

因此当前推荐优先级为：

1. 对外接受 `.rss`，内部转 `.json`
2. 直接使用 `.json`
3. 只有在无法转换时，才直接解析 XML

### 6.1.3 规范化策略建议

另一个项目中建议增加一个“Feed URL 规范化”逻辑：

- 如果用户提供的链接满足：
  - Host 属于当前 `we-mp-rss` 服务
  - Path 形如 `/feed/{feed_id}.rss`
  - 或 `/feed/{feed_id}.xml`
  - 或 `/feed/{feed_id}.atom`

则内部自动改写为：

```text
/feed/{feed_id}.json
```

并保留原有查询参数。

### 6.1.4 当前推荐结论

对于另一个项目：

- 不建议直接把 RSS XML 当成内部唯一处理输入
- 更建议把 RSS URL 当“用户输入形式”
- 再在内部统一转成 `Feed JSON` 做程序消费
- XML 解析只保留为兼容兜底方案

### 6.2 延迟刷新层

由另一个项目自行控制：

1. 记录文章的 RSS 首次发现时间
2. 延迟 `10` 分钟
3. 调用正文刷新接口

```text
POST /api/v1/wx/articles/{article_id}/refresh
```

接口返回后，拿到刷新任务 ID。

### 6.3 刷新状态查询层

轮询刷新任务状态：

```text
GET /api/v1/wx/articles/refresh/tasks/{task_id}
```

成功后进入文章详情拉取。

### 6.4 正文详情拉取层

拉取文章详情：

```text
GET /api/v1/wx/articles/{article_id}
```

当前重点字段：

- `title`
- `publish_time`
- `url`
- `description`
- `content`
- `content_html`
- `has_content`
- `pic_url`

## 7. 当前实现选择建议

对于另一个项目，当前建议如下：

### 文章发现

优先级建议如下：

1. 内部系统对接：优先使用 `Feed JSON` 或 REST API
2. 标准 RSS 订阅器兼容：使用 `Feed XML`

如果另一个项目是你们自己可控的业务系统，而不是通用 RSS 阅读器，当前更推荐：

- 用 `GET /feed/{feed_id}.json?limit=5` 做文章发现
- 用 `GET /api/v1/wx/articles/{article_id}` 做正文详情获取

不推荐把 RSS XML 作为下游程序的唯一消费载体。

### 正文获取

不要只依赖 RSS 首次返回的 `content:encoded`。

### 稳定正文来源

以 `GET /api/v1/wx/articles/{article_id}` 返回的：

- `content_html` 作为优先正文字段
- `content` 作为备用正文字段

## 8. 正文校验脚本

为了避免在联调时直接打印大段正文 HTML，同时快速判断正文是否已补抓完成，已新增一个只读验证脚本：

- `tools/check_content_html.py`

对应测试文件：

- `tools/test_check_content_html.py`

脚本功能：

- 支持直接检查单篇文章：`--article-id`
- 支持先取某个公众号最新 N 篇文章，再逐篇检查：`--mp-id --limit`
- 支持 `--token` 直传 Bearer Token
- 支持 `--username --password` 自动登录换取 Token
- 只输出结构化摘要，不输出正文内容本身

输出字段：

- `article_id`
- `title`
- `has_content`
- `content_len`
- `content_html_len`
- `content_html_present`

示例命令：

```bash
python3 tools/check_content_html.py \
  --base-url http://127.0.0.1:8001 \
  --mp-id MP_WXS_3941633310 \
  --limit 5 \
  --username admin \
  --password admin@123
```

当前验证结果：

- 目标公众号 `MP_WXS_3941633310` 最新 `5` 篇文章均已补抓正文
- 这 `5` 篇文章的 `has_content=1`
- 这 `5` 篇文章的 `content_html_present=true`
- `content_html` 长度明显小于 `content`，说明 `content_html` 是经过进一步整理后的版本

## 9. 当前推荐消费方式

如果另一个项目是你们自己的业务系统，而不是必须兼容 RSS 标准客户端，那么目前更推荐：

### 推荐方式

- 文章发现层：消费 `Feed JSON` 或后台 REST API
- 正文详情层：消费文章详情 REST API

### 不推荐方式

- 直接把 RSS XML 当成下游处理的唯一数据源

原因：

1. RSS XML 更适合“订阅分发”，不适合“稳定字段消费”
2. RSS 中的正文依赖 `content`，不是 `content_html`
3. RSS 首次发现时，正文可能为空，这是正常现象
4. 文章详情 API 能直接给出：
   - `has_content`
   - `content`
   - `content_html`
   - 其他结构化字段
5. REST API 更适合你们做延迟控制、重试和状态判断

因此当前最推荐的组合是：

1. 用 `Feed JSON` 或 RSS 发现最新文章
2. 记录 RSS 首次发现时间
3. 延迟 `10` 分钟
4. 调用 `POST /api/v1/wx/articles/{article_id}/refresh`
5. 轮询 `GET /api/v1/wx/articles/refresh/tasks/{task_id}`
6. 再调用 `GET /api/v1/wx/articles/{article_id}`
7. 优先消费 `content_html`

## 10. 当前已确认但需要注意的边界

### 10.1 自动补抓不等于“每篇文章精确延迟 10 分钟”

`we-mp-rss` 自带自动补抓是“周期扫描”模式，不是“按每篇文章的发现时间精确延迟执行”。

因此：

- 另一个项目若需要“首次发现后 10 分钟开始抓正文”
- 必须由你们自己的项目控制这段延迟逻辑

### 10.2 RSS 首次发现时正文可能为空

这是当前链路允许出现的正常现象，不应直接视为异常。

### 10.3 任务调度状态接口不一定等于正文补抓调度器本身

当前已有观察表明：

- 某些任务队列/调度器状态接口未必能直接反映正文补抓任务的真实状态
- 因此后续如需监控正文补抓，需要单独定义观察方式

这个细节后续还需要继续补充。

## 11. 后续待补充项

以下内容后续继续补到本文件：

1. 另一个项目的完整时序图
2. 正文刷新任务的状态机定义
3. 失败重试策略
4. 去重策略
5. 下游二次清洗规则建议
6. `content` 与 `content_html` 的字段差异示例
7. 正文图片处理策略
8. 监控与告警建议

## 12. 当前阶段的统一结论

当前最终结论是：

- `we-mp-rss` 继续保留自动补抓正文能力，作为后台兜底
- 自动补抓间隔设置为 `30` 分钟
- 真正满足业务时序要求的“延迟 10 分钟后抓正文”逻辑，由另一个项目自己实现
- 下游正文消费优先使用文章详情接口返回结果，而不是只依赖 RSS 首次正文输出
