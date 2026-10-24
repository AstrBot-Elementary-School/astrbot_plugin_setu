from __future__ import annotations

import pytest
from astrbot_plugin_setu.main import (
    _is_fortune_command_invocation,
    _route_regex_command,
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
