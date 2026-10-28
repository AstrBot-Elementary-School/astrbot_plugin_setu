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

    async def setu_command(self, event, count="1", *, tags="", natural=False):
        yield self.marker

    async def random_doujinshi_command(self, event, *, tags: str = ""):
        self.doujinshi_tags.append(tags)
        yield "doujinshi"

    async def fortune_command(self, event):
        yield self.marker


@pytest.mark.asyncio
async def test_regex_router_dispatches_setu_and_fortune(
    mock_event, monkeypatch
) -> None:
    from astrbot_plugin_setu.src.shared.config import SetuPluginConfig

    monkeypatch.setattr(
        "astrbot_plugin_setu.main.get_config", lambda: SetuPluginConfig()
    )
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


@pytest.mark.asyncio
async def test_custom_phrases_first_match_disable_and_command_dedup(
    mock_event, monkeypatch
):
    from astrbot_plugin_setu import main
    from astrbot_plugin_setu.src.shared.config import SetuPluginConfig

    config = SetuPluginConfig(
        setu_general={
            "trigger_templates": [
                {"__template_key": "setu", "phrase": "来{数量}张{标签}"},
                {"__template_key": "doujinshi", "phrase": "来{标签}"},
                {"__template_key": "fortune", "phrase": "占卜一下"},
            ]
        }
    )
    monkeypatch.setattr(main, "get_config", lambda: config)
    mock_event.message_str = "来2张白丝"
    matched = main._match_natural_trigger(mock_event)
    assert (matched.kind, matched.count, matched.tags) == ("setu", "2", "白丝")
    mock_event.message_str = "来张"
    matched = main._match_natural_trigger(mock_event)
    assert (matched.count, matched.tags) == ("1", "")
    mock_event.message_str = "占卜一下"
    assert main.NaturalLanguageFilter().filter(mock_event, None)
    config.setu_general.natural_language_enabled = False
    assert not main.NaturalLanguageFilter().filter(mock_event, None)
    config.setu_general.natural_language_enabled = True
    config.setu_general.trigger_templates = []
    mock_event.message_str = "来一份色图"
    assert main._match_natural_trigger(mock_event) is None
    config = SetuPluginConfig()
    mock_event.message_str = "jrys"
    mock_event.is_at_or_wake_command = True
    assert main._match_natural_trigger(mock_event) is None


def test_builtin_grammar_and_literal_phrase_compatibility():
    from astrbot_plugin_setu.src.domain.setu.triggers import (
        compile_trigger,
        match_trigger,
    )
    from astrbot_plugin_setu.src.shared.config.models import SetuGeneralConfig

    rules = SetuGeneralConfig().trigger_templates
    for phrase, kind, count, tags in [
        ("来三份白丝瑟图", "setu", "三", "白丝"),
        ("来9份白丝 萝莉色图", "setu", "9", "白丝 萝莉"),
        ("来份图 r18", "setu", "1", "r18"),
        ("来份碧蓝档案本子", "doujinshi", "1", "碧蓝档案"),
        ("今日运势", "fortune", "1", ""),
    ]:
        match = match_trigger(phrase, rules)
        assert (match.kind, match.count, match.tags) == (kind, count, tags)
    literal = compile_trigger("setu", "给我[图片].{标签}")
    assert literal.fullmatch("给我[图片].白丝")
    assert not literal.fullmatch("给我图x白丝")
    for kind, phrase in [
        ("setu", "{未知}"),
        ("setu", "{标签}{标签}"),
        ("fortune", "{标签}"),
        ("setu", "{数量:03}"),
        ("setu", "{"),
    ]:
        with pytest.raises(ValueError):
            compile_trigger(kind, phrase)
