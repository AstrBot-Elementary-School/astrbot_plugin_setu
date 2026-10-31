---
name: astrbot_plugin_setu-skill
description: 使用 astrbot_plugin_setu 获取色图、随机本子和今日运势，解释个人主题、搜索标签、SID 权限和注册开关。适用于色图、setu、今日运势、运势刷新和偏好设置。
---

# 色图与今日运势

按当前已注册工具处理请求：`get_setu_image(count, tags)`、`get_today_fortune()`、`refresh_my_fortune()`、`refresh_group_fortune()`、`refresh_all_fortune()`。只在用户明确要求时刷新，并按其指定范围调用；工具未注册时直接说明当前入口已关闭。

色图默认数量 1、标签空列表，保留用户的完整标签。独立 `r18` 标签只影响本次请求，当前会话为 SFW 时会拒绝。内容分级、发送方式和访问权限由插件及完整 SID 会话配置决定。

用户命令为 `/色图`（别名 `/setu`）、`/随机本子`、`/今日运势`（别名 `/jrys`）。`/刷新运势` 刷新当前会话中的本人运势，管理员可 At 指定一位用户；普通用户需开启 `fortune.allow_user_refresh`。`/刷新全局运势` 和全局刷新工具仅供 AstrBot 超级管理员使用。群刷新工具按完整 SID 清理本群当天运势。

个人偏好通过原生子命令设置：

- `/运势偏好 查看`
- `/运势偏好 主题 arona`
- `/运势偏好 标签 猫耳 白发`
- `/运势偏好 重置主题`
- `/运势偏好 重置标签`

主题可选 `arona`、`endfield`、`persona5`、`minecraft`、`minimal`、`random`，默认 `endfield`。主题按“个人偏好 → 插件默认值”生效；搜索标签按“个人偏好 → 当前 SID 会话配置 → 插件默认值”生效。偏好以 `user_id` 为键跨会话共享，运势星级按会话、用户、日期保存，切换主题保持当天星级。

配置在 AstrBot 插件面板修改，保存后重载。`setu_general.commands_enabled`、`natural_language_enabled`、`llm_tools_enabled` 分别控制普通命令、短语入口和 LLM 工具注册；关闭运势时也移除运势入口和工具。`safety` 使用完整 SID 管理会话权限，`session_configs` 管理会话分级和运势默认标签。

未知配置删除、非法字段恢复默认；非法权限配置可能恢复开放访问，请提醒管理员检查 `safety`。文件缓存默认关闭，共用 512 MiB 上限；历史保留包含当天的 30 天。数据位于 `plugin_data/astrbot_plugin_setu/db.sqlite` 和 `cache/`。

据工具结果说明成功、失败或等待确认的状态。平台接收待确认时保留原状态，避免自动重发。权限失败直接报告，配置问题引导到插件面板。运势渲染失败时使用主题提供的文字运势。
