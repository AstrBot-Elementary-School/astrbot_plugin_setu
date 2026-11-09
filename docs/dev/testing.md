# 集成验收

测试文件直接放在 `tests/`，保留权限、数据保存与恢复、缓存并发、平台发送契约等回归，运行时数据均放临时目录。使用 AstrBot 已有开发环境运行：

```fish
uv run python -m pytest tests/ -q
uv run python -m compileall -q main.py src
uv run ruff check main.py src tests --select E9,F,I
```

存储测试覆盖同日并发唯一、SID 隔离、逐图历史、30 天边界、迁移回滚和提交后清理恢复。发送测试覆盖 DOCX 与图片文件释放、本子 PDF/ZIP 生成与容量失败清理、消息与群文件任务重启恢复；命令测试使用原生 CommandFilter 验证多词参数、跨会话偏好保存、管理员 At 刷新和超级管理员全局刷新。普通默认值快照和共享发送逻辑的重复包装测试已移除。

官方生命周期入口为 `scripts/ci/check_astrbot_plugin.py`：在临时 `ASTRBOT_ROOT` 运行 PluginManager，检查加载、初始化、实际注册、重载、卸载和资源释放。`--config` 与 `--reload-config` 可传初始、重载后的合成 JSON 配置，检查关闭命令、短语或 LLM 工具后的注册结果。CI 在正式版和 master 运行，`src/` 中的模板变更也会触发。

模板使用 `playwright-cli` 查看五个主题，覆盖 0–7 星、有图/无图、长昵称，检查字体、图片和控制台，并保存截图。已有视觉变化按主题实际实现验收。

真实平台发送、NapCat 上传和远程 t2i 需在受控测试会话验证；本地集成测试使用确认结果可控的发送端。集成结果与真实平台验收分开记录。
