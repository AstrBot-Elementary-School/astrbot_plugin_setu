# LLM 工具

插件注册了以下 LLM 工具，供 AstrBot 的 AI agent 调用。

`llm_tools.enabled=false` 时不注册下列工具，手动命令仍可用。`fortune.enabled=false` 时不注册运势工具。
修改后重载插件生效；已有工具引用在执行入口也会检查开关。聊天内 `/session_config` 始终可用，其修改权限仍由管理员权限控制。

## Setu 工具

| 工具名 | 作用 | 参数 | 权限 |
|---|---|---|---|
| `get_setu_image` | 获取并发送随机图片 | `count: integer`（数量）, `tags: string[]`（标签） | 普通用户可用 |

## 会话配置工具

| 工具名 | 作用 | 参数 | 权限 |
|---|---|---|---|
| `get_session_config` | 查看当前会话全部配置或单个 key 的生效值 | `key?: string` | 普通用户可用 |
| `set_session_config` | 设置当前会话一个覆盖配置 | `key: string`, `value: string` | 管理员/超级管理员 |
| `clear_session_config` | 清除当前会话一个覆盖配置，或清空全部覆盖 | `key?: string` | 管理员/超级管理员 |

## 今日运势工具

| 工具名 | 作用 | 参数 | 权限 |
|---|---|---|---|
| `get_today_fortune` | 获取并发送今日运势（含运势图） | 无 | 普通用户可用 |
| `refresh_my_fortune` | 刷新"我的"今日运势 | 无 | 管理员 |
| `refresh_group_fortune` | 刷新当前群今日运势 | 无 | 管理员 |
| `refresh_all_fortune` | 刷新全局今日运势 | 无 | 超级管理员 |

## 调用建议

- 需要"仅查看状态"时优先调用 `get_session_config`。
- 需要会话级覆写时使用 `set_session_config`；希望回到全局配置时使用 `clear_session_config`。
- 对于发送类工具，插件会直接把结果发送到当前会话，工具返回文本用于说明执行结果。
- 权限类工具在非管理员场景会返回权限不足提示。
