# we-mp-rss Bearer Token API 消费流程

本文档面向“另一个项目”中通过 `Bearer Token` 消费 `we-mp-rss` API 的场景，整理一条可直接落地的标准流程，并附带主要步骤的 `curl` 示例。

> 本文默认服务地址为 `http://localhost:8001`。
> 如果你的环境里 `localhost` 不可用，可替换为 `http://127.0.0.1:8001`。

---

## 1. 目标场景

另一个项目已经拿到了 `we-mp-rss` 生成的单公众号 RSS 地址，例如：

```text
http://localhost:8001/feed/MP_WXS_3201788143.rss
```

现在希望通过 REST API 完成以下事情：

1. 登录并获取 Bearer Token
2. 从 RSS URL 解析出 `mp_id`
3. 获取该公众号详情
4. 触发该公众号文章列表刷新
5. 获取该公众号最新文章列表
6. 对缺正文文章触发单篇正文抓取
7. 轮询正文抓取任务状态
8. 获取文章详情并消费正文

---

## 2. 认证方式

本文统一使用 JWT Bearer Token 认证。

### 2.1 登录获取 access_token

```bash
curl -X POST "http://localhost:8001/api/v1/wx/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=admin&password=admin@123"
```

示例返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "<YOUR_ACCESS_TOKEN>",
    "token_type": "bearer",
    "expires_in": 259200
  }
}
```

### 2.2 后续请求统一带上 Authorization 头

```text
Authorization: Bearer <YOUR_ACCESS_TOKEN>
```

例如：

```bash
curl -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/mps/MP_WXS_3201788143"
```

---

## 3. 从 RSS URL 反推出 mp_id

对于这种 URL：

```text
http://localhost:8001/feed/MP_WXS_3201788143.rss
```

其中：

```text
MP_WXS_3201788143
```

就是该公众号的 `mp_id`。

也就是说：

- RSS URL 中的 `/feed/{feed_id}.rss`
- 这里的 `feed_id`
- 就等于 REST API 里的 `mp_id`

你不需要真的去请求 RSS 内容本身，就可以直接从 URL 路径中解析出这个值。

---

## 4. 推荐的标准调用链路

### Step 1：获取 Bearer Token

```bash
curl -X POST "http://localhost:8001/api/v1/wx/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=admin&password=admin@123"
```

拿到：

- `access_token`

---

### Step 2：获取公众号详情

```bash
curl -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/mps/MP_WXS_3201788143"
```

典型返回字段：

- `id`
- `mp_name`
- `mp_cover`
- `mp_intro`
- `status`
- `sync_time`
- `update_time`
- `created_at`
- `updated_at`
- `faker_id`

示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "MP_WXS_3201788143",
    "mp_name": "PaperWeekly",
    "mp_cover": "http://mmbiz.qpic.cn/...",
    "mp_intro": "PaperWeekly是一个推荐、解读、讨论和报道人工智能前沿论文成果的学术平台...",
    "status": 1,
    "sync_time": 1776820578,
    "update_time": 1776820578,
    "created_at": "2026-04-22T09:16:19",
    "updated_at": "2026-04-22T09:16:19",
    "faker_id": "MzIwMTc4ODE0Mw=="
  }
}
```

> 说明：对外使用时请始终以 `id/mp_id` 为准，不要把 `faker_id` 当成外部主键。

---

### Step 3：触发公众号文章列表刷新

```bash
curl -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/mps/update/MP_WXS_3201788143?start_page=0&end_page=1"
```

典型返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "time_span": 130597,
    "list": [],
    "total": 0,
    "mps": {
      "id": "MP_WXS_3201788143",
      "mp_name": "PaperWeekly"
    }
  }
}
```

> 重要说明：
>
> 这个接口的作用是 **触发刷新**，不是“等待刷新完成并把抓到的文章列表直接返回给你”。
>
> 它在服务端内部是异步线程执行，因此返回里的：
>
> - `list: []`
> - `total: 0`
>
> **不能代表没有刷新到文章**。
>
> 正确做法是：触发后再调用文章列表接口查询结果。

#### 参数说明

- `mp_id`：公众号 ID
- `start_page`：起始页，默认 `0`
- `end_page`：抓取页上限，默认 `1`

当前项目的定时刷新和手动刷新通常都是抓最新一页。

#### 真实刷新逻辑说明

这里需要特别说明：这个接口的默认行为**不是“按自然日刷新当天文章”**，而是：

1. 用 `mp_id` 查到该公众号对应的 `faker_id`
2. 调微信后台的文章列表接口
3. 从 `start_page=0` 开始抓
4. 默认 `end_page=1`，因此只抓**第 1 页**

也就是说，默认语义更接近：

> “回抓该公众号当前最新一页的发布记录”

而不是：

> “只刷新今天发布的文章”

当前代码里，每页请求参数固定 `count=5`。但这个 `5` 对应的是微信接口分页里的**发布单元**，不是严格意义上的“5 篇文章”：

- 在 `web` 模式下，请求的是 `/cgi-bin/appmsgpublish`
- 在 `api` 模式下，请求的是 `/cgi-bin/appmsg`
- 返回中可能存在多图文发布
- 多图文会在服务端被展开成多篇文章写入数据库

所以默认一次刷新通常可以理解为：

- 抓取公众号**最新一页**
- 这一页里默认请求 `count=5`
- 最终入库的“文章篇数”可能**等于或大于 5**

#### “会不会刷新到当天文章”应如何理解

是否覆盖到“当天文章”，取决于当天文章是否还落在公众号发布历史的第一页：

- 如果当天文章都还在第一页内：会刷新到
- 如果当天文章很多，但超出了第一页：默认不会全部覆盖
- 如果当天没有新文章：它仍然会重新检查最新一页，只是大概率不会产生新入库结果

因此外部项目不应把这个接口理解为“按日期范围抓取当天列表”，而应理解为：

> “按页抓取最新发布记录，默认抓第一页”

#### `start_page` / `end_page` 的实际含义

按当前实现，这两个参数更适合理解为“页范围控制”：

- `start_page=0&end_page=1`
  - 抓第 1 页
- `start_page=0&end_page=2`
  - 抓第 1~2 页
- `start_page=1&end_page=2`
  - 抓第 2 页

它们不是“按日期范围”参数，也不是“精确按篇数抓取”的参数。

#### 额外补充：刷新接口还有一个频率限制

接口内部会根据 `mp.update_time` 做一次简单限流；如果距离上次刷新过近，会返回：

- `code = 40402`
- `message = 请不要频繁更新操作`

当前代码里这个保护阈值默认按 `60` 秒处理，因此不建议高频连续触发同一个 `mp_id` 的列表刷新。

---

### Step 4：获取该公众号的文章列表

```bash
curl -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles?mp_id=MP_WXS_3201788143&limit=5&offset=0"
```

如果你只想看“还没有正文”的文章：

```bash
curl -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles?mp_id=MP_WXS_3201788143&has_content=false&limit=5&offset=0"
```

关键字段：

- `id`：文章 ID
- `mp_id`
- `title`
- `url`
- `description`
- `publish_time`
- `has_content`
- `mp_name`

示例片段：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "list": [
      {
        "id": "3201788143-2247719816_1",
        "mp_id": "MP_WXS_3201788143",
        "title": "“蒸馏”学术大牛后，我的论文直接把导师看傻了",
        "url": "https://mp.weixin.qq.com/s/NrDTKwN_T7AfgdKVKAdqhA",
        "has_content": 0,
        "mp_name": "PaperWeekly"
      }
    ],
    "total": 5
  }
}
```

---

### Step 5：触发单篇文章正文抓取/刷新

假设上一步发现一篇文章：

```text
article_id = 3201788143-2247719816_1
```

触发正文抓取：

```bash
curl -X POST \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles/3201788143-2247719816_1/refresh"
```

示例返回：

```json
{
  "code": 0,
  "message": "已开始刷新，请稍后查看",
  "data": {
    "task_id": "1b15f81e-a522-4674-9ac9-8284e8c19616",
    "article_id": "3201788143-2247719816_1",
    "status": "pending",
    "message": "任务已创建"
  }
}
```

你需要关注：

- `task_id`
- `article_id`
- `status`

---

### Step 6：轮询正文刷新任务状态

```bash
curl -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles/refresh/tasks/1b15f81e-a522-4674-9ac9-8284e8c19616"
```

成功时典型返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": "1b15f81e-a522-4674-9ac9-8284e8c19616",
    "article_id": "3201788143-2247719816_1",
    "status": "success",
    "message": "文章刷新成功",
    "updated_at": 1776951230,
    "updated_at_millis": 1776951230515,
    "fetch_mode": "api"
  }
}
```

任务状态重点关注：

- `pending`
- `running`
- `success`
- `failed`

> 实际验证结果表明，当前环境下成功抓取时常见 `fetch_mode = api`。

---

### Step 7：获取文章详情并消费正文

```bash
curl -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles/3201788143-2247719816_1"
```

重点字段：

- `id`
- `title`
- `url`
- `description`
- `publish_time`
- `has_content`
- `content`
- `content_html`

典型行为：

- 刷新前：
  - `has_content = 0`
  - `content = null`
  - `content_html = ""`
- 刷新后：
  - `has_content = 1`
  - `content` / `content_html` 会被填充

在另一个项目中，建议正文消费优先级如下：

1. 优先使用 `content_html`
2. 如果 `content_html` 为空，再退回 `content`

---

## 5. 一个推荐的最小可用流程

对于另一个项目，推荐这样串：

1. 用户配置 RSS URL
2. 从 `/feed/{feed_id}.rss` 中解析出 `mp_id`
3. 登录获取 `access_token`
4. 调 `GET /api/v1/wx/mps/{mp_id}` 确认公众号存在
5. 调 `GET /api/v1/wx/mps/update/{mp_id}` 触发文章列表刷新
6. 调 `GET /api/v1/wx/articles?mp_id={mp_id}` 获取最新文章
7. 遍历文章：
   - 若 `has_content = 1`，可直接消费正文
   - 若 `has_content = 0`，调用单篇刷新接口
8. 轮询正文刷新任务直到 `success`
9. 再调文章详情接口获取正文

---

## 6. 一组可直接抄走的 curl 示例

### 6.1 登录并拿 token

```bash
curl -X POST "http://localhost:8001/api/v1/wx/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=admin&password=admin@123"
```

### 6.2 查公众号详情

```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8001/api/v1/wx/mps/MP_WXS_3201788143"
```

### 6.3 触发公众号文章列表刷新

```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8001/api/v1/wx/mps/update/MP_WXS_3201788143?start_page=0&end_page=1"
```

### 6.4 查该公众号最新文章

```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles?mp_id=MP_WXS_3201788143&limit=5&offset=0"
```

### 6.5 只查缺正文文章

```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles?mp_id=MP_WXS_3201788143&has_content=false&limit=5&offset=0"
```

### 6.6 对某篇文章触发正文抓取

```bash
curl -X POST \
  -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles/3201788143-2247719816_1/refresh"
```

### 6.7 查询正文刷新任务状态

```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles/refresh/tasks/<TASK_ID>"
```

### 6.8 获取文章详情

```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8001/api/v1/wx/articles/3201788143-2247719816_1"
```

---

## 7. 验证结论摘要

基于当前本地环境的实际验证，已经确认：

1. `mp_id` 和 RSS URL 中的 `feed_id` 相同
2. `GET /api/v1/wx/mps/{mp_id}` 可以返回公众号详情
3. `GET /api/v1/wx/mps/update/{mp_id}` 可以触发该公众号文章列表刷新
4. 该刷新接口是异步触发，不直接返回最终文章结果
5. `GET /api/v1/wx/articles?mp_id=...` 可以查到该公众号文章列表
6. `POST /api/v1/wx/articles/{article_id}/refresh` 可以触发单篇正文抓取
7. 对 `has_content = 0` 的文章，正文抓取成功后会变成 `has_content = 1`

---

## 8. 注意事项

1. 某些详情接口当前可能不强制认证，但建议外部项目统一都带 `Bearer Token`
2. `/mps/update/{mp_id}` 的返回值不能当作“刷新完成结果”使用
3. 正文抓取是文章级行为，不是公众号级批量正文刷新
4. 如果需要批量补正文，请先查出 `has_content = 0` 的文章，再逐篇调用刷新接口
5. 默认服务地址可用：
   - `http://localhost:8001`
   - 不通时可改为 `http://127.0.0.1:8001`
