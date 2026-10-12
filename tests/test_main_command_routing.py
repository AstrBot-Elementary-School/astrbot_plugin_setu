from __future__ import annotations

import re

import pytest

from astrbot_plugin_setu.main import (
    DOUJINSHI_REGEX_PATTERN,
    FORTUNE_REGEX_PATTERN,
    REGEX_COMMAND_PATTERN,
    SETU_REGEX_PATTERN,
    _is_fortune_command_invocation,
    _route_regex_command,
    _resolve_fortune_refresh_target,
    _resolve_fortune_toggle_action,
    _resolve_fortune_user_action,
)


class _RegexHandler:
    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.doujinshi_tags: list[str] = []

    async def get_random_picture(self, event):
        yield self.marker

    async def random_doujinshi_command(self, event, *, tags: str = ""):
        self.doujinshi_tags.append(tags)
        yield "doujinshi"

    async def fortune_command(self, event):
        yield self.marker


def test_resolve_fortune_refresh_target_from_new_command(mock_event) -> None:
    mock_event.message_str = "/运势刷新 本群"
    assert _resolve_fortune_refresh_target(mock_event, "本群") == "group"


def test_resolve_fortune_refresh_target_from_legacy_alias(mock_event) -> None:
    mock_event.message_str = "/刷新全局今日运势"
    assert _resolve_fortune_refresh_target(mock_event, "") == "all"


def test_resolve_fortune_toggle_action_from_new_command(mock_event) -> None:
    mock_event.message_str = "/运势开关 关"
    assert _resolve_fortune_toggle_action(mock_event, "关") == "disable"


def test_resolve_fortune_toggle_action_from_legacy_alias(mock_event) -> None:
    mock_event.message_str = "/开启运势"
    assert _resolve_fortune_toggle_action(mock_event, "") == "enable"


def test_resolve_fortune_user_action_from_new_command(mock_event) -> None:
    mock_event.message_str = "/运势用户 拉黑 12345"
    assert _resolve_fortune_user_action(mock_event, "拉黑 12345") == ("block", "12345")


def test_resolve_fortune_user_action_from_legacy_alias(mock_event) -> None:
    mock_event.message_str = "/取消运势信任 12345"
    assert _resolve_fortune_user_action(mock_event, "12345") == ("untrust", "12345")


def test_fortune_regex_pattern_matches_plain_jrys() -> None:
    assert re.match(FORTUNE_REGEX_PATTERN, "jrys")
    assert re.match(FORTUNE_REGEX_PATTERN, "今日运势")
    assert not re.match(FORTUNE_REGEX_PATTERN, "/jrys")


def test_combined_regex_pattern_matches_both_plain_command_families() -> None:
    assert re.match(REGEX_COMMAND_PATTERN, "来一份色图")
    assert re.match(REGEX_COMMAND_PATTERN, "来份本子")
    assert re.match(REGEX_COMMAND_PATTERN, "jrys")


@pytest.mark.parametrize(
    "message",
    ["来一张色图 r18", "来一张初音ミク r18 色图", "来一张色图 R18 r18"],
)
def test_regex_accepts_request_r18_marker(message):
    from astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu import (
        SETU_REGEX_PATTERN as handler_pattern,
    )

    assert SETU_REGEX_PATTERN == handler_pattern
    assert re.match(REGEX_COMMAND_PATTERN, message)


@pytest.mark.asyncio
async def test_regex_router_dispatches_request_with_r18_marker(mock_event):
    mock_event.message_str = "来一张色图 r18"
    results = [
        result
        async for result in _route_regex_command(
            mock_event, _RegexHandler("setu"), None
        )
    ]
    assert results == ["setu"]


def test_doujinshi_regex_pattern_accepts_common_spacing() -> None:
    assert re.match(DOUJINSHI_REGEX_PATTERN, "来份本子")
    assert re.match(DOUJINSHI_REGEX_PATTERN, "来一份本子")
    tagged_match = re.match(DOUJINSHI_REGEX_PATTERN, "来份碧蓝档案本子")
    assert tagged_match and tagged_match.group("tags") == "碧蓝档案"
    assert not re.match(DOUJINSHI_REGEX_PATTERN, "来两份本子")


@pytest.mark.asyncio
async def test_regex_router_dispatches_setu_and_fortune(mock_event) -> None:
    setu_handler = _RegexHandler("setu")
    fortune_handler = _RegexHandler("fortune")

    mock_event.message_str = "来一份色图"
    setu_results = [
        result
        async for result in _route_regex_command(
            mock_event, setu_handler, fortune_handler
        )
    ]
    mock_event.message_str = "jrys"
    fortune_results = [
        result
        async for result in _route_regex_command(
            mock_event, setu_handler, fortune_handler
        )
    ]

    assert setu_results == ["setu"]
    assert fortune_results == ["fortune"]

    mock_event.message_str = "来份碧蓝档案本子"
    doujinshi_results = [
        result
        async for result in _route_regex_command(
            mock_event, setu_handler, fortune_handler
        )
    ]

    assert doujinshi_results == ["doujinshi"]
    assert setu_handler.doujinshi_tags == ["碧蓝档案"]


def test_fortune_regex_dedup_skips_command_invocation(mock_event) -> None:
    mock_event.is_at_or_wake_command = True
    mock_event.message_str = "/jrys"
    assert _is_fortune_command_invocation(mock_event) is True
    mock_event.message_str = "/今日运势"
    assert _is_fortune_command_invocation(mock_event) is True
    mock_event.message_str = "!jrys"
    assert _is_fortune_command_invocation(mock_event) is True
    mock_event.message_str = "。今日运势"
    assert _is_fortune_command_invocation(mock_event) is True

    mock_event.is_at_or_wake_command = False
    mock_event.message_str = "jrys"
    assert _is_fortune_command_invocation(mock_event) is False
