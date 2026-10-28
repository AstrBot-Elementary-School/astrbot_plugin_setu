# 配置参考

在 AstrBot 管理面板的插件配置中修改以下选项，保存后重载插件生效。全局设置、会话覆盖和访问控制都使用这一个入口。

## 界面顺序

配置按“图片获取、发送与撤回、今日运势、会话设置、访问控制、图片来源高级设置”排列。先设置图片分级、数量和发送方式；只有需要调整标签别名、压缩、卡片或平台传输时，再打开对应区域的“显示更多配置”。

关闭运势、压缩或会话标签覆盖时，相关输入会隐藏；权限名单只显示当前模式使用的一份。隐藏不会清空已有值，切换回来仍可继续使用。

## 图片获取

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `api_type` | 字符串 | API 类型 | `lolicon` / `sexnyan` / `custom` / `all` | `lolicon` |
| `send_mode` | 字符串 | 色图发送模式 | `auto` / `image` / `forward` | `auto` |
| `content_mode` | 字符串 | 内容模式 | `sfw` / `r18` / `mix` | `sfw` |
| `max_count` | 整数 | 单次最大图片数 | 1-10 | `10` |
| `exclude_ai` | 布尔值 | 是否排除 AI 生成图片 | `true` / `false` | `true` |

图片 URL 已返回但下载出现连接错误、HTTP 错误或超时时，插件会先按内部默认的 3 轮对同一 URL 重试，并记录结果。仍失败时才进入后续补图轮次或返回无结果，避免 CDN/反代短暂抖动被直接当成最终失败。

### 功能开关与短语

在“图片获取”的更多配置中：

- `setu_general.llm_tools_enabled`：默认 `true`，关闭后不注册插件工具，命令仍可用。
- `setu_general.natural_language_enabled`：默认 `true`，只控制短语触发。
- `setu_general.trigger_templates`：按顺序匹配整句，首次匹配后停止。默认含 `setu`、`doujinshi`、`fortune` 三条空短语规则，分别沿用原有语法；填写短语替换该条语法，删除全部规则表示不提供自然语句入口。

图片模板可用 `{数量}`、`{标签}`，本子仅可用 `{标签}`，运势不接受占位符。数量省略为 1，标签省略为空；重复、未知占位符及格式修饰报错。文字按字面匹配，不开放正则。例如：

```json
"trigger_templates": [
  {"__template_key": "setu", "phrase": "给我{数量}张{标签}图片"},
  {"__template_key": "doujinshi", "phrase": "找本{标签}本子"},
  {"__template_key": "fortune", "phrase": "看看今天运气"}
]
```

命令、图片短语和图片工具都接受独立的 `r18` 标签，大小写不限；它不参与标签别名和图片源搜索，仅影响本次请求。生效会话分级为 SFW 时，在访问图片源前拒绝。

## 发送与撤回

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `doujinshi_send_mode` | 字符串 | 随机本子文件格式；两种模式都直接发送普通文件 | `pdf` / `archive` | `pdf` |
| `doujinshi_max_page` | 整数 | 随机本子最大页数，超过该页数的本子会被 API 过滤 | ≥0，`0` 表示不限 | `0` |
| `delivery.html_card_strategy` | 字符串 | 图片卡片发送方式 | `never` / `fallback` / `always` | `fallback` |
| `platform_transports` | template_list | 平台传输能力模板；当前内置 NapCat 模板 | 见下文 | `[]` |
| `auto_revoke_targets` | 列表 | 自动撤回内容 | `setu` / `fortune` / `doujinshi` | `["doujinshi"]` |
| `auto_revoke_scope` | 字符串 | Setu 图片自动撤回范围 | `none` / `sfw` / `r18` / `all` | `none` |
| `auto_revoke_delay` | 整数 | 已启用内容共用自动清理延迟（秒） | ≥0，`0` 全部关闭 | `30` |
| `r18_docx_mode` | 布尔值 | R18 是否使用 Docx 封装 | `true` / `false` | `true` |

R18 请求开启 `delivery.r18_docx_mode`（会话配置为 `setu.r18_docx`）后，
全部图片按获取顺序封装为一个 DOCX，通过普通文件发送。JPEG、PNG 直接嵌入，
WebP 等格式转换为 PNG；图片按页面可用范围等比缩放。
生成或发送确认失败使用内置 `r18_docx_failed` 提示并结束当前发送，
确认超时保留 pending 状态，避免重复发送。SFW 和关闭 DOCX 时沿用图片发送。
自动撤回仍受 `auto_revoke_targets`、范围和延时控制。
文件在插件数据目录的 `send_cache/` 保留缓存 TTL 后清理，即使图片缓存关闭仍执行清理；
DOCX 在 TTL 内免于容量淘汰，以保留异步文件上传所需路径。

### HTML 卡片发送

| 策略 | 说明 |
|------|------|
| `never` | 从不使用 HTML 卡片，直接发送原图 |
| `fallback`（默认） | 确认发送失败时自动降级为 HTML 卡片 |
| `always` | 总是使用 HTML 卡片包装发送 |

发送接口超时或 OneBot/NapCat 类适配器未返回 message id 时，插件会把结果标记为“可能仍在送达”，不会立刻触发 NapCat 流式或 HTML 卡片 fallback，避免原图稍后送达时又重复发送降级图片。明确抛出的发送异常仍会进入原有 fallback 链路。

### 自动撤回内容与范围

先用一个 `auto_revoke_targets` 列表选择内容，每行填写一个值：`setu`（色图）、`fortune`（今日运势）或 `doujinshi`（随机本子）。默认值为 `["doujinshi"]`，所以默认只撤回本子消息，不撤回色图和今日运势。

`auto_revoke_scope` 只作用于列表中已启用的 `setu` 图片发送，不作用于今日运势或本子。可选值：

| 值 | 说明 |
|----|------|
| `none` | 不自动撤回 |
| `sfw` | 只撤回 SFW Setu 图片 |
| `r18` | 只撤回 R18 Setu 图片或 R18 Docx 文件 |
| `all` | SFW 与 R18 Setu 发送都撤回 |

色图和今日运势的消息撤回依赖 OneBot-like 平台返回的 `message_id`。如果平台不支持 `delete_msg`、发送返回里没有 `message_id`，或删除失败，插件只记录 warning，不阻止消息发送。已登记的撤回任务会写入插件数据目录中的 `revoke_tasks.json`，插件退出时仅停止内存计时，重启后仍按原到期时间恢复。旧版 `delivery.auto_revoke_r18` 启动时会迁移为 `auto_revoke_scope`：`true` → `r18`，`false` → `none`，迁移后旧字段会被移除。

### 随机本子文件格式

`delivery.doujinshi_enabled` 位于更多配置，默认 `true`。关闭后命令和短语只提示停用，不下载或生成文件；已有文件和持久化撤回任务保留。

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
| `local_file_mode` | 字符串 | NapCat 本地 `file://` 直通策略 | `disabled` / `fallback` / `always` | `disabled` |
| `local_file_allowed_roots` | 列表 | NapCat 也能读取的额外共享目录 | 绝对路径列表 | `[]` |

| 策略 | 说明 |
|------|------|
| `disabled`（默认） | 保持现有 base64 链路 |
| `fallback` | 确认普通发送失败后先尝试 `file://` 直通，再尝试 stream / HTML |
| `always` | 直发模式优先尝试 `file://` 直通，失败后回到原链路 |

只有满足以下条件时才会直通：平台为 OneBot/NapCat 类；图片是本地真实文件；路径 resolve 后位于发送缓存目录或 NapCat 模板的 `local_file_allowed_roots` 中。Docker 部署需要 AstrBot 与 NapCat 共享同一路径，例如都能读取 `/AstrBot/data`。

NapCat `upload_file_stream` 的 `chunk_data` 仍是 base64 字符串，这是 NapCat 当前接口约束；分块原始字节大小固定为 64 KiB。旧版 NapCat 传输模式和本地路径字段仍作为兼容兜底，分块大小不再读取旧值，新配置建议使用 `platform_transports`。

## 模板覆盖配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `provider_overrides` | template_list | 可选覆盖 provider 默认参数；Lolicon 支持图片尺寸、代理、UID、关键词、AI 过滤，SexNyan 支持代理、作者 UID、关键词 |
| `custom_api_configs` | template_list | 自定义图片 API 列表 |
| `tag_alias_templates` | template_list | 标签别名映射；添加后优先于旧文本格式 `tag_alias` |

## 会话级覆盖

要让某个群聊使用不同的发送方式，在 `session_configs` 添加“图片与发送”，填写完整 `session_id`，把发送模式设为 `forward`，其他字段保持 `inherit`。

`session_id` 使用 AstrBot 事件的 `unified_msg_origin`，可从 AstrBot 会话信息或事件日志取得，例如 `bot:GroupMessage:123`。必须完整匹配平台实例、消息类型和目标；裸群号不会跨平台匹配。

两种模板均允许同一会话各一条，重复条目或非法值会阻止初始化并报告错误：

- `setu`：`content_mode`、`send_mode`、`r18_docx_mode`、`auto_revoke_scope`。默认 `inherit`；Docx 可选字符串 `true`／`false`，以区分显式关闭和继承。
- `fortune`：背景 `content_mode`，默认 `inherit`；`override_tags` 默认 `false`；开启后使用 `tags`，即使 `tags` 为空也会覆盖全局标签。

撤回范围仅过滤已在全局 `auto_revoke_targets` 启用的色图，不会单独开启撤回。删除模板恢复全局值，业务命令和 LLM 工具都使用相同的生效配置。

运势预生成使用记录中的完整会话标识；旧记录缺少标识时继承全局。运势和图片缓存仍按用户与日期归属，不是每群独立一份；新配置不会主动清空今日卡片，需等待重新生成或使用运势刷新操作。

## 访问控制

`safety` 使用 `template_list`，仅提供“色图与随机本子”和“今日运势”两种模板，每种最多一条。每条模板包含：

- `mode`：`none`（不限）、`blacklist`（命中黑名单拒绝）、`whitelist`（仅允许白名单）。
- `blocked_sids`：黑名单，每行一个完整 SID。
- `whitelist_sids`：白名单，每行一个完整 SID。

SID 使用 AstrBot 的完整 `unified_msg_origin`（`平台:消息类型:会话ID`）。同号的其他平台、群聊与私聊互不匹配；群聊规则适用于整个群，不再支持在群内单独拉黑某个成员。Setu 规则同时约束随机本子。

未添加模板的功能不限；空白名单会拒绝该功能的所有会话。黑白名单不能重叠，重复模板、裸 ID 和非法模式都会报错。运势预生成同样检查记录中的 SID；配置限制时缺少 SID 的旧记录会跳过，不绕过权限。

```json
"safety": [
  {
    "__template_key": "setu",
    "mode": "whitelist",
    "whitelist_sids": ["aiocqhttp:GroupMessage:123456"]
  }
]
```

## 内部默认与内置提示

以下不再开放配置：缓存开启、TTL 2 小时、容量 200 条、启动清理；卡片间距和内边距均为 6；流式分块 64 KiB；补图轮次 3。旧调优值停止生效，传输模式和本地共享目录白名单仍可配置。

提示集中保存在 `src/shared/config/messages.py`，通过 `resolve_message()` 替换 `{count}`、`{max_count}`、`{min_count}`、`{error}`、`{tags_info}`、`{revoke_delay}`、`{feature}` 等占位符；运势发图结果提示 `fortune_image_submitted`、`fortune_image_failed` 使用 `{fortune}`。提示固定启用，旧 `messages` 与 `message_overrides` 不再影响输出。

## 今日运势

命令与 LLM 工具共用运势图片发送流程，支持现有压缩与平台传输设置。运势卡片始终直发，不使用色图的合并转发或 R18 Word 包装；是否撤回只由 `auto_revoke_targets` 中的 `fortune` 决定。渲染或图片发送失败时提供文字运势。

背景图片使用“图片获取”中选择的图片来源，可单独设置分级和标签。关闭运势时，其余选项隐藏。

关闭 `fortune.enabled` 会停用获取、刷新、运势工具和后台预生成，不初始化运势数据库或渲染器；已有运势和缓存保留，持久化撤回任务照常恢复。

更多配置中的 `fortune.allow_user_refresh` 默认关闭；开启后普通用户可刷新自己的运势，但仍须通过运势 SID 权限检查。本群刷新仍需管理员，全局刷新仍需超级管理员。“后台预生成运势”（`fortune.auto_refresh`）控制每日零点为近期活跃用户生成运势及图片缓存。关闭预生成不会关闭主动获取运势，也不表示沿用前一天的运势。

## 升级与恢复

Atri 内置图片源已移除，`all` 只轮流使用 Lolicon 和 SexNyan。旧 `setu_general.api_type=atri` 在配置自愈前迁为 `lolicon` 并保存，日志会提示；保存失败则停止初始化。已有 Lolicon 参数、分级和 SID 权限保留，Atri 专属参数删除，不映射给其他来源。自定义 API 不限制地址中是否包含 Atri。随机本子仍调用 Atri 服务，需关闭 `delivery.doujinshi_enabled` 才能停用这条下载入口。

卡片配置由 `html_card.strategy` 迁入 `delivery.html_card_strategy`；新旧路径都有值时使用新路径，保存成功后移除旧字段。有效默认仍为 `fallback`。Schema 的新字段使用空值作为迁移占位，避免 AstrBot 提前补默认值覆盖旧设置；初始化后会写入实际值。隐藏的旧字段仅用于升级，不是配置入口。

`setu_general.multi_api_strategy` 与 `fortune.api_type` 不再生效：多个图片源固定轮流使用，运势使用全局图片源。

首次升级从 `StarTools.get_data_dir(self.name)` 返回的运行目录读取旧 `config.json` 和 `session_overrides.json`，将会话覆盖迁入插件配置。同一会话、同一字段冲突时以原 Pages 有效值为准，非冲突模板字段保留；旧撤回布尔值转换为 `r18`／`none`。

旧平铺权限或四种用户／群组模板中的裸 ID 无法推导完整 SID。存在限制模式或任何名单（包括未启用名单）时会明确报错，保留原文件和配置；请在插件配置 `safety` 中明确填写新的 SID 模板，作为对旧权限的替换，然后重载。无权限规则时迁为空列表。

完整读取和校验成功后才保存插件配置，保存成功后才写入 `config_templates_migrated_v1` 标记。读取、校验、保存或标记失败均会报错并停止初始化；先修复日志中的文件或值再重载，不要以清空旧文件绕过失败。

迁移完成后只读插件配置，清空名单或删除模板不会重新导入。旧运行文件保留，供需要回退旧版本时恢复；回退后如再升级，需要先备份并核对两边配置，再决定是否删除迁移标记重新导入，避免覆盖新设置。插件不提供配置修改命令或配置修改 LLM 工具，也不再提供 Pages 页面。

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
  "session_configs": [
    {
      "__template_key": "setu",
      "session_id": "bot:GroupMessage:123",
      "send_mode": "forward",
      "content_mode": "sfw"
    },
    {
      "__template_key": "fortune",
      "session_id": "bot:GroupMessage:123",
      "override_tags": true,
      "tags": "猫耳"
    }
  ]
}
```
