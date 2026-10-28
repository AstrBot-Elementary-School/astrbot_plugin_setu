# Changelog

## [3.0.0] - 2026-10-24

### Added

- 可配置的自然语句短语模板：分别设置图片、本子和运势入口，支持数量与标签占位符，按列表顺序整句匹配一次。
- LLM 工具、随机本子和自然语句触发开关；关闭自然语句或工具不影响聊天命令。
- 单次 `r18` 标记：命令、图片短语和图片工具共用解析，不修改配置，也不能绕过生效会话的 SFW 分级。

### Changed

- **不兼容升级：配置统一到 AstrBot 插件配置。** 会话差异通过 `session_configs` 模板管理，访问控制通过 `safety` 模板按完整 SID 匹配整个会话，不再支持在群内单独限制成员。
- 配置界面按图片获取、发送与撤回、今日运势、会话设置、访问控制和图片来源高级设置排列，低频设置默认隐藏。
- 缓存、卡片间距、传输分块和补图轮次使用内部默认；多图片源固定轮流使用，运势复用全局图片源。
- 卡片策略由 `html_card.strategy` 迁至 `delivery.html_card_strategy`，新路径优先。

### Removed

- Pages 页面、管理 API、配置修改命令及对应 LLM 工具；运势刷新统一使用 `/运势刷新 [我|本群|全局]`。
- 用户自定义消息与消息覆盖，统一使用内置提示。
- 内置 Atri 图片源及专属参数。旧 `api_type=atri` 会迁为 Lolicon，`all` 只轮流使用 Lolicon 和 SexNyan；随机本子仍使用 Atri 接口，可关闭本子功能停止下载。
- README 中的“未来更新”列表。

### Fixed

- 关闭 `fortune.enabled` 后，运势获取、刷新、工具和后台预生成均停用，不初始化运势专用资源；已有数据与持久化撤回任务保留。
- `fortune.allow_user_refresh` 生效：普通用户可在通过运势 SID 权限检查后刷新自己，本群与全局刷新权限不变。
- 运势命令与 LLM 工具共用发图流程；渲染或发送失败时返回文字运势，待确认的发送不重复降级（#35）。

### 升级注意事项

- 升级前备份 AstrBot 插件配置和插件运行数据。旧会话覆盖迁入插件配置，原运行文件保留；迁移完成后，删除模板或清空名单不会重新导入。
- 旧用户／群组裸 ID 权限不能可靠转换成完整 SID。存在限制模式或非空名单时会停止初始化，请在插件配置中明确填写新的 SID 规则后重载；迁移读写失败也会阻止启动。
- Atri 图片源迁移保留现有 Lolicon 参数、分级和 SID 权限，不把 Atri 参数映射给其他来源；配置保存失败时停止初始化。
- 旧自定义消息和已移除的调优参数停止生效。配置修改仍按 AstrBot 的保存、重载流程生效。

## [2.2.0] - 2026-08-14

### Added

- **随机本子文件**：新增 `/随机本子`（`/本子`、`/doujinshi`）命令；调用 Atri 随机本子 API，下载全部页图并支持 PDF/ZIP 两种生成模式。
- **本子自然语言入口**：支持发送“来份本子”或“来一份本子”触发随机本子。
- **本子文件发送策略**：新增 `delivery.doujinshi_send_mode`（`pdf`/`archive`）；两种模式在所有平台均直接发送普通 `File`，取消本子合并转发及标题/原始地址节点。
- **本子文件名与撤回**：PDF/ZIP 使用 API 返回的本子标题作为文件名；OneBot/NapCat 普通文件消息可按统一可恢复队列延迟撤回，不再反查群文件。
- **统一可恢复撤回队列**：图片自动撤回与 OneBot/NapCat 本子文件消息延迟撤回统一保存到 `revoke_tasks.json`；插件重启后按原到期时间继续执行，旧 `doujinshi_file_cleanup_tasks.json` 会自动迁移。
- **可配置提示**：新增 `doujinshi_fetching`、`doujinshi_failed` 消息键。

### Changed

- **正则入口收敛**：色图自然语言与纯文本今日运势改由 `main.py` 的单一 regex 路由函数分发。
- **撤回调度重构**：移除仅在内存存活的撤回调度，所有已登记的 OneBot `delete_msg` 与 `delete_group_file` 任务均使用统一可恢复调度器。

### Fixed

- **OneBot 本子文件 URI**：普通文件直发取得 `message_id` 时，统一将绝对本地路径规范化为 `file://`，避免 NapCat 虽接受 action 但 QQ 客户端打开附件显示下载失败。

## [2.1.2] - 2026-07-09

### Fixed
- **Provider over-return 数量保护**：修复部分上游 API 在请求 `num=1` 时返回多个图片 URL，导致插件连续发送 2 张图片的问题。下载层现在会按本轮缺口裁剪候选 URL，只下载并交付用户请求数量的图片；正常补齐、下载重试、缓存落盘和 sender 发送策略不变。新增回归测试覆盖「请求 1 张但 provider 返回 2 个 URL」场景。

## [2.1.1] - 2026-06-15

### Changed
- **移除未使用的 Playwright 依赖**：`requirements.txt` 不再声明 `playwright>=1.45.0`。经全仓库静态/动态引用面诊断确认，插件代码从未直接或间接引用 Playwright；运势卡片渲染经 AstrBot `html_renderer.render_custom_template()` 走 network t2i 终结点（HTTP），本插件进程无需 Playwright。移除后减少约 4.5GB 浏览器二进制与 148MB pip 包的无谓占用，渲染行为与失败语义不变（t2i 不可用时照常返回失败）

## [2.1.0] - 2026-06-14

### Added
- **NapCat 平台传输模板**：新增 `delivery.platform_transports` 的 NapCat 模板，支持配置 stream 上传策略、`stream_chunk_kb` 分块大小、本地 `file://` 直通模式与额外共享目录
- **可信本地文件直通**：AstrBot 与 NapCat 共享发送缓存或显式共享目录时，直发模式可通过 raw OneBot `file://` 发送，绕过 AstrBot 标准链路的图片 base64 转换
- **发送前压缩与自动分批**：新增大图压缩与按 base64 估算体积分批发送能力，降低 original 多图撞 WebSocket 单帧上限或 direct 8 图限制的概率
- **自动撤回范围枚举**：新增 `delivery.auto_revoke_scope` 与会话覆盖 `setu.auto_revoke_scope`，支持 `none`、`sfw`、`r18`、`all` 四档范围
- **撤回调度器**：新增 OneBot `delete_msg` 延迟调度与插件退出清理，direct、stream、`file://`、HTML fallback、forward、R18 Docx 均在可拿到 `message_id` 时支持自动撤回
- **SexNyan 配置模板**：新增 SexNyan provider 模板，支持 `proxy`、`uid`、`keyword`，`uid` 会按 SexNyan V2 的 `author_uuid` 参数发送
- **发送限制文档**：新增 `docs/project/sending-limits.md`，记录 OneBot/NapCat 标准链路 base64、stream base64 分块、`file://` 直通与多图限制的诊断结论

### Changed
- **默认发送模式收敛为 auto**：`send_mode` 默认使用 `auto`，多图且平台支持时优先合并转发，否则直发
- **Provider 默认图片尺寸改为 regular**：降低原图体积对发送链路的压力，需要原图时可在 provider override 中显式选择 `original`
- **提示文案默认开启**：所有内置提示默认 `enabled=true` 并带默认文本；仍可通过 `message_overrides` 关闭或改写单条提示
- **撤回提示时机调整**：`found` 不再在图片发送前承诺撤回；`revoke_scheduled` 仅在至少一个 `message_id` 成功调度后发送，并沿用消息配置开关控制
- **NapCat stream 语义明确化**：`stream_chunk_kb` 只控制每块原始字节大小，`upload_file_stream.chunk_data` 仍按 NapCat 协议使用 base64 字符串
- **Plugin Pages 加载顺序加固**：Dashboard 显式在 `app.js` 前加载 bridge SDK，并动态等待 bridge 注入，减少 iframe 加载竞态
- **访问控制表单改为对话框**：访问控制标签页主视图保留模式设置与记录表格，新增/编辑记录改由 modal 承载，减少页面拥挤

### Fixed
- **旧自动撤回配置迁移**：`delivery.auto_revoke_r18` 会迁移为 `auto_revoke_scope`，旧会话覆盖 `setu.auto_revoke` 会迁移为 `setu.auto_revoke_scope` 并写回 `session_overrides.json`
- **撤回失败不影响发图**：拿不到 `message_id`、平台不支持 `delete_msg` 或删除失败时只记录 warning，不阻止图片发送，也不触发重复 fallback
- **发送结果聚合更准确**：修复字符串 `message_id` 被拆成字符列表，以及部分批次失败时仍误报整体成功的问题
- **forward + stream 死路规避**：forward 模式失败时不再尝试 NapCat stream 回退，避免 `Node.to_dict()` 对 `stream://` 强制 base64 转换后崩溃
- **本地直通安全校验**：`file://` 直通只允许真实文件、发送缓存目录或配置的绝对共享目录，拒绝不存在路径、目录、相对路径与跳出根目录的 symlink
- **命令空文案保护**：Setu 与 Fortune 命令均跳过空配置提示，避免关闭或清空 message config 后发出空白消息

### Documentation
- **配置与命令文档同步**：README、配置参考、聊天命令、Plugin Pages、测试说明与 `get-setu` skill 均更新为 `auto_revoke_scope` 与 NapCat 模板语义
- **Dashboard 测试说明更新**：记录 bridge 注入时序、`node --check` 与 Plugin Pages iframe 验证入口

## [2.0.3] - 2026-06-07

### Added
- **统一 Dashboard 管理入口**：Plugin Pages 合并为 `pages/dashboard/`，在同一页面管理会话配置与访问控制
- **访问控制 Web API**：新增访问控制页面 API，支持黑白名单表格、Setu/运势独立模式与旧 `safety.*` 配置一次性导入

### Changed
- **发送失败判定更谨慎**：发送接口超时或适配器暂未返回 message id 时标记为待确认，不再立刻触发 HTML 卡片或 NapCat 流式降级，降低网络延迟导致重复发图的概率
- **Provider 下载缓存语义修正**：关闭发送缓存时不再走 `reserve/commit` 落盘分支，改为直接返回 streaming bytes
- **运势预生成更贴近运行态访问控制**：预生成会跳过被访问控制拒绝的用户/群组，只在实际缓存可读时跳过渲染，并同步旧记录的展示字段
- **标签别名解析保持多词标签**：列表输入中的 `blue archive` 等多词标签不再被 join/split 拆开
- **配置与文档收敛**：更新 Dashboard、配置项、测试命令与 `exclude_ai` 默认值说明，移除旧性能配置残留描述

### Fixed
- **访问控制持久化失败不再伪成功**：保存失败会抛出明确错误，Web API 对参数错误和内部错误使用不同状态码与安全提示
- **访问控制初始化减少无效写盘**：已有配置未变化时不再每次启动重写 `config.json`
- **Dashboard bridge 兜底**：Plugin Page bridge 未注入时页面不再因直接调用 `ready/apiGet/apiPost` 崩溃
- **平台能力误判修复**：移除泛化 `onebot` marker，避免 OneBot v12 被误判为支持 OneBot v11 合并转发能力
- **Atri provider 配置生效**：`api_type=atri` 时 `exclude_ai` 读取 Atri provider override，不再固定沿用 Lolicon 配置

## [2.0.2] - 2026-05-18

### Fixed
- **恢复运势自动预缓存**：启用 `auto_refresh` 时，近期使用过 `jrys` 的用户会在跨日后预生成并缓存运势卡片图片
- **修复测试目录污染**：测试初始化阶段固定 `ASTRBOT_ROOT`，避免 AstrBot 核心运行时数据写入插件目录下的 `data/`

### Changed
- **清理无效工作流路径**：移除 `.github/workflow/` 下的旧工作流文件，保留 GitHub Actions 标准目录 `.github/workflows/`

## [2.0.1] - 2026-05-18

### Added
- **提示消息全面可配置**：将 Setu 与 Fortune 的提示文案统一接入 `messages` 配置，支持 `enabled + text` 控制
- **占位符渲染能力**：新增统一消息解析逻辑，支持 `{count}`、`{max_count}`、`{user_id}`、`{error}`、`{tags_info}` 等占位符

### Changed
- **Setu 无结果提示改由命令层处理**：移除 use case 内硬编码提示，统一通过配置解析生成
- **Fortune 提示链路统一**：运势相关的配置未加载、仅群聊、刷新成功/失败、黑白名单操作反馈全部走统一消息配置

### Fixed
- **修复提示开关不生效**：补齐并生效 `send_failed` 开关，避免关闭后仍发送固定失败文案
- **修复部分提示无法关闭**：`fetching`、`found`、`send_failed` 及新增 fortune 提示项均可独立关闭
- **恢复今日运势卡片样式**：重新接回旧版模板、字体资源与渲染管线，避免截图卡片退化为简化样式
- **修复私聊运势重复触发**：`jrys/今日运势` 在多命令前缀场景下改为基于命令唤醒状态去重，避免 regex 与 command 同时响应

## [2.0.0] - 2026-05-17

### Changed
- **统一命令入口**：合并运势相关命令，减少主入口分发重复
- **发送链路日志增强**：补全 sender / provider / fallback / NapCat stream 的关键日志
- **配置加载路径修正**：插件初始化改为读取插件自身配置，不再误用 AstrBot 全局配置

### Fixed
- **修复图片反代未生效**：Lolicon / Atri 现在都会使用插件配置中的 proxy，并对 Pixiv 图片 URL 做兜底改写
- **修复空 aspect_ratio 导致启动失败**：兼容配置文件中的空字符串，避免 Pydantic 校验报错
- **修复旧临时文件路径直发失败**：普通发送前先将本地图片物化为稳定载荷，降低 OneBot 发送阶段失败率

### Added
- **统一 provider 诊断日志**：补充抓取、下载、缓存命中和失败汇总日志，便于定位“拿不到图”的根因

## [1.3.1] - 2026-04-19

## [1.3.0] - 2026-04-10

### Added
- **安全配置升级为功能级 + 维度级**：`setu` 与 `fortune` 完全独立，并将访问模式细分为用户/群组两个维度
  - 新增 `safety.setu_user_access_control_mode`
  - 新增 `safety.setu_group_access_control_mode`
  - 新增 `safety.fortune_user_access_control_mode`
  - 新增 `safety.fortune_group_access_control_mode`
- **功能级黑白名单管理完善**：提供 setu/fortune 独立的用户与群组黑白名单读写能力
  - `setu_blocked_users` / `setu_whitelist_users` / `setu_blocked_groups` / `setu_whitelist_groups`
  - `fortune_blocked_users` / `fortune_whitelist_users` / `fortune_blocked_groups` / `fortune_whitelist_groups`
- **安全配置读取缓存**：主配置读取增加 mtime 缓存，减少高频消息场景下的重复磁盘 I/O 与 JSON 解析开销

### Changed
- **访问控制判定逻辑重构**：访问检查改为“用户模式 + 群组模式”双通道判定
  - 用户和群组分别按各自模式（`none`/`blacklist`/`whitelist`）执行
  - `setu` 与 `fortune` 的访问判定互不影响
- **黑白名单互斥策略**：同一用户不会同时存在于同一功能的黑名单与白名单
  - 执行“信任用户”时自动从对应黑名单移除
  - 执行“拉黑用户”时自动从对应白名单移除
- **安全配置来源优先级调整**：优先读取主配置 `safety`（WebUI 持久化来源），再回退运行时与本地缓存

### Fixed
- **修复 WebUI 安全配置读取不一致**：修复 `safety` 配置保存后插件读取不到或读到旧值的问题
  - 修复启动阶段同步方向，避免本地空缓存反向覆盖 WebUI 配置
  - 修复 Windows 下带 BOM 的主配置读取兼容性（`utf-8-sig`）
- **修复访问控制兜底行为**：当 `feature` 缺失或非法时不再静默跳过检查，改为默认拒绝（fail-closed）
- **修复 URL 模式超时反馈**：`fetch_image_urls` 超时时返回明确用户提示，区分“拉取超时”与其他失败

### Migration
- **旧键兼容**：保留旧配置键读取兼容
  - `safety.setu_access_control_mode` -> 同步映射到 `setu_user_access_control_mode` 与 `setu_group_access_control_mode`
  - `safety.fortune_access_control_mode` -> 同步映射到 `fortune_user_access_control_mode` 与 `fortune_group_access_control_mode`
- **升级建议**：建议在 WebUI 中显式配置 4 个新模式键，逐步移除旧键，避免后续版本兼容层移除后的歧义

## [1.2.1] - 2026-04-10

### Fixed
- **Atri 参数兼容性**: 修复 `excludeAI` 在部分调用链中可能收到非布尔值（如 `"none"`）的问题
  - 新增布尔归一化逻辑，确保向 API 发送稳定的 `true/false`
  - 避免因参数类型异常导致 Atri 接口报错
- **Atri 查询参数编码**: 修复 `uid` 过滤参数序列化方式
  - 改为重复参数形式（如 `uid=1&uid=2`），避免 Python 列表字符串化导致后端无法识别
  - `tag` / `uid` 参数改由 `httpx` 统一编码处理，降低边界编码风险
- **LLM 工具暴露不完整**: 修复 `set_setu_send_mode` 未注册导致无法被调用的问题
  - 补齐工具注册与反注册清单，保持生命周期一致性
- **会话配置并发一致性**: 修复会话配置读写锁不一致的问题
  - `get_config` 读取路径与写入路径统一使用锁，降低并发可见性风险

### Changed
- **会话配置代码结构优化**: 抽取共享基类 `session_config_base.py`
  - 复用 Setu 与今日运势会话配置的公共逻辑，减少重复实现
  - 保持既有配置行为兼容，提升后续维护性
- **兼容接口语义明确化**: `cleanup_expired_sessions` 标记为弃用兼容 no-op
  - 增加弃用告警与日志提示，明确该接口不再执行实际清理

### Documentation
- **README 补充 LLM 工具清单**: 完整列出 Setu / 今日运势可用工具、参数与权限
- **权限术语统一**: 统一“超管/超级管理员”文案并补充说明，减少歧义

## [1.2.0] - 2026-04-10

### Added
- **新增 Atri 图片供应商**: 接入 `https://api.atri.rodeo/setu` 作为可选图源
  - 新增 `providers/atri.py`，支持 `r18`、`excludeAI`、`size`、`proxy`、`aspectRatio`、`uid`、`keyword` 参数
  - 支持多 `tag` 查询与 URL 编码，提升中文/特殊字符标签兼容性

### Fixed
- **今日运势重复触发**: 修复 `/今日运势`、`/jrys` 同时命中 regex 与 command 导致重复响应的问题
  - 为纯文本入口增加显式 `/` 前缀拦截，仅保留命令路由处理
- **今日运势图文不一致**: 修复 LLM 返回星级与运势图片星级偶发不一致的问题
  - `get_today_fortune` 改为仅查询当天记录，避免误读历史记录

### Changed
- **今日运势查询策略调整**: 严格按“今日”语义处理
  - 当天有记录：直接返回并更新 `last_view_date`
  - 当天无记录：即时生成并落库，再返回结果

## [1.1.0] - 2026-03-24

### Added
- **今日运势功能**: 全新运势系统上线，为用户每日生成个性化运势卡片
  - 支持七种运势等级：大吉、中吉、小吉、末吉、凶、大凶、半吉
  - 运势卡片包含：运势标题、星级评分、运势描述、寄语等丰富内容
  - 支持主题配色系统，根据运势自动匹配对应色彩主题（红/金/蓝/紫/绿/灰）
  - 支持用户绑定背景图片，运势卡片将展示自定义背景
  - 提供独立的管理命令 `jrys_config` 用于管理运势配置
  - 支持通过 LLM 工具触发运势生成，智能识别用户请求
  - 运势数据持久化存储，支持历史记录查询
  - 图片渲染支持 Playwright T2I，保证高质量输出
  - 字体系统支持三种中文字体动态嵌入（NotoSansSC-Regular/NotoSansSC-Bold/得意黑）
  - 支持运势模板热重载，无需重启插件即可更新样式
  - 渲染器支持缓存机制，首次渲染后缓存字体 base64 数据避免重复读取

### Changed
- **架构升级**: 运势模块采用独立架构设计
  - 新增 `fortune/` 模块目录，包含 renderer、service、commands 等子模块
  - 模板系统支持 Jinja2 语法，通过 `{{ fonts_css }}` 变量动态注入字体
  - 渲染器采用延迟加载策略，首次使用时缓存字体 base64 数据
  - 支持 HTML 模板与渲染数据分离，便于自定义样式

## [1.0.8] - 2026-03-19

### Fixed
- **跨平台兼容性**: 修复合并转发在不受支持平台的问题（如 Telegram）
  - 新增 `_is_forward_supported()` 方法，使用 `event.platform.name` 智能检测平台是否支持合并转发
  - 仅对 OneBot v11 (`aiocqhttp`) 平台启用合并转发功能
  - 对于不支持的平台（如 Telegram），自动降级为普通图片发送，避免无效尝试
  - 改进 `_send_nodes_direct` 和 `_send_nodes_with_revoke` 的错误检测，正确识别平台不支持的情况
  - HTML 卡片降级也应用相同的平台检测逻辑
  - 添加详细的日志输出，帮助诊断发送问题
- **LLM 工具状态检测**: 修复发送状态检测不准确的问题
  - `send_images` 现在在发送成功时 yield 内部成功标记 `{"send_success": True, "image_count": n}`
  - 修改命令处理器不过滤内部成功标记，确保能传递给 LLM handler
  - LLM handler 现在能正确识别成功发送的图片数量，返回正确的工具结果
  - 移除 LLM handler 中的重复计数逻辑 `sent_count += 1`，避免错误消息被计入成功数量
- **Unicode 转义处理**: 修复标签中文 Unicode 错误转义问题
  - 重构 `_decode_unicode_escapes`：使用正则表达式只替换 `\uXXXX` 格式
  - 避免 `unicode_escape` 过度解码其他转义序列（如 `\n`, `\t` 等）
  - 中文标签（如 `碧蓝档案萝莉`）不再被错误转义为 `\u74f7\u7b25\u6728\u684c`
- **发送逻辑健壮性**: 修复多平台发送异常处理问题
  - `_direct_send` 现在只对 OneBot v11 平台严格检查 `send_message` 返回值
  - 对于 Telegram 等平台，`send_message` 返回 `None` 不再视为失败
  - 添加 `TimeoutError` 捕获，处理 Telegram 等平台的网络超时问题
  - 避免在 Telegram 等平台上不必要地触发 HTML 卡片降级
- **资源泄漏**: 修复 HTML 卡片渲染中的同步 I/O 阻塞问题
  - 使用 `asyncio.to_thread` 读取文件，避免阻塞事件循环

### Changed
- **代码重构**: 提取共享逻辑，减少代码重复
  - 重构 `_send_nodes_with_revoke` 和 `_send_nodes_direct`
  - 提取共享辅助函数 `_send_forward_messages` 和 `_check_forward_result`
- **日志优化**: 降低日志级别，减少生产环境噪音
  - 将部分 `info`/`warning` 日志降级为 `debug`
- **依赖清理**: 完全迁移到 httpx
  - 移除 aiohttp 依赖，统一使用 httpx 进行所有 HTTP 请求
  - 移除配置项：`use_httpx`、`tcp_connector_limit`、`tcp_connector_limit_per_host`
  - 移除依赖：`aiohttp`、`aiofiles`

## [1.0.7] - 2026-03-18

### Added
- **HTML 卡片策略**: 将 `enable_html_card` (布尔值) 改为 `html_card_strategy` (下拉框)，提供三种选项：
  - `never`：从不使用 HTML 卡片
  - `fallback`（默认）：发送失败时降级为 HTML 卡片
  - `always`：总是使用 HTML 卡片包装发送
- **分段下载功能**: 将大图片分多段并行下载，显著提升高带宽环境下的下载速度
- **性能配置面板**: 新增性能配置面板，支持配置分段下载、并发限制、超时等参数

### Changed
- **合并转发性能优化**:
  - 使用 `asyncio.gather` 并行转换 nodes 到 dict，减少序列化等待时间
  - 非自动撤回模式下使用直接 API 调用，绕过 AstrBot 内部消息处理
  - 添加详细性能日志，便于诊断发送慢的问题
- **图片下载优化**:
  - 图片下载使用流式传输（streaming）替代直接读取 content，强制 50MB 大小限制
  - 分段下载添加范围验证，检查返回数据大小与预期是否匹配
- **图片发送逻辑重写**:
  - 使用 `context.send_message` 直接发送代替 `yield`，可正确捕获发送异常
  - HTML 卡片降级优化：发送失败时正确重用已下载的图片数据，渲染方法改为返回字节数据而非文件路径
- **错误提示优化**: 区分"未找到符合要求的图片"和"网络/服务异常"两种场景，提供更准确的错误信息

### Fixed
- **DocxService 初始化**: 移除多余的 `initialize()` 调用，修复初始化错误

## [1.0.6] - 2026-03-13

### Fixed
- 修复命令注册的 BUG，确保命令正确注册到 AstrBot 框架

## [1.0.5] - 2026-03-13

### Changed
- **架构重构**: 所有模块文件严格控制在 500 行以内
  - 极致压缩 main.py，仅保留命令与工具注册逻辑，剥离所有业务代码
  - 重构代码架构，提高可维护性
- **性能优化**: 优化图片下载性能
  - 提升 TCP 连接池上限至 100，单主机连接数提升至 30
- **HTML 卡片降级**: 修复发送失败时的降级逻辑
  - 现在正确重用已下载的图片数据，而非重新请求

### Fixed
- **初始化修复**: 修复 DocxService 初始化参数错误
- **方法缺失**: 修复 LlmHandlers 缺失的 `_check_admin` 方法
- **导入修复**: 修复 revoke_tasks.py 缺失的 time 模块导入

## [1.0.4] - 2026-03-13

### Changed
- 重构代码结构，优化模块组织方式

## [1.0.3] - 2026-03-11

### Added
- **审核绕过机制**: 优化绕过审核机制，有效捕获发送失败错误并采用 HTML 卡片包装绕过审核发送
- **LLM 工具**: 新增 "内容模式设置" 和 "内容模式查看" 工具

### Changed
- **缓存优化**: 调高图片缓存的默认值至 200 个
- **依赖清理**: 移除一些不必要的模块导入

### Fixed
- 优化绕过审核机制，现在会有效捕获发送失败产生错误从而采用 HTML 卡片包装绕过审核发送图片

## [1.0.2] - 2026-03-10

### Added
- **高带宽服务器支持**: 增加针对于高带宽服务器的性能配置选项

### Fixed
- 修复补货机制，解决图库库存不足时仍尝试补货的问题

## [1.0.1] - 2026-03-10

### Fixed
- **边界逻辑**: 修复 `/setu` 命令的边界逻辑偏差问题
- **私有成员优化**: 对 core.py 进行私有成员使用上的优化
- **全局配置保护**: `DEFAULT_TAG_ALIAS` 现在返回拷贝对象，避免污染全局配置
- **组件一致性**: 修复分支消息组件构造不一致的问题
- **资源管理**: 撤回任务的生命周期已托管，减少潜在资源管理问题
- **代码清理**: 去除未使用的函数
- **安全防护**: API 供应商接口增加并发下载限速、响应体大小约束、SSRF 防护
- **解析增强**: 增加 URL 编码和 JSONPath 解析
- **并发安全**: 增加会话配置管理的并发写入锁保护
- **路径一致性**: 优化导入路径一致性的潜在风险

### Security
- **哈希注释**: `hashlib.md5` 使用处添加注释说明非安全用途

## [1.0.0] - 2026-03-10

### Added
- 瑟瑟诞生！初始版本发布
