---
name: get-setu
description: Help users fetch Setu images and today's fortune through astrbot_plugin_setu, or explain where to configure session-specific content and delivery. Use for 色图/瑟图/涩图/setu/random anime images, tags, content mode, send mode, auto revoke, DOCX packaging, session settings, and 今日运势.
---

# get-setu

Use only the registered business tools:

- `get_setu_image(count: integer, tags: string[])`
- `get_today_fortune()`
- `refresh_my_fortune()`
- `refresh_group_fortune()`
- `refresh_all_fortune()`

## Image and fortune requests

Extract image count and tags; default to `count=1`, `tags=[]`. Preserve multi-word tags. Content rating and delivery come from the current session template over global configuration; the image tool does not accept a separate R18 flag.

Use `get_today_fortune` to send the rendered fortune card. If rendering or delivery fails, it returns a text fortune. A submitted or pending delivery is not a confirmed receipt; do not retry it automatically. Use refresh tools only for an explicit refresh request and the requested scope.

Refresh-my and refresh-group require administrator permission; refresh-all requires super administrator permission. Report permission failures directly; do not switch tools to bypass them.

## Configuration questions

Configuration tools and management commands have been removed. Do not call session-config get/set/clear tools. Direct users to AstrBot plugin configuration:

- `session_configs`: add a `setu` or `fortune` template with the complete `unified_msg_origin` session ID. Unspecified values inherit global configuration.
- The `setu` template controls content rating, send mode, R18 DOCX, and auto-revoke scope.
- The `fortune` template controls background rating and tags. Turn on `override_tags` to replace global tags; an empty tag string then clears them.
- `safety`: add a Setu or fortune template with a mode and complete SID blacklist/whitelist. A group SID controls the whole conversation, not individual members.

Save and reload the plugin to apply changes. No separate Pages dashboard exists. Cache size/TTL, card spacing, stream chunk size, and replenish rounds use internal defaults and are not configurable.

## Results

State what the tool reported; do not claim delivery unless the tool says it succeeded. Surface failures directly. For transport issues, explain the existing NapCat `stream_mode` and shared-path `local_file_mode` options without pretending to change them through tools.
