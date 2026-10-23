# 维护规则

项目入口见 [AGENTS.md](../../AGENTS.md)，模块与运行链路见[架构](../project/architecture.md)。这里记录配置、迁移和文档维护时需要了解的事项。

## 文档同步

命令、配置、默认值、兼容规则或发送行为变化时，同步更新对应使用文档；模块关系和数据归属变化时更新架构说明。索引只保留入口，不重复专题细节。

`AGENTS.md` 按任务和模块指向文档、代码，不保存业务规则或检查命令。`CLAUDE.md` 只通过 `@AGENTS.md` 引用它。入口路径变化时更新路由地图。

## 分层与提示

`main.py` 连接生命周期、注册和路由，业务规则由 application/domain 负责，平台适配位于 infrastructure。用户可见提示集中在 `MessagesConfig` / `resolve_message()`；图片与本子的标签共用 `application/setu/tag_resolution.py`。

## 本地路径

- 插件运行数据路径统一通过 `StarTools.get_data_dir(self.name)` 获取。
- 不要在插件源目录下创建运行态数据。
- `tests/conftest.py` 固定 `ASTRBOT_ROOT`，阻止 AstrBot 在插件目录创建运行时数据。

## 配置与迁移

- 配置模型文件是 `src/shared/config/models.py`。
- 新增配置项时，以下文件必须同步更新：
  - `_conf_schema.json`
  - `src/shared/config/models.py`
  - 相关测试
- 内置提示位于 `src/shared/config/messages.py`；新增 key 时同步占位符文档和测试，不恢复用户自定义消息入口。
- sender 和 provider 参数的行为见[配置参考](../usage/configuration.md)及对应源码。

- 配置文案不用 Unicode 表情或 `obvious_hint`；标题写用途，提示只写条件、格式和必要限制。
- 插件弹窗不支持 `collapsed`，低频字段使用 `show_advanced` 开关配合原生 `condition`；条件显示不能删除隐藏值。
- 卡片新字段的 Schema 空默认和隐藏旧字段用于跨路径迁移，不能直接改为默认 `fallback`，否则 AstrBot 预填默认会覆盖旧值。

## 配置来源

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
