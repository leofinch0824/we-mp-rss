# RSS 服务端集成开发说明

本文档面向另一个项目的开发同学，描述“业务消费端如何对接 RSS 服务端并获取最新文章正文”的完整需求背景、实现流程、接口调用方式与伪代码。

本说明刻意采用抽象表达，不依赖服务端具体项目名。

## 1. 目标

业务消费端需要对接一个本地运行的 RSS 服务端，默认地址为：

```text
http://127.0.0.1:8001
```

消费目标不是“所有订阅源的总聚合”，而是“某一个具体公众号/频道对应的单独 Feed”。

业务上需要完成以下链路：

1. 输入一个单频道 Feed 地址
2. 获取该频道最新 `5` 篇文章
3. 提取文章基础字段
4. 以“RSS 首次发现时间”为基准延迟 `10` 分钟
5. 主动触发服务端刷新该文章正文
6. 查询正文刷新任务状态
7. 获取文章详情
8. 使用正文内容做下游加工处理

## 2. 需求背景

RSS 服务端对外暴露了两层能力：

1. `Feed 输出能力`
   用于发现某个频道的最新文章列表

2. `文章详情与正文刷新能力`
   用于获取结构化正文、主动刷新正文、查询刷新状态

需要注意：

- Feed 首次输出时，文章正文未必已经准备好
- 服务端存在后台自动补抓机制，但该机制是周期扫描，不适合作为业务主链路的唯一时序保障
- 因此，业务消费端应自行控制“延迟 + 触发正文刷新 + 轮询 + 读取详情”这条主链路

## 3. 对接原则

### 3.1 外部输入形式

业务消费端可以继续接受用户配置 RSS/Feed URL，例如：

```text
http://127.0.0.1:8001/feed/MP_WXS_3941633310.rss?limit=5
```

### 3.2 内部消费形式

如果识别出该 URL 属于当前 RSS 服务端生成的单频道 Feed，则业务消费端内部应优先将其规范化为 JSON Feed：

```text
http://127.0.0.1:8001/feed/MP_WXS_3941633310.json?limit=5
```

并保留原始查询参数，例如：

- `limit`
- `offset`

### 3.3 为什么内部优先消费 JSON

原因如下：

1. XML/RSS 更适合作为订阅协议，不适合作为内部业务处理格式
2. JSON 更易于直接读取结构化字段
3. XML 解析需要处理 namespace、CDATA、HTML 实体等额外问题
4. JSON 更适合后续串联：
   - 文章发现
   - 文章 ID 提取
   - 延迟调度
   - 正文刷新
   - 详情获取

## 4. 关键接口约定

以下接口都以默认服务端地址 `http://127.0.0.1:8001` 为前缀。

### 4.1 Feed 发现接口

推荐内部使用：

```text
GET /feed/{feed_id}.json?limit=5
```

兼容输入：

```text
GET /feed/{feed_id}.rss?limit=5
GET /feed/{feed_id}.xml?limit=5
```

用途：

- 获取指定频道的最新文章
- 提取文章 ID 与基础元信息

### 4.2 文章详情接口

```text
GET /api/v1/wx/articles/{article_id}
```

用途：

- 获取文章正文
- 获取结构化元信息
- 判断正文是否已就绪

重点字段：

- `id`
- `title`
- `publish_time`
- `url`
- `description`
- `pic_url`
- `has_content`
- `content`
- `content_html`

### 4.3 正文刷新接口

```text
POST /api/v1/wx/articles/{article_id}/refresh
```

用途：

- 主动触发指定文章的正文抓取/刷新

返回结果中应包含：

- `task_id`
- `article_id`
- `status`

### 4.4 刷新任务状态接口

```text
GET /api/v1/wx/articles/refresh/tasks/{task_id}
```

用途：

- 轮询正文刷新任务状态

建议关注状态：

- `pending`
- `running`
- `success`
- `failed`

## 5. 字段消费建议

### 5.1 文章发现阶段

从 Feed 中只取基础字段：

- `id`
- `title`
- `link`
- `description`
- `pubDate` 或 `updated`
- `feed.id`
- `feed.name`

### 5.2 正文消费阶段

优先级如下：

1. `content_html`
   作为优先正文来源
2. `content`
   作为备用正文来源

理由：

- `content_html` 更适合作为下游稳定消费版本
- `content` 更接近原始正文 HTML

### 5.3 正文格式约定

当前按业务约定，应认为：

- `content` 是 HTML 片段，不是纯文本
- `content_html` 也是 HTML
- 正文可能包含：
  - `<img>` 标签
  - `<a>` 标签
  - 各类内联样式
  - 外部图片链接

因此下游不应假设正文已经是纯文本，也不应假设图片 URL 已被替换为本地地址。

## 6. 完整链路设计

### 6.1 主链路

业务消费端按以下步骤执行：

1. 接收用户提供的 RSS/Feed URL
2. 判断该 URL 是否属于当前 RSS 服务端
3. 若属于，则内部规范化为 `.json`
4. 获取最新 `5` 篇文章
5. 对每篇文章：
   - 保存文章 ID
   - 保存首次发现时间
   - 记录当前正文状态为 `unknown`
6. 当某篇文章“首次发现时间 + 10 分钟”到达时：
   - 调用正文刷新接口
   - 记录刷新任务 ID
7. 轮询刷新任务状态
8. 刷新成功后：
   - 拉取文章详情
   - 优先读取 `content_html`
   - 若 `content_html` 为空，则退回 `content`
9. 将正文交给下游加工模块

### 6.2 兜底链路

RSS 服务端本身保留后台自动补抓机制，默认作为兜底，不作为主链路依赖。

约定：

- 自动补抓已启用
- 自动补抓间隔为 `30` 分钟

但业务消费端不应把“等后台自动补抓跑到”作为主流程。

## 7. 状态模型建议

业务消费端内部建议给每篇文章维护一个状态：

```text
discovered
waiting_for_refresh
refresh_requested
refresh_running
refresh_success
refresh_failed
detail_fetched
processed
```

建议状态流转：

```text
discovered
  -> waiting_for_refresh
  -> refresh_requested
  -> refresh_running
  -> refresh_success
  -> detail_fetched
  -> processed
```

失败时：

```text
refresh_requested / refresh_running
  -> refresh_failed
  -> retry_scheduled
```

## 8. 实现伪代码

### 8.1 Feed URL 规范化

```python
def normalize_feed_url(raw_url: str) -> str:
    parsed = parse_url(raw_url)

    if parsed.host not in {"127.0.0.1:8001", "localhost:8001"}:
        return raw_url

    # /feed/{feed_id}.rss
    # /feed/{feed_id}.xml
    # /feed/{feed_id}.atom
    matched = match_feed_path(parsed.path)
    if not matched:
        return raw_url

    feed_id = matched.feed_id
    query = parsed.query
    return build_url(
        host=parsed.host,
        path=f"/feed/{feed_id}.json",
        query=query,
    )
```

### 8.2 拉取最新文章列表

```python
def fetch_latest_articles(feed_url: str) -> list[dict]:
    normalized_url = normalize_feed_url(feed_url)
    payload = http_get_json(normalized_url)

    items = payload.get("items", [])
    result = []
    for item in items[:5]:
        result.append({
            "article_id": item["id"],
            "title": item["title"],
            "link": item["link"],
            "description": item.get("description", ""),
            "published_at": item.get("updated"),
            "discovered_at": now(),
            "feed": item.get("feed"),
        })
    return result
```

### 8.3 延迟调度正文刷新

```python
def schedule_refresh(article: dict):
    run_at = article["discovered_at"] + timedelta(minutes=10)
    delay_queue.enqueue(
        task_name="refresh_article_content",
        run_at=run_at,
        payload={"article_id": article["article_id"]},
    )
```

### 8.4 触发正文刷新

```python
def request_article_refresh(article_id: str) -> str:
    url = f"http://127.0.0.1:8001/api/v1/wx/articles/{article_id}/refresh"
    payload = http_post_json(url)

    task_id = payload["data"]["task_id"]
    return task_id
```

### 8.5 轮询刷新状态

```python
def wait_refresh_result(task_id: str, timeout_seconds: int = 180) -> str:
    deadline = now() + timedelta(seconds=timeout_seconds)

    while now() < deadline:
        url = f"http://127.0.0.1:8001/api/v1/wx/articles/refresh/tasks/{task_id}"
        payload = http_get_json(url)
        status = payload["data"]["status"]

        if status == "success":
            return "success"
        if status == "failed":
            return "failed"

        sleep(3)

    return "timeout"
```

### 8.6 获取文章详情

```python
def fetch_article_detail(article_id: str) -> dict:
    url = f"http://127.0.0.1:8001/api/v1/wx/articles/{article_id}"
    payload = http_get_json(url)
    data = payload["data"]

    return {
        "article_id": data["id"],
        "title": data["title"],
        "published_at": data["publish_time"],
        "url": data["url"],
        "description": data.get("description", ""),
        "has_content": data.get("has_content", 0),
        "content": data.get("content") or "",
        "content_html": data.get("content_html") or "",
    }
```

### 8.7 选择最终正文

```python
def choose_final_content(article_detail: dict) -> str:
    if article_detail["content_html"].strip():
        return article_detail["content_html"]
    return article_detail["content"]
```

### 8.8 总流程

```python
def process_feed(feed_url: str):
    articles = fetch_latest_articles(feed_url)

    for article in articles:
        save_article_if_new(article)
        schedule_refresh(article)


def refresh_and_fetch_detail(article_id: str):
    task_id = request_article_refresh(article_id)
    result = wait_refresh_result(task_id)

    if result != "success":
        mark_refresh_failed(article_id, result)
        return

    detail = fetch_article_detail(article_id)
    final_content = choose_final_content(detail)

    save_article_content(
        article_id=article_id,
        content=final_content,
        raw_content=detail["content"],
        stable_content=detail["content_html"],
    )

    trigger_downstream_processing(article_id)
```

## 9. 异常处理建议

至少处理以下异常：

1. Feed URL 无法识别
2. Feed 返回空列表
3. 文章 ID 缺失
4. 正文刷新接口调用失败
5. 刷新任务超时
6. 刷新任务失败
7. 文章详情接口返回成功但正文仍为空
8. 下游加工失败

建议重试策略：

- 刷新请求失败：重试 `1~3` 次
- 状态轮询超时：记为失败并延后重试
- 详情正文为空：延后重试一次，不要立即判为永久失败

## 10. 验收标准

满足以下条件时，视为该集成方案可用：

1. 输入单频道 RSS URL 后，系统能识别并转换为内部 JSON Feed
2. 能稳定获取最新 `5` 篇文章的基础字段
3. 能以 RSS 首次发现时间为基准，延迟 `10` 分钟触发正文刷新
4. 能正确轮询正文刷新任务状态
5. 能稳定获取文章详情
6. 已补抓文章能优先得到非空 `content_html`
7. 下游不依赖直接解析 RSS XML 正文
8. 正文处理失败时有可观测的失败状态与重试记录

## 11. 当前建议的实现策略

最终建议如下：

- 用户配置层：继续接受 `.rss` URL
- 业务内部发现层：优先转 `.json`
- 正文获取层：统一使用 REST API
- 正文字段优先级：`content_html > content`
- 服务端后台自动补抓：保留，间隔 `30` 分钟，仅作为兜底

