---
name: get-setu
description: Help users operate the current astrbot_plugin_setu LLM tools for fetching Setu images, reading or changing unified session settings, R18 delivery safeguards, and today's fortune. Use this skill whenever the user asks for 色图/瑟图/涩图/setu/random anime images, image tags, content mode, send mode, auto revoke, DOCX packaging, session config, or 今日运势, even if they do not mention the plugin or tool names explicitly.
---

# get-setu

Use this skill to choose the correct `astrbot_plugin_setu` LLM tool and explain the result. Tools operate in the current AstrBot session. Session config tools only affect the current session; WebUI can manage other sessions, but these LLM tools cannot.

## Current Tool Inventory

Use only these registered tools:

- `get_setu_image(count: integer, tags: string[])`
- `get_today_fortune()`
- `refresh_my_fortune()`
- `refresh_group_fortune()`
- `refresh_all_fortune()`
- `get_session_config(key?: string)`
- `set_session_config(key: string, value: string)`
- `clear_session_config(key?: string)`

Do not call removed legacy tools such as `get_setu_content_mode`, `set_setu_content_mode`, `set_setu_r18_docx_mode`, `set_setu_auto_revoke`, `set_setu_send_mode`, `get_fortune_config`, or `set_fortune_config`.

## Session Config Keys

Use these keys with `get_session_config`, `set_session_config`, and `clear_session_config`:

| Key | Values | Meaning |
|---|---|---|
| `setu.content_mode` | `sfw`, `r18`, `mix` | Content rating for Setu image requests. |
| `setu.r18_docx` | `true`, `false` | Whether R18 images are packaged as DOCX. |
| `setu.auto_revoke_scope` | `none`, `sfw`, `r18`, `all` | Which Setu image sends are auto-revoked. |
| `setu.send_mode` | `image`, `forward`, `auto` | Direct image, merged forward, or automatic send mode. |
| `fortune.tags` | string | Default tags for fortune images. |
| `fortune.content_mode` | `sfw`, `r18`, `mix` | Content rating for fortune images. |

Boolean values can be passed as strings like `"true"` or `"false"`.

Global delivery settings such as `platform_transports` NapCat options, send cache TTL, and send cache size are not session preferences and are not exposed through the LLM session config tools. Tell users to change them in the AstrBot WebUI plugin config.

## Choosing Tools

For image requests, extract count and tags from the user. Default to `count=1` and `tags=[]` when unspecified. Preserve meaningful tags such as `白丝`, `猫耳`, `blue archive`, or `long_hair`. If the user explicitly includes the standalone marker `r18`, keep it as a separate item in `tags`: the plugin removes it before calling the image API and requests R18 for that request only, provided the effective content mode is `r18` or `mix`. In `sfw` mode, the request is rejected; do not change session settings or retry through another tool to bypass the restriction. Otherwise, the plugin uses the current effective `setu.content_mode`. Do not pass a separate R18 parameter or change session settings for a one-time request.

For settings questions, call `get_session_config`. If the user asks about one setting, pass the specific key. If they ask for all settings, omit `key`. The tool returns JSON; read `ok`, then summarize `data.effective`, `data.override`, and `data.global` as needed.

For setting changes, call `set_session_config(key, value)` with the exact key. The tool returns JSON; if `ok` is false, report `message` directly. If `ok` is true, summarize the changed key and effective value.

For clearing settings, call `clear_session_config(key)` for one override or `clear_session_config()` to clear all current-session overrides. Explain that the global config will apply afterward.

For fortune requests, call `get_today_fortune`. For refresh requests, use `refresh_my_fortune`, `refresh_group_fortune`, or `refresh_all_fortune` based on scope.

## Permission Boundaries

Treat `set_session_config`, `clear_session_config`, and all refresh tools as privileged. If a tool reports insufficient permission, tell the user the operation requires an administrator or super administrator. Do not retry with a different tool to bypass permission checks.

Use extra care with `r18`, `mix`, `setu.auto_revoke_scope`, and `setu.r18_docx`. Change only what the user requested; do not silently enable unrelated safety or delivery settings.

## Response Style

Be concise. After a fetch or fortune tool returns, say what was requested and whether the plugin reported success or failure. Do not claim that an image was sent unless the tool result says it succeeded.

For failures, surface the plugin's message directly and suggest a practical next step such as fewer images, different tags, or a different send mode. Do not tell the user to configure HTML fallback in WebUI after fallback failure; the plugin now reports fallback failure as a normal send failure.

For slow image sending on NapCat/OneBot, explain that the plugin downloads images to local send cache first and the NapCat platform transport defaults to `stream_mode=fallback`: it tries normal file-path sending, then uses NapCat stream upload if that fails. `always` can be enabled globally in WebUI when the platform supports stream upload and large original images are common. NapCat stream chunks are still base64 `chunk_data`; shared-path `local_file_mode` is the route that bypasses AstrBot's normal base64 image chain.

## Examples

User: `来三张白丝猫耳`

Action: `get_setu_image(count=3, tags=["白丝", "猫耳"])`

User: `现在是 r18 吗`

Action: `get_session_config(key="setu.content_mode")`

User: `这个群以后用合并转发`

Action: `set_session_config(key="setu.send_mode", value="forward")`

User: `开启 r18 自动撤回`

Action: `set_session_config(key="setu.auto_revoke_scope", value="r18")`

User: `清掉这个群的色图模式`

Action: `clear_session_config(key="setu.content_mode")`

User: `今日运势`

Action: `get_today_fortune()`
