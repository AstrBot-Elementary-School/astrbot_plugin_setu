"""SID policies are the sole authority for every member of a conversation."""

import pytest
from astrbot_plugin_setu.src.domain.access_control.service import AccessControlService
from astrbot_plugin_setu.src.infrastructure.persistence import ConfigAccessControlRepo
from astrbot_plugin_setu.src.shared.config.models import SafetyConfig
from pydantic import ValidationError

SID = "bot:GroupMessage:123"


def test_features_and_exact_sid_are_independent() -> None:
    service = AccessControlService(
        ConfigAccessControlRepo(
            SafetyConfig.model_validate(
                [
                    {
                        "__template_key": "setu",
                        "mode": "whitelist",
                        "whitelist_sids": [SID],
                    },
                    {
                        "__template_key": "fortune",
                        "mode": "blacklist",
                        "blocked_sids": [SID],
                    },
                ]
            )
        )
    )
    assert service.check_access("setu", SID)
    assert not service.check_access("fortune", SID)
    for other in ("other:GroupMessage:123", "bot:FriendMessage:123", None):
        assert not service.check_access("setu", other)
    assert service.check_access("fortune", "other:GroupMessage:123")
    assert not service.check_access("fortune", None)


def test_missing_rule_and_empty_whitelist() -> None:
    service = AccessControlService(
        ConfigAccessControlRepo(
            SafetyConfig.model_validate(
                [
                    {"__template_key": "setu", "mode": "whitelist"},
                ]
            )
        )
    )
    assert not service.check_access("setu", SID)
    assert service.check_access("fortune", SID)
    assert service.check_access("fortune", None)


@pytest.mark.parametrize(
    "rule",
    [
        {"blocked_sids": [SID], "whitelist_sids": [" " + SID + " "]},
        {"blocked_sids": ["123"]},
        {"blocked_sids": ["bot::123"]},
        {"blocked_sids": [""]},
        {"mode": "bad"},
    ],
)
def test_invalid_rule_rejected(rule) -> None:
    with pytest.raises(ValidationError):
        SafetyConfig.model_validate([{"__template_key": "setu", **rule}])


def test_duplicate_templates_rejected() -> None:
    rule = {"__template_key": "setu"}
    with pytest.raises(ValidationError, match="重复"):
        SafetyConfig.model_validate([rule, rule])


@pytest.mark.asyncio
@pytest.mark.parametrize("feature", ["setu", "fortune"])
async def test_handlers_use_sid_not_sender(monkeypatch, feature) -> None:
    from importlib import import_module
    from types import SimpleNamespace

    module = import_module(
        f"astrbot_plugin_setu.src.infrastructure.astrbot.commands.{feature}"
    )
    repo = ConfigAccessControlRepo(
        SafetyConfig.model_validate(
            [
                {"__template_key": feature, "mode": "blacklist", "blocked_sids": [SID]},
            ]
        )
    )
    monkeypatch.setattr(module, "get_access_control_repo", lambda: repo)
    cls = (
        module.SetuCommandHandler if feature == "setu" else module.FortuneCommandHandler
    )
    handler = cls()
    monkeypatch.setattr(handler, "_message", lambda key: key)
    for sender in ("member1", "member2"):
        event = SimpleNamespace(
            unified_msg_origin=SID,
            get_sender_id=lambda sender=sender: sender,
            get_group_id=lambda: "123",
        )
        assert await handler._check_access(event, None) == (False, "access_denied")
        event.unified_msg_origin = "other:GroupMessage:123"
        assert await handler._check_access(event, None) == (True, "")
