"""丢弃无效配置，保留当前模型支持的有效字段。"""

from copy import deepcopy

from pydantic import ValidationError

from ...shared.config.models import SetuPluginConfig


def _default(meta):
    if meta["type"] == "object":
        return {key: _default(value) for key, value in meta["items"].items()}
    return deepcopy(meta["default"])


def _value(value, meta):
    kind = meta["type"]
    if kind == "object":
        return {
            k: _value(value[k], m)
            if isinstance(value, dict) and k in value
            else _default(m)
            for k, m in meta["items"].items()
        }
    if kind == "template_list":
        if not isinstance(value, list):
            return _default(meta)
        result = []
        seen = set()
        for item in value:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("__template_key"), str)
                or item["__template_key"] not in meta["templates"]
            ):
                continue
            fields = meta["templates"][item["__template_key"]]["items"]
            entry = {
                "__template_key": item["__template_key"],
                **{
                    k: _value(item[k], m) if k in item else _default(m)
                    for k, m in fields.items()
                },
            }
            # 权限与会话模板按类型、类型与 SID 去重。
            if "blocked_sids" in fields or "session_id" in fields:
                key = (entry["__template_key"], entry.get("session_id"))
                if key in seen:
                    continue
                seen.add(key)
            result.append(entry)
        return result
    expected = {
        "bool": bool,
        "int": int,
        "float": float,
        "list": list,
        "string": str,
        "text": str,
    }[kind]
    if type(value) is not expected or (
        "options" in meta and kind != "list" and value not in meta["options"]
    ):
        return _default(meta)
    return value


def heal_astrbot_plugin_config(raw_config, schema):
    root_meta = {"type": "object", "items": schema}
    value = _value(raw_config, root_meta)
    while True:
        try:
            config = SetuPluginConfig.model_validate(value)
            if config.api_type == "custom" and not config.api.custom_api_configs:
                config.setu_general.api_type = SetuPluginConfig().setu_general.api_type
            cleaned = config.model_dump(mode="json", by_alias=True)
            return cleaned, [] if cleaned == raw_config else [
                "已删除失效配置，无效值已恢复默认"
            ]
        except ValidationError as exc:
            # 每次修复一个错误，重新校验后处理剩余字段，避免列表索引漂移。
            error = exc.errors()[0]
            target = value
            meta = root_meta
            parent = None
            parent_key = None
            template_item = None
            for key in error["loc"]:
                if meta["type"] == "template_list" and isinstance(key, int):
                    template_item = (target, key)
                    parent, parent_key = target, key
                    target = target[key]
                    meta = {
                        "type": "object",
                        "items": meta["templates"][target["__template_key"]]["items"],
                    }
                elif meta["type"] == "object" and key in meta["items"]:
                    parent, parent_key = target, key
                    target = target[key]
                    meta = meta["items"][key]
                elif key in ("root", "setu", "fortune"):
                    continue
                else:
                    break
            default = _default(meta)
            if template_item is not None and (
                meta["type"] == "object" or target == default
            ):
                entries, index = template_item
                entries.pop(index)
            else:
                parent[parent_key] = default
