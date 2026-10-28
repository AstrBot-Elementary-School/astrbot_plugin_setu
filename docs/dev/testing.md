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

## 分层验证矩阵

| 改动类型 | 最小检查 | 建议额外回归 | 关注点 |
| --- | --- | --- | --- |
| Python 业务逻辑 | 相关单元测试、`ruff check` | provider、sender、config model、message config | 不要只跑被改函数附近的测试。 |
| Plugin Pages | `node --check pages/dashboard/app.js` | 手工验证 `/api/plugin/page/content/astrbot_plugin_setu/dashboard/` 的 Dashboard 标签页加载、读写、重置 | 前端改动不要只看代码；bridge SDK 需要在 `app.js` 前加载，并确认 iframe 内没有 bridge 注入错误。 |
| 配置或迁移 | 相关配置测试 | `_conf_schema.json` 同步、`models.py` 同步、旧配置兼容 | 脏配置要能被容忍。 |
| sender / 媒体 | sender 单测、发送策略测试 | HTML 卡片降级、NapCat 流式、文件封装、自动撤回 | 不同平台行为差异要覆盖，撤回只在拿到 `message_id` 后调度。 |
| 运势 / Fortune | fortune 相关单测 | 渲染、缓存、预生成、刷新命令 | 卡片渲染失败要能降级到文本。 |

## 高风险改动清单

| 改动 | 风险 | 建议 |
| --- | --- | --- |
| 命令注册或路由变化 | 破坏 AstrBot 命令解析或去重 | 补命令解析测试。 |
| sender 行为变化 | 平台吞图、媒体类型错误、fallback 丢失 | 至少覆盖直接发送和 HTML 卡片降级。 |
| 配置模型变化 | 启动失败或配置丢失 | 检查 `_conf_schema.json`、`models.py`、测试三件同步。 |
| 运势预生成逻辑 | 跨日缓存失效或卡片渲染失败 | 覆盖预生成和缓存命中路径。 |
| 消息配置变化 | 提示文案不生效或占位符渲染错误 | 覆盖所有 message key 的解析和 fallback。 |
| 访问控制判定 | 误拒或误放 | 覆盖用户/群组维度、黑白名单互斥。 |

## 回归检查清单

- [ ] `/setu` 命令在无结果时走配置提示而非硬编码文案。
- [ ] HTML 卡片 fallback 在原图发送失败时仍能触发。
- [ ] 运势卡片渲染失败时降级为纯文本。
- [ ] 会话配置读写不锁死（并发安全）。
- [ ] `auto_revoke_targets` 默认仅含 `doujinshi`，并能分别将 `setu`、`fortune`、`doujinshi` 传递到对应链路；`auto_revoke_scope` 的 `none` / `sfw` / `r18` / `all` 仅过滤已启用的色图。
- [ ] OneBot 图片、今日运势和本子普通文件消息均使用 `auto_revoke_delay` 写入统一持久化消息任务；本子通过原始 `send_group_msg` 取得 `message_id` 并在到期后调用 `delete_msg`，旧字段与旧队列均可迁移；删除任务连续失败三次后会移除持久化记录。
- [ ] `tests/conftest.py` 固定的 `ASTRBOT_ROOT` 仍能阻止插件目录污染。
- [ ] 访问控制黑白名单互斥逻辑正常。

## R18 DOCX 回归

`tests/infrastructure/test_docx_service.py` 使用普通 JPEG、PNG、WebP 验证有效
DOCX 的图片数量、顺序、页面尺寸、并发唯一文件名、保存失败清理和缓存关闭后的回收。
`test_image_sender.py` 覆盖服务缺失、读取/生成失败、文件发送失败及 pending，
并检查普通 File 和撤回消息 ID 传递。按基础命令运行 `tests/infrastructure/ -q`。

集成验收使用受控 AstrBot + NapCat 会话：设置 `setu.content_mode=r18`、
`setu.r18_docx=true`，分别请求一张和多张测试图片，下载并打开 DOCX；
启用色图自动撤回后检查消息 ID 与撤回记录；关闭 DOCX 再检查普通图片发送。
该客户端验收须在可用测试会话执行，单测使用模拟平台结果。
