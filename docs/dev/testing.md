# 测试与回归检查

## 基础命令

| 场景 | 工作目录 | 命令 |
| --- | --- | --- |
| Python 格式化 | AstrBot 根目录 | `uv run ruff format data/plugins/astrbot_plugin_setu` |
| Python lint | AstrBot 根目录 | `uv run ruff check data/plugins/astrbot_plugin_setu` |
| 全量 pytest | 插件目录 | `PYTHONPATH=/path/to/data/plugins python -m pytest tests/ -v` |
| 单文件测试 | 插件目录 | `PYTHONPATH=/path/to/data/plugins python -m pytest tests/infrastructure/test_fortune_pregeneration.py -q` |
| 编译检查 | 插件目录 | `python -m compileall main.py src tests` |

> [!TIP]
> 如果上级缓存目录不可写，设置 `RUFF_CACHE_DIR=.ruff_cache` 后再运行 ruff。

## PR 合并检查

- `PR Template Validation`：检查 PR 描述中的「变更点 / Changes」「验证步骤 / Verification」「检查清单 / Checklist」，并拒绝未勾选的清单项。HTML 注释不参与检查；描述中的命令不会被执行。修改描述后自动重验。
- `AstrBot Plugin Lifecycle`：把 DNA 插件的载入与生命周期检查合为一个检查，在最新正式版和 master 上分别验证官方 PluginManager 的载入、初始化、命令与工具注册、卸载和资源清理。

生命周期测试仅在 `main.py`、`__init__.py`、`src/`、`templates/`、配置 schema、插件元数据、依赖清单或该检查自身变更时执行；Markdown、预览资源和单元测试文件变更不会单独触发。纯文档 PR 仍产生成功的检查结果，不安装依赖、不运行生命周期测试，避免 required check 一直等待。

插件测试只执行于无写权限的 `pull_request` 工作流，不读取真实账号或本地配置。PR 模板检查运行于 `pull_request_target`，不 checkout PR 代码，只向当前 head 发布 `PR Template Validation` 状态。

两个名称对应仓库默认分支的 required checks；修改名称时需要同步修改仓库规则。首次部署时先让工作流进入默认分支并确认结果，再启用 required checks。

检查入口为 `.github/workflows/pr-template.yml`、`.github/workflows/plugin-validation.yml` 和 `scripts/ci/check_astrbot_plugin.py`。脚本改编自 `astrbot_plugin_dna/scripts/ci/`，保留临时目录隔离、原始错误、凭据脱敏和卸载残留检查；模板校验沿用 `pixiv-cli/tools/prmeta` 的章节与清单规则，未迁入其命令执行系统。原许可证分别见 `scripts/ci/LICENSE.dna` 和 `.github/licenses/pixiv-cli-MIT.txt`。

## 长期保留哪些测试

`tests/` 保留权限与 SID 隔离、配置和 SQLite 迁移、文件页序与路径安全、平台发送确认、持久化撤回，以及 #35 等已知故障回归。每个场景保留能覆盖实际边界的一组断言，不按文件或函数数量补测试。

字段赋值、异常继承、方法存在、固定文案和 schema 排版快照不再单独测试；相同规则已有行为测试时，删除重复样例。插件实际注册、初始化与卸载由 `AstrBot Plugin Lifecycle` 检查，不再用 `hasattr` 代替载入验证。

普通低风险逻辑可以临时验证，不必留下永久测试。长期稳定的非核心测试可以删除；涉及权限、数据恢复或外部平台契约的测试，不因长期通过而删除。下载恢复回归集中在 `tests/infrastructure/test_image_download.py`。

## 按改动选择检查

| 改动类型 | 最小检查 | 建议额外回归 | 关注点 |
| --- | --- | --- | --- |
| Python 业务逻辑 | 相关单元测试、`ruff check` | provider、sender、config model、内置提示 | 覆盖受影响的调用者和失败路径。 |
| 配置或迁移 | 相关配置测试 | `_conf_schema.json` 同步、`models.py` 同步、旧配置兼容 | 权限或会话配置非法时应报错，不能重置为宽松默认。 |
| sender / 媒体 | sender 单测、发送策略测试 | HTML 卡片降级、NapCat 流式、文件封装、自动撤回 | 不同平台行为差异要覆盖，撤回只在拿到 `message_id` 后调度。 |
| 运势 / Fortune | fortune 相关单测 | 渲染、缓存、预生成、刷新命令 | 卡片渲染失败要能降级到文本。 |

## 高风险改动清单

| 改动 | 风险 | 建议 |
| --- | --- | --- |
| 命令注册或路由变化 | 破坏 AstrBot 命令解析或去重 | 补命令解析测试。 |
| sender 行为变化 | 平台吞图、媒体类型错误、fallback 丢失 | 至少覆盖直接发送和 HTML 卡片降级。 |
| 配置模型变化 | 启动失败或配置丢失 | 检查 `_conf_schema.json`、`models.py`、测试三件同步。 |
| 运势预生成逻辑 | 跨日缓存失效或卡片渲染失败 | 覆盖预生成和缓存命中路径。 |
| 内置提示变化 | 提示缺失或占位符未替换 | 检查改动涉及的 message key 和占位符。 |
| 访问控制判定 | 误拒或误放 | 覆盖完整 SID 隔离、两种功能、黑白名单互斥和旧规则迁移阻断。 |

## 回归检查清单

- [ ] `/setu` 命令在无结果时走配置提示而非硬编码文案。
- [ ] HTML 卡片 fallback 在原图发送失败时仍能触发。
- [ ] 运势卡片渲染失败时降级为纯文本。
- [ ] 会话模板精确匹配、继承、显式关闭和清空标签正常；重复和非法模板报错。
- [ ] 权限和会话迁移失败阻止初始化；保存成功才标记，完成后清空名单或删除模板不恢复旧值。
- [ ] `auto_revoke_targets` 默认仅含 `doujinshi`，并能分别将 `setu`、`fortune`、`doujinshi` 传递到对应链路；`auto_revoke_scope` 的 `none` / `sfw` / `r18` / `all` 仅过滤已启用的色图。
- [ ] OneBot 图片、今日运势和本子普通文件消息均使用 `auto_revoke_delay` 写入统一持久化消息任务；本子通过原始 `send_group_msg` 取得 `message_id` 并在到期后调用 `delete_msg`，旧字段与旧队列均可迁移；删除任务连续失败三次后会移除持久化记录。
- [ ] `tests/conftest.py` 固定的 `ASTRBOT_ROOT` 仍能阻止插件目录污染。
- [ ] 访问控制黑白名单互斥逻辑正常。
