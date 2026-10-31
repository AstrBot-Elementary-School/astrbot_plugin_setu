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
文件写入 `cache/setu/`，发送期间持有使用权；缓存关闭时，收到发送确认后删除。确认待定时保留文件，避免平台仍在读取时被删除。

### 自动撤回内容与范围

先用一个 `auto_revoke_targets` 列表选择内容，每行填写一个值：`setu`（色图）、`fortune`（今日运势）或 `doujinshi`（随机本子）。默认值为 `["doujinshi"]`，所以默认只撤回本子消息，不撤回色图和今日运势。

`auto_revoke_scope` 只作用于列表中已启用的 `setu` 图片发送，不作用于今日运势或本子。可选值：

| 值 | 说明 |
|----|------|
| `none` | 不自动撤回 |
| `sfw` | 只撤回 SFW Setu 图片 |
| `r18` | 只撤回 R18 Setu 图片或 R18 Docx 文件 |
| `all` | SFW 与 R18 Setu 发送都撤回 |

色图和今日运势的消息撤回依赖 OneBot-like 平台返回的 `message_id`。已登记任务保存在统一数据库的 `setu_schedule_task` 表，重启后按原到期时间恢复。执行失败记录完整错误，沿用现有连续失败处理规则。

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

`auto_revoke_delay` 控制已启用内容的清理延迟，默认 30 秒，`0` 关闭。新的本子任务通过普通文件消息的 `message_id` 调用 `delete_msg`。历史群文件任务按实际目标导入，保留执行所需字段；缺少必要 SID 信息时迁移停止并完整报告源任务。

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
| `fallback` | 确认普通发送失败后先尝试 `file://` 直通，再尝试 stream |
| `always` | 直发模式优先尝试 `file://` 直通，失败后回到原链路 |

只有满足以下条件时才会直通：平台为 OneBot/NapCat 类；图片是本地真实文件；路径 resolve 后位于发送缓存目录或 NapCat 模板的 `local_file_allowed_roots` 中。Docker 部署需要 AstrBot 与 NapCat 共享同一路径，例如都能读取 `/AstrBot/data`。

NapCat `upload_file_stream` 的 `chunk_data` 使用 base64 字符串；分块原始字节大小固定为 64 KiB，传输配置只读取 `platform_transports`。

## 模板覆盖配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `provider_overrides` | template_list | 可选覆盖 provider 默认参数；Lolicon 支持图片尺寸、代理、UID、关键词、AI 过滤，SexNyan 支持代理、作者 UID、关键词 |
| `custom_api_configs` | template_list | 自定义图片 API 列表 |
| `tag_alias_templates` | template_list | 标签别名映射；按模板配置别名 |

## 会话级覆盖

要让某个群聊使用不同的发送方式，在 `session_configs` 添加“图片与发送”，填写完整 `session_id`，把发送模式设为 `forward`，其他字段保持 `inherit`。

`session_id` 使用 AstrBot 事件的 `unified_msg_origin`，可从 AstrBot 会话信息或事件日志取得，例如 `bot:GroupMessage:123`。必须完整匹配平台实例、消息类型和目标；裸群号不会跨平台匹配。

两种模板均允许同一会话各一条，无效字段恢复默认，无法识别的条目丢弃：

- `setu`：`content_mode`、`send_mode`、`r18_docx_mode`、`auto_revoke_scope`。默认 `inherit`；Docx 可选字符串 `true`／`false`，以区分显式关闭和继承。
- `fortune`：背景 `content_mode`，默认 `inherit`；`override_tags` 默认 `false`；开启后使用 `tags`，即使 `tags` 为空也会覆盖全局标签。

撤回范围仅过滤已在全局 `auto_revoke_targets` 启用的色图，不会单独开启撤回。删除模板恢复全局值，业务命令和 LLM 工具都使用相同的生效配置。

运势以 `(session_id, user_id, date)` 唯一保存，同平台各会话的星级独立。个人偏好跨会话共享，命令见[个人运势偏好](commands.md#个人运势偏好)。

## 访问控制

`safety` 使用 `template_list`，仅提供“色图与随机本子”和“今日运势”两种模板，每种最多一条。每条模板包含：

- `mode`：`none`（不限）、`blacklist`（命中黑名单拒绝）、`whitelist`（仅允许白名单）。
- `blocked_sids`：黑名单，每行一个完整 SID。
- `whitelist_sids`：白名单，每行一个完整 SID。

SID 使用 AstrBot 的完整 `unified_msg_origin`（`平台:消息类型:会话ID`）。同号的其他平台、群聊与私聊互不匹配；群聊规则适用于整个群，不再支持在群内单独拉黑某个成员。Setu 规则同时约束随机本子。

未添加模板的功能默认开放；空白名单拒绝全部会话。非法权限值恢复默认，可能使访问范围回到开放状态，保存或升级后请检查实际规则。

```json
"safety": [
  {
    "__template_key": "setu",
    "mode": "whitelist",
    "whitelist_sids": ["aiocqhttp:GroupMessage:123456"]
  }
]
```

## 缓存与数据保留

`cache.setu`、`cache.fortune`、`cache.doujinshi` 默认均为 `false`，可分别开启。三类文件与临时文件共用固定 512 MiB 硬上限；优先淘汰最旧的闲置文件，正在发送或上传的文件保持可用。空间不足时终止本次写入并报告原因。关闭缓存时，发送确认后删除临时文件；确认待定的本地文件保留到本次插件卸载，避免平台读取中断；重载后纳入容量淘汰。

`daily_fortune` 和 `setu_history` 保留包含当天的滚动 30 天。启动及跨日后首次数据访问先清理过期运势，再清理过期且未被运势引用的图片历史及关联文件。

普通提示位于 `src/shared/config/messages.py`；各主题运势标题、正文位于 `src/template/fortune/<主题>/text.json`。`messages` 和 `tip` 均按字符串键 `"0"`～`"7"` 对应星级，每组先提供三条备选文案；每次渲染时分别随机抽取一条正文和寄语。开启运势缓存后会复用已生成的卡片。固定标识、装饰文字和图片说明直接写在主题的 `index.jinja2` 中。

## 今日运势

`fortune.card_theme` 为默认主题，默认 `endfield`。可选 `arona`、`endfield`、`persona5`、`minecraft`、`minimal`、`random`；随机主题从五个保留主题中选择。模板统一位于 `src/template/fortune/<主题>/index.jinja2`，样式为 `index.css`。

配置面板将 `random` 显示为“随机”，每次查看随机选择主题，沿用当天星级。每个主题另有 `template.yaml`，记录 `version`（初始为 `"0.1"`）、`name`、`aliases`、`author`。插件当前只使用 `aliases` 解析偏好命令中的主题别名；编辑后重载插件生效。

主题优先使用个人偏好。背景搜索标签按“个人偏好 → 当前 SID 会话配置 → 插件默认值”生效，分级继续受会话配置和权限约束。后端保存每日星级与背景历史关联，切换主题保持星级。

`fortune.enabled=false` 时移除运势入口和工具，跳过运势处理器与渲染器初始化。统一数据库和撤回调度照常初始化。

`fortune.allow_user_refresh` 默认关闭。管理员可用 `/刷新运势` 刷新本人，也可 At 指定用户；开启后普通用户可刷新本人。`/刷新全局运势` 需要超级管理员权限，清理当天全部运势与卡片缓存。

## 注册开关

- `setu_general.commands_enabled`：普通命令及偏好子命令，默认开启。
- `setu_general.natural_language_enabled`：短语入口，默认开启。
- `setu_general.llm_tools_enabled`：LLM 工具，默认开启。

三个开关独立生效，关闭后移除实际注册项和相关元数据，保存并重载生效。

## 升级与恢复

运行目录为 `plugin_data/astrbot_plugin_setu/`，只保留 `db.sqlite` 与 `cache/{fortune,setu,doujinshi}/`。

配置只接受当前结构：未知键删除，非法字段恢复默认，无法识别的模板项丢弃，清理后写回 AstrBot 配置。旧键、别名和类型猜测转换全部移除。**非法权限配置恢复默认可能开放访问，请检查 `safety`。**

空字符串或空对象填入配置分组时，该分组恢复默认值。缺少完整 SID 的会话模板、缺少 HTTP/HTTPS 地址的自定义 API，以及选择 JSON 解析却未填写路径的 API 条目会被删除，其余有效条目保留。选择 `custom` 但没有有效 API 时，图片来源恢复为 `lolicon`。标签、代理等允许留空的字段继续保持为空。

数据库迁移位于 `src/infrastructure/persistence/migrations/`，按 `0001_initial.py` 格式顺序执行。`migration` 表记录版本、名称和应用时间；数据库变更和版本记录同事务提交。提交失败保留源数据，提交成功后才清理旧数据库、缓存、废弃配置与标记。清理中断时下次启动继续，清理完成后启动业务。

只导入完整 SID 且位于 30 天窗口内的旧运势，缺 SID 的旧运势删除。旧撤回任务按实际目标迁移；必要会话信息无法恢复时，保留源文件、完整报告任务并停止初始化。升级前请保留运行目录备份，旧配置文件在新版迁移完成后清除。
