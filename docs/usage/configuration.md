# 配置参考

在 AstrBot 管理面板中配置以下选项。

## 基础配置

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `api_type` | 字符串 | API 类型 | `lolicon` / `atri` / `sexnyan` / `custom` / `all` | `lolicon` |
| `send_mode` | 字符串 | 色图发送模式 | `auto` / `image` / `forward` | `auto` |
| `content_mode` | 字符串 | 内容模式 | `sfw` / `r18` / `mix` | `sfw` |
| `max_count` | 整数 | 单次最大图片数 | 1-10 | `10` |
| `max_replenish_rounds` | 整数 | 下载暂时失败时的同 URL 确认尝试次数，也是短缺时的补图轮次 | 1-3 | `3` |
| `cache_enabled` | 布尔值 | 是否复用本地发送缓存 | `true` / `false` | `true` |
| `exclude_ai` | 布尔值 | 是否排除 AI 生成图片 | `true` / `false` | `true` |

图片 URL 已返回但下载出现连接错误、HTTP 错误或超时时，插件会先按 `max_replenish_rounds` 对同一 URL 做可观测的确认重试。仍失败时才进入后续补图轮次或返回无结果，避免 CDN/反代短暂抖动被直接当成最终失败。

## HTML 卡片与防审核配置

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `doujinshi_send_mode` | 字符串 | 随机本子文件格式；两种模式都直接发送普通文件 | `pdf` / `archive` | `pdf` |
| `doujinshi_max_page` | 整数 | 随机本子最大页数，超过该页数的本子会被 API 过滤 | ≥0，`0` 表示不限 | `0` |
| `html_card_strategy` | 字符串 | HTML 卡片策略 | `never` / `fallback` / `always` | `fallback` |
| `platform_transports` | template_list | 平台传输能力模板；当前内置 NapCat 模板 | 见下文 | `[]` |
| `auto_revoke_targets` | 列表 | 自动撤回内容 | `setu` / `fortune` / `doujinshi` | `["doujinshi"]` |
| `auto_revoke_scope` | 字符串 | Setu 图片自动撤回范围 | `none` / `sfw` / `r18` / `all` | `none` |
| `auto_revoke_delay` | 整数 | 已启用内容共用自动清理延迟（秒） | ≥0，`0` 全部关闭 | `30` |
| `r18_docx_mode` | 布尔值 | R18 是否使用 Docx 封装 | `true` / `false` | `true` |

R18 请求开启 `delivery.r18_docx_mode`（会话配置为 `setu.r18_docx`）后，
全部图片按获取顺序封装为一个 DOCX，通过普通文件发送。JPEG、PNG 直接嵌入，
WebP 等格式转换为 PNG；图片按页面可用范围等比缩放。
生成或发送确认失败使用 `messages.r18_docx_failed` 提示并结束当前发送，
确认超时保留 pending 状态，避免重复发送。SFW 和关闭 DOCX 时沿用图片发送。
自动撤回仍受 `auto_revoke_targets`、范围和延时控制。
文件在插件数据目录的 `send_cache/` 保留缓存 TTL 后清理，即使图片缓存关闭仍执行清理；
DOCX 在 TTL 内免于容量淘汰，以保留异步文件上传所需路径。

### HTML 卡片策略详解

| 策略 | 说明 |
|------|------|
| `never` | 从不使用 HTML 卡片，直接发送原图 |
| `fallback`（默认） | 确认发送失败时自动降级为 HTML 卡片 |
| `always` | 总是使用 HTML 卡片包装发送 |

发送接口超时或 OneBot/NapCat 类适配器未返回 message id 时，插件会把结果标记为“可能仍在送达”，不会立刻触发 NapCat 流式或 HTML 卡片 fallback，避免原图稍后送达时又重复发送降级图片。明确抛出的发送异常仍会进入原有 fallback 链路。

### 自动撤回内容与范围

先用一个 `auto_revoke_targets` 列表选择内容，每行填写一个值：`setu`（色图）、`fortune`（今日运势）或 `doujinshi`（随机本子）。默认值为 `["doujinshi"]`，所以色图和今日运势默认禁用，本子默认启用。

`auto_revoke_scope` 只作用于列表中已启用的 `setu` 图片发送，不作用于今日运势或本子。可选值：

| 值 | 说明 |
|----|------|
| `none` | 不自动撤回 |
| `sfw` | 只撤回 SFW Setu 图片 |
| `r18` | 只撤回 R18 Setu 图片或 R18 Docx 文件 |
| `all` | SFW 与 R18 Setu 发送都撤回 |

色图和今日运势的消息撤回依赖 OneBot-like 平台返回的 `message_id`。如果平台不支持 `delete_msg`、发送返回里没有 `message_id`，或删除失败，插件只记录 warning，不阻止消息发送。已登记的撤回任务会写入插件数据目录中的 `revoke_tasks.json`，插件退出时仅停止内存计时，重启后仍按原到期时间恢复。旧版 `delivery.auto_revoke_r18` 启动时会迁移为 `auto_revoke_scope`：`true` → `r18`，`false` → `none`，迁移后旧字段会被移除。

### 随机本子文件格式

`delivery.doujinshi_send_mode` 控制本子生成的文件类型：

| 值 | 行为 |
|----|------|
| `pdf`（默认） | 下载全部页图并生成一个多页 PDF，文件名为本子标题加 `.pdf` |
| `archive` | 下载全部页图并生成一个 ZIP 压缩包，成员按页码顺序命名，文件名为本子标题加 `.zip` |

两种模式都会在所有平台通过普通 `File` 消息发送，不再使用 OneBot `Nodes` 合并转发，也不再追加标题/原始地址节点。

`delivery.doujinshi_max_page` 限制本子最多包含的页数：大于 `0` 时作为 `max_page` 查询参数传给 Atri 随机本子 API，超过该页数的本子会被 API 过滤；`0` 表示不限制（不传 `max_page` 参数）。

### 自动撤回与本子文件

`auto_revoke_delay` 同时控制 `auto_revoke_targets` 中启用的 Setu 图片、今日运势消息和 OneBot/NapCat 群聊中的随机本子普通文件消息。默认 `30` 秒；设为 `0` 会关闭全部自动清理；如需 30 分钟，设为 `1800`。旧 `doujinshi_file_cleanup_delay` 会在插件启动时迁移到新字段；两者同时存在时以 `auto_revoke_delay` 为准。

待撤回记录统一保存于插件运行数据目录的 `revoke_tasks.json`。本子发送时会直接调用 OneBot `send_group_msg` 取得普通文件消息的 `message_id`，并立即将撤回任务持久化；到期后统一调用 `delete_msg`。插件不依赖 `get_group_root_files`、文件名或体积反查群文件，因此不会把合并转发附件误当作群文件处理。插件退出或重启只停止内存计时，下一次初始化会按原绝对到期时间恢复；已有 `doujinshi_file_cleanup_tasks.json` 会迁移到统一队列。OneBot action 不可用、发送结果没有 `message_id` 或删除 action 返回错误时，任务会保留并记录 warning，不会重复发送。实际到期删除失败时，任务会将连续失败次数持久化；前两次失败保留以便下次插件启动恢复，第三次连续失败会自动从 `revoke_tasks.json` 移除，避免无效任务无限累积。启用本子自动撤回后，发送成功会立即写入该文件并记录“已登记本子文件自动撤回”日志；若没有任务记录，可从 warning 区分调度器、插件上下文或 `message_id` 缺失的原因。

旧版本已经写入的 `group_file` 任务没有对应的普通消息 `message_id`，也无法从空的群文件接口反向取得它；插件会保留这些旧任务，避免静默丢失状态。需要先在 QQ 客户端手动处理旧附件，再按需清理对应的旧任务记录。

### NapCat 本地文件直通

标准 AstrBot OneBot 发送链路会把 `Image` 转成 `base64://`，因此只把图片做成 `file://` 组件并不能绕过 base64。在 `platform_transports` 添加 NapCat 模板并启用 `local_file_mode` 后，插件会在直发模式下改走 raw OneBot 图片 action，把受信任本地文件路径作为 `file://` 交给 NapCat 读取。

| NapCat 模板字段 | 类型 | 说明 | 可选值 | 默认值 |
|-----------------|------|------|--------|--------|
| `stream_mode` | 字符串 | NapCat 流式上传策略 | `disabled` / `fallback` / `always` | `fallback` |
| `stream_chunk_kb` | 整数 | NapCat stream 单块原始字节大小（KiB） | ≥1 | `64` |
| `local_file_mode` | 字符串 | NapCat 本地 `file://` 直通策略 | `disabled` / `fallback` / `always` | `disabled` |
| `local_file_allowed_roots` | 列表 | NapCat 也能读取的额外共享目录 | 绝对路径列表 | `[]` |

| 策略 | 说明 |
|------|------|
| `disabled`（默认） | 保持现有 base64 链路 |
| `fallback` | 确认普通发送失败后先尝试 `file://` 直通，再尝试 stream / HTML |
| `always` | 直发模式优先尝试 `file://` 直通，失败后回到原链路 |

只有满足以下条件时才会直通：平台为 OneBot/NapCat 类；图片是本地真实文件；路径 resolve 后位于发送缓存目录或 NapCat 模板的 `local_file_allowed_roots` 中。Docker 部署需要 AstrBot 与 NapCat 共享同一路径，例如都能读取 `/AstrBot/data`。

NapCat `upload_file_stream` 的 `chunk_data` 仍是 base64 字符串，这是 NapCat 当前接口约束；`stream_chunk_kb` 只控制每个 base64 分块对应的原始字节大小。旧版 `delivery.napcat_*` 平铺字段仍会被读取作为兼容兜底，新配置建议使用 `platform_transports`。

## 模板覆盖配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `provider_overrides` | template_list | 可选覆盖 provider 默认参数；Lolicon/Atri 支持图片尺寸、代理、UID、关键词、AI 过滤，SexNyan 支持代理、作者 UID、关键词 |
| `custom_api_configs` | template_list | 自定义图片 API 列表 |
| `tag_alias_templates` | template_list | 标签别名映射；添加后优先于旧文本格式 `tag_alias` |
| `message_overrides` | template_list | 只在需要关闭或自定义某条提示时添加；所有内置提示默认启用并带默认文本 |

访问控制 Web API 错误提示也可通过 `message_overrides` 覆盖，内置键为 `error.invalid_request` 和 `error.internal_server`。
自动撤回成功调度后的提示 key 为 `revoke_scheduled`，占位符支持 `{count}`、`{revoke_delay}`、`{scope}`、`{r18}`，默认启用。

## 访问控制配置

安全配置已从 `_conf_schema.json` 移到插件 WebUI 的 Dashboard 访问控制标签页。页面支持：

- 设置 Setu/运势的用户、群组访问模式：`none` / `blacklist` / `whitelist`
- 用表格新增、编辑、删除用户/群组黑白名单
- 按功能、对象类型、名单类型筛选并搜索 ID 或备注

访问控制数据写入插件数据目录，不再写回全局配置面板。旧版 `safety.*` 配置会在初始化时导入一次，确保已有黑白名单和模式不丢失。

### 访问控制模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `none` | 不启用该维度的黑白名单检查 | 不限制该维度 |
| `blacklist` | 命中黑名单即拒绝 | 只屏蔽少数对象 |
| `whitelist` | 不在白名单即拒绝 | 仅允许特定对象 |

### 判定规则

- 用户和群组分别按各自模式独立判定；任一维度拒绝则最终拒绝。
- `setu` 与 `fortune` 的名单和模式互不影响。
- 用户白名单**不再**具有"跳过群组限制"的特权。
- 当同一用户被"拉黑"后又"信任"（或反向操作）时，会自动从对立名单移除，保持互斥。

## 性能优化配置

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `platform_transports.napcat.stream_mode` | NapCat/OneBot 图片传输策略 | `fallback` |
| `platform_transports.napcat.stream_chunk_kb` | NapCat stream 单块大小；接口仍为 base64 分块 | `64` 起，网络稳定可逐步增大 |
| `platform_transports.napcat.local_file_mode` | 共享路径部署下绕过 AstrBot 标准 base64 链路 | 已确认共享目录后用 `always` |
| `cache_enabled` | 是否复用发送缓存 | `true` |
| `max_replenish_rounds` | 图片 URL 短暂下载失败时的确认重试和补图轮次 | `3` |

## 配置示例

```json
{
  "setu_general": {
    "api_type": "lolicon",
    "content_mode": "mix",
    "max_count": 5
  },
  "delivery": {
    "send_mode": "auto",
    "doujinshi_send_mode": "pdf",
    "doujinshi_max_page": 0,
    "auto_revoke_targets": ["setu", "doujinshi"],
    "auto_revoke_scope": "r18",
    "auto_revoke_delay": 1800,
    "r18_docx_mode": false
  },
  "messages": {
    "message_overrides": [
      {
        "__template_key": "message",
        "message_key": "fetch_failed",
        "enabled": true,
        "text": "获取图片失败，请稍后再试"
      }
    ]
  }
}
```
