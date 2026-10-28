"""Shared fixtures for AstrBot Setu plugin tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

for parent in Path(__file__).resolve().parents:
    if (parent / "astrbot" / "core" / "__init__.py").exists():
        os.environ.setdefault("ASTRBOT_ROOT", str(parent))
        break

from astrbot.api.event import AstrMessageEvent  # noqa: E402


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create temporary data directory for tests.

    Args:
        tmp_path: Pytest temporary path fixture

    Returns:
        Temporary data directory
    """
    data_dir = tmp_path / "plugin_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def mock_event() -> AstrMessageEvent:
    """Create mock AstrMessageEvent.

    Returns:
        Mock event with common attributes
    """
    event = MagicMock(spec=AstrMessageEvent)
    event.get_sender_id = MagicMock(return_value="test_user_123")
    event.get_group_id = MagicMock(return_value="test_group_456")
    event.get_session_id = MagicMock(return_value="test_group_456_test_user_123")
    event.get_self_id = MagicMock(return_value="test_bot_789")
    event.get_messages = MagicMock(return_value=[])
    event.get_message_str = MagicMock(return_value="/setu 3")
    event.message_str = "/setu 3"
    event.unified_msg_origin = "test_platform:12345"
    event.platform = MagicMock()
    event.platform.name = "test_platform"
    event.is_at_or_wake_command = False

    # Message chain results
    def plain_result_fn(text: str) -> Any:
        result = MagicMock()
        result.result_chain = [MagicMock(text=text)]
        return result

    event.plain_result = MagicMock(side_effect=plain_result_fn)

    def chain_result_fn(chain: list[Any]) -> Any:
        result = MagicMock()
        result.result_chain = chain
        return result

    event.chain_result = MagicMock(side_effect=chain_result_fn)

    return event


@pytest.fixture
def sample_config_dict() -> dict[str, Any]:
    """Create sample plugin configuration.

    Returns:
        Configuration dict matching _conf_schema.json structure
    """
    return {
        "setu_general": {
            "api_type": "lolicon",
            "content_mode": "sfw",
            "max_count": 10,
        },
        "delivery": {
            "send_mode": "auto",
            "html_card_strategy": "fallback",
            "doujinshi_send_mode": "pdf",
            "r18_docx_mode": True,
            "auto_revoke_scope": "none",
            "auto_revoke_delay": 30,
            "platform_transports": [],
        },
        "fortune": {
            "enabled": True,
            "tags": "",
            "content_mode": "sfw",
            "allow_user_refresh": False,
            "auto_refresh": True,
        },
        "api": {
            "provider_overrides": [
                {
                    "__template_key": "lolicon",
                    "image_size": "original",
                    "proxy": "",
                    "aspect_ratio": "",
                    "uid": [],
                    "keyword": "",
                    "exclude_ai": True,
                },
                {
                    "__template_key": "sexnyan",
                    "proxy": "",
                    "uid": [],
                    "keyword": "",
                },
            ],
            "custom_api_configs": [],
        },
        "safety": [],
        "session_configs": [],
    }
