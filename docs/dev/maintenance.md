# 维护规则

本文面向维护者和协作 agent，记录开发时需要遵守的仓库级规则。业务细节不要继续塞进 `AGENTS.md` 或 `CLAUDE.md`，应拆到 `docs/project/` 的对应主题文档。

## 文档同步

- 文档不是可选收尾。
- 行为、边界、入口、配置、流程、架构或维护约定变化时，必须同步更新对应文档。
- 下列变化默认需要更新文档：
  - 命令行为或参数变化
  - 会话模板交互与迁移变化
  - 配置项、默认值或兼容规则变化
  - provider、sender、消息配置算法变化
  - 访问控制判定逻辑变化
  - 运势预生成或缓存策略变化
- 修改 repo-wide 维护规则或 agent 入口约定时，同步更新 `AGENTS.md` 和 `CLAUDE.md`。

## 入口与分层

入口与分层事实统一维护在 [`../project/architecture.md`](../project/architecture.md)。本文件只记录维护要求：保持 `main.py` 专注注册和路由，业务规则、平台适配和入口适配不要互相污染。

## 本地路径

- 插件运行数据路径统一通过 `StarTools.get_data_dir(self.name)` 获取。
- 不要在插件源目录下创建运行态数据。
- 从插件目录本地调试时，不应创建或使用 `<plugin>/data` 作为运行态目录。
- `tests/conftest.py` 固定 `ASTRBOT_ROOT`，阻止 AstrBot 在插件目录创建运行时数据。

## 配置维护

- 配置模型文件是 `src/shared/config/models.py`。
- 新增配置项时，以下文件必须同步更新：
  - `_conf_schema.json`
  - `src/shared/config/models.py`
  - 相关测试
- 内置提示位于 `src/shared/config/messages.py`；新增 key 时同步占位符文档和测试，不恢复用户自定义消息入口。
- sender strategy 和 provider 参数的运行时语义见源码注释和 README，不要在维护文档里复制完整字段清单。

- 配置文案不用 Unicode 表情或 `obvious_hint`；标题写用途，提示只写条件、格式和必要限制。
- 插件弹窗不支持 `collapsed`，低频字段使用 `show_advanced` 开关配合原生 `condition`；条件显示不能删除隐藏值。
- 卡片新字段的 Schema 空默认和隐藏旧字段用于跨路径迁移，不能直接改为默认 `fallback`，否则 AstrBot 预填默认会覆盖旧值。

## 代码组织

- provider 行为属于 `src/infrastructure/providers/`。
- sender 行为属于 `src/infrastructure/sending/`。
- 消息配置解析属于 `src/shared/config/`。
- 不要把 provider 日志、sender 降级或消息解析散落到命令层或领域层。

## 配置唯一来源

- 全局与会话配置只从 AstrBot 插件配置读取，不提供 Pages、管理 API、配置命令或配置修改工具。
- `session_configs` 模板按完整会话标识精确匹配，继承与显式关闭必须可区分。
- 升级迁移先校验，再持久化配置，最后记录完成；迁移失败阻止初始化，不覆盖源文件。
- 权限只按完整 SID 匹配整个会话，不恢复用户／群组双维度。旧裸 ID 规则不可猜测转换或静默丢弃。
- 权限和会话非法值不得通过通用自愈重置为宽松默认。

## 测试与检查

常用命令见 [`testing.md`](./testing.md)。涉及下列行为时，优先补回归测试：

- 配置模型新增或变更
- 消息配置 key 和占位符解析
- provider 参数和 URL 构造
- sender 降级和 HTML 卡片 fallback
- 运势预生成和缓存生命周期
- 访问控制判定和黑白名单互斥
- 命令路由和触发去重

## 仓库体积

- 插件仓库总大小不宜过大。
- 不要把大型二进制资源（字体、模型权重、样例图片）纳入仓库。
- 模板字体（`templates/res/fonts/`）当前为嵌入式资源，后续如有体量增长应改为运行时下载。

## 已移除能力

- Pages、配置修改命令与工具、自定义消息和调优配置已移除；权限和会话配置以插件配置为准。
- `aiohttp` 依赖已完全移除，统一使用 `httpx`。
- `use_httpx`、`tcp_connector_limit`、`tcp_connector_limit_per_host` 等旧配置项已移除。
