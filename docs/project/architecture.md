# 架构与数据归属

`main.py` 负责 AstrBot 原生命令、子命令、注册开关和生命周期。业务按 `domain`、`application`、`infrastructure`、`shared` 分层；模板位于 `src/template/`。

## 启动和卸载

启动时按当前 schema 清理配置并写回，创建容量缓存，连接统一数据库并执行迁移；随后初始化 provider、SID 权限仓储、撤回调度和命令处理器。运势关闭时跳过其处理器和渲染器。普通命令、短语、LLM 工具分别按开关注册。

初始化失败释放本次创建的资源并保留完整错误。卸载停止内存调度、移除工具、关闭数据库并清除插件上下文；待执行任务保存在数据库供下次恢复。

## 图片与发送

provider 返回逐图 `ImageMetadata(image_url, source_url, tags)`，下载结果保留顺序。普通请求和运势取图都记录图片历史：上游标签优先，否则使用请求标签；来源为原图源地址，缺失时记录调用 API，图片地址完整保留反代。

图片通过直接发送或合并转发发送，支持既有 NapCat 流式与受信任本地路径传输。R18 DOCX 按需导入 `python-docx`，本子生成 PDF 或 ZIP，以普通文件发送。发送确认待定时保留本地文件并记录状态，避免重复发送或提前删除。

运势使用 AstrBot t2i 渲染；普通图片的 HTML 包装路线已移除。

## 运势与偏好

每日运势由 `FortuneService` 和 `SQLiteFortuneRepo` 保存星级，唯一键为 `(session_id, user_id, date)`，背景通过 `setu_history_id` 关联。偏好以框架返回的 `user_id` 为主键，跨群聊与私聊共享。

模板输入为昵称、日期、星级、图片。主题的 `text.json` 保存运势标题，以及按 0～7 星分组的 `messages` 和 `tip` 候选数组，模板分别随机抽取正文和寄语；固定标识、装饰文字和图片说明直接写在 `index.jinja2`，`index.css` 管样式。渲染器只装配所选主题及其字体。主题包括 `arona`、`endfield`、`persona5`、`minecraft`、`minimal`，默认随机，从 `fortune.random_themes` 勾选的范围中抽取，初始范围排除 `minimal`。

各主题的 `template.yaml` 保存版本、名称、别名和作者，初始版本为 `"0.1"`。当前只使用 `aliases` 解析主题选择，偏好入库前统一为主题目录名，随机选择保存为 `random`。

完整 Jinja 文档直接交给 AstrBot，确保注入脚本位于 `<head>` 内、保留 `DOCTYPE` 标准模式。运势截图按主题的原有卡片宽度设置 t2i 视口，页面高度随内容展开。图片展示区固定高度，横图、竖图和无图占位保持相近的成品比例；Minecraft 从页面顶部排版，避免视口高度参与垂直居中。字体随主题内嵌，截图沿用 Playwright 的字体加载等待。

## 持久化与缓存

```text
plugin_data/astrbot_plugin_setu/
├── db.sqlite
└── cache/
    ├── fortune/
    ├── setu/
    └── doujinshi/
```

- `daily_fortune`：`id, session_id, user_id, date, stars, setu_history_id`。
- `user_preference`：`user_id, theme, tags`。
- `setu_history`：`id, session_id, user_id, date, tags, source_url, image_url`。
- `setu_schedule_task`：`id, session_id, target, due_at, payload`，payload 为当前执行流程需要的目标数据。
- `migration`：`version, name, applied_at`。

运势和图片历史保留包含当天的 30 天，过期历史仍被有效运势引用时保留。三类文件缓存默认关闭，临时文件与缓存共用 512 MiB 上限；文件使用权与容量检查在同一缓存管理器协调。

迁移脚本使用异步 `upgrade(connection, data_dir)`，事务提交后执行 `cleanup(data_dir)`；后者可重复执行，清理中断后重启继续。已发布脚本保持不变，新增版本用新脚本升级。

## 配置

`SessionConfigService` 按完整 SID 解析会话模板，`ConfigAccessControlRepo` 只读配置权限。个人标签覆盖会话标签和插件默认值，主题覆盖插件默认主题，内容分级继续遵循会话配置。

schema 和 Pydantic 模型共同约束当前配置。未知键删除、非法值恢复默认，旧配置转换已移除。具体字段见[配置参考](../usage/configuration.md)。
