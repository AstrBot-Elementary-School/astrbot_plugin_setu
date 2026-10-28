"""Schema-driven AstrBot config self-healing."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .legacy_migration import apply_legacy_config_aliases, record_config_heal

_SCHEMA_DEFAULTS: dict[str, Any] = {
    "bool": False,
    "int": 0,
    "float": 0.0,
    "list": [],
    "object": {},
    "string": "",
    "template_list": [],
    "text": "",
}


def _schema_default(meta: dict[str, Any]) -> Any:
    if "default" in meta:
        return deepcopy(meta["default"])
    meta_type = meta.get("type")
    if meta_type == "object":
        return {
            key: _schema_default(item)
            for key, item in (meta.get("items") or {}).items()
            if isinstance(item, dict)
        }
    return deepcopy(_SCHEMA_DEFAULTS.get(str(meta_type), None))


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _normalize_list_value(
    value: Any,
    meta: dict[str, Any],
    path: str,
    changes: list[str],
) -> list[Any]:
    if not isinstance(value, list):
        record_config_heal(changes, path, "reset invalid list")
        return _schema_default(meta)
    return list(value)


def _normalize_template_list_value(
    value: Any,
    meta: dict[str, Any],
    path: str,
    changes: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        record_config_heal(changes, path, "reset invalid template_list")
        return _schema_default(meta)

    templates = meta.get("templates")
    if not isinstance(templates, dict):
        return [item for item in value if isinstance(item, dict)]

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            record_config_heal(changes, item_path, "removed invalid template item")
            continue
        template_key = item.get("__template_key")
        template_meta = templates.get(template_key)
        if not isinstance(template_key, str) or not isinstance(template_meta, dict):
            record_config_heal(changes, item_path, "removed unknown template item")
            continue
        template_items = template_meta.get("items")
        if not isinstance(template_items, dict):
            normalized.append({"__template_key": template_key})
            continue

        normalized_item = {"__template_key": template_key}
        for key, child_meta in template_items.items():
            child_path = f"{item_path}.{key}"
            if key in item:
                normalized_item[key] = _normalize_schema_value(
                    item[key],
                    child_meta,
                    child_path,
                    changes,
                )
            else:
                normalized_item[key] = _schema_default(child_meta)
                record_config_heal(changes, child_path, "added missing default")
        for key in item:
            if key != "__template_key" and key not in template_items:
                record_config_heal(changes, f"{item_path}.{key}", "removed unknown key")
        normalized.append(normalized_item)
    return normalized


def _normalize_schema_value(
    value: Any,
    meta: dict[str, Any],
    path: str,
    changes: list[str],
) -> Any:
    meta_type = meta.get("type")

    if value is None:
        record_config_heal(changes, path, "reset null value")
        return _schema_default(meta)

    if meta_type == "object":
        if not isinstance(value, dict):
            record_config_heal(changes, path, "reset invalid object")
            return _schema_default(meta)
        items = meta.get("items")
        if not isinstance(items, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, child_meta in items.items():
            child_path = f"{path}.{key}" if path else key
            if key in value:
                normalized[key] = _normalize_schema_value(
                    value[key],
                    child_meta,
                    child_path,
                    changes,
                )
            else:
                normalized[key] = _schema_default(child_meta)
                record_config_heal(changes, child_path, "added missing default")
        for key in value:
            if key not in items:
                normalized[key] = deepcopy(value[key])
        return normalized

    if meta_type == "template_list":
        return _normalize_template_list_value(value, meta, path, changes)

    if meta_type == "list":
        return _normalize_list_value(value, meta, path, changes)

    if meta_type == "int":
        coerced = _coerce_int(value)
        if coerced is None:
            record_config_heal(changes, path, "reset invalid int")
            return _schema_default(meta)
        if coerced != value:
            record_config_heal(changes, path, "coerced int")
        return coerced

    if meta_type == "bool":
        if not isinstance(value, bool):
            record_config_heal(changes, path, "reset invalid bool")
            return _schema_default(meta)
        return value

    if meta_type in {"string", "text"}:
        if not isinstance(value, str):
            record_config_heal(changes, path, "reset invalid string")
            return _schema_default(meta)
        options = meta.get("options")
        if isinstance(options, list) and value not in options:
            record_config_heal(changes, path, "reset invalid option")
            return _schema_default(meta)
        return value

    return value


def heal_astrbot_plugin_config(
    raw_config: dict[str, Any] | None,
    schema: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Project raw AstrBot config onto the current plugin schema."""
    if raw_config is None:
        return {}, []
    if not isinstance(raw_config, dict) or not isinstance(schema, dict):
        return dict(raw_config or {}), []

    changes: list[str] = []
    aliased = apply_legacy_config_aliases(raw_config, changes)
    for key in ("messages", "message_overrides", "cache", "fortune_session_configs"):
        if key in aliased:
            aliased.pop(key)
            record_config_heal(changes, key, "removed retired configuration")
    for section, keys in {
        "setu_general": ("max_replenish_rounds", "multi_api_strategy"),
        "fortune": ("api_type",),
        "html_card": ("card_padding", "card_gap", "mode"),
        "delivery": ("napcat_stream_chunk_kb",),
    }.items():
        value = aliased.get(section)
        if isinstance(value, dict):
            for key in keys:
                if key in value:
                    value.pop(key)
                    record_config_heal(
                        changes, f"{section}.{key}", "removed retired configuration"
                    )
    normalized = _normalize_schema_value(
        aliased, {"type": "object", "items": schema}, "", changes
    )
    # The nullable schema default distinguishes a missing new key from an explicit fallback.
    delivery = normalized.get("delivery")
    if (
        isinstance(delivery, dict)
        and "html_card_strategy" in delivery
        and delivery["html_card_strategy"] is None
    ):
        delivery["html_card_strategy"] = "fallback"
        record_config_heal(changes, "delivery.html_card_strategy", "applied default")
    normalized.pop("html_card", None)
    if normalized == raw_config:
        changes.clear()
    return normalized, changes
