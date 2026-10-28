"""Legacy AstrBot config migration helpers for Setu."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...shared.config.models import HtmlCardStrategyStr

TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enable",
    "enabled",
    "开",
    "开启",
    "启用",
    "是",
}


def record_config_heal(changes: list[str], path: str, reason: str) -> None:
    """Record one config healing decision for startup logs and tests."""
    changes.append(f"{path}: {reason}")


def apply_legacy_config_aliases(
    raw_config: dict[str, Any],
    changes: list[str],
) -> dict[str, Any]:
    """Migrate legacy config keys before schema normalization."""
    normalized = deepcopy(raw_config)
    delivery = normalized.get("delivery")
    legacy_card = normalized.get("html_card")
    if legacy_card is not None or (
        isinstance(delivery, dict) and "html_card_strategy" in delivery
    ):
        if delivery is None:
            delivery = normalized["delivery"] = {}
        if not isinstance(delivery, dict):
            raise TypeError("delivery 必须是 object")
        strategy = delivery.get("html_card_strategy")
        if strategy is None:
            if legacy_card is not None and not isinstance(legacy_card, dict):
                raise TypeError("旧 html_card 必须是 object")
            strategy = (legacy_card or {}).get("strategy", "fallback")
        delivery["html_card_strategy"] = HtmlCardStrategyStr(strategy).value
        record_config_heal(
            changes, "html_card", "migrated to delivery.html_card_strategy"
        )
    if "html_card" in normalized:
        normalized.pop("html_card")
        record_config_heal(changes, "html_card", "removed retired configuration")
    if isinstance(delivery, dict) and "auto_revoke_r18" in delivery:
        legacy_value = delivery.pop("auto_revoke_r18")
        if "auto_revoke_scope" not in delivery:
            delivery["auto_revoke_scope"] = _legacy_revoke_bool_to_scope(legacy_value)
            record_config_heal(
                changes,
                "delivery.auto_revoke_r18",
                "migrated to delivery.auto_revoke_scope",
            )
        else:
            record_config_heal(
                changes,
                "delivery.auto_revoke_r18",
                "removed legacy key because auto_revoke_scope exists",
            )

    if isinstance(delivery, dict) and "doujinshi_file_cleanup_delay" in delivery:
        legacy_value = delivery.pop("doujinshi_file_cleanup_delay")
        if "auto_revoke_delay" not in delivery:
            delivery["auto_revoke_delay"] = legacy_value
            record_config_heal(
                changes,
                "delivery.doujinshi_file_cleanup_delay",
                "migrated to delivery.auto_revoke_delay",
            )
        else:
            record_config_heal(
                changes,
                "delivery.doujinshi_file_cleanup_delay",
                "removed legacy key because auto_revoke_delay exists",
            )

    return normalized


def _legacy_revoke_bool_to_scope(value: Any) -> str:
    """Map the old bool-ish R18 revoke toggle to the new scope enum."""
    if isinstance(value, bool):
        return "r18" if value else "none"
    text = str(value or "").strip().lower()
    return "r18" if text in TRUE_VALUES else "none"
