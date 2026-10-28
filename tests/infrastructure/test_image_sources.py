"""Regression coverage for AstrBot Base64 image components (#44)."""

import base64
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from random import Random
from unittest.mock import AsyncMock, MagicMock

import astrbot.api.message_components as Comp
import pytest
from astrbot_plugin_setu.src.application.setu import ImagePayload
from astrbot_plugin_setu.src.infrastructure.astrbot.config import set_plugin_context
from astrbot_plugin_setu.src.infrastructure.sending.image_sender import ImageSender
from astrbot_plugin_setu.src.infrastructure.sending.image_sources import (
    local_image_path,
)
from astrbot_plugin_setu.src.infrastructure.sending.send_strategies import (
    HtmlCardFallbackStrategy,
)
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig
from PIL import Image, UnidentifiedImageError


@pytest.mark.asyncio
@pytest.mark.parametrize("compress", [False, True])
async def test_large_base64_reaches_sender(compress, sample_config_dict, mock_event):
    buffer = BytesIO()
    Image.frombytes("RGB", (800, 800), Random(44).randbytes(800 * 800 * 3)).save(
        buffer, "PNG"
    )
    data = buffer.getvalue()
    config = SetuPluginConfig(**sample_config_dict)
    sender = ImageSender(config)
    options = await sender._build_options(mock_event)
    sender._build_options = AsyncMock(
        return_value=replace(
            options,
            compress_enabled=compress,
            compress_max_mb=1,
            html_card_strategy="never",
            auto_revoke=False,
        )
    )
    context = MagicMock(send_message=AsyncMock(return_value={"message_id": "ok"}))
    set_plugin_context(context)
    try:
        comp = Comp.Image.fromBytes(data)
        assert len(comp.file) > 1_000_000
        assert await sender._estimate_chain_sizes([comp]) == [
            4 * ((len(data) + 2) // 3)
        ]
        assert sender._image_from_ref(comp.file).file == comp.file
        payload = ImagePayload(urls=(), raw_bytes=(data,), r18=False, tags=())
        result = [item async for item in sender.send_images(payload, mock_event)]
        assert any(
            isinstance(item, dict) and item.get("send_success") for item in result
        )
        sent = context.send_message.call_args_list[0].args[1].result_chain[0]
        sent_bytes = base64.b64decode(sent.file[9:])
        if compress:
            assert len(sent_bytes) <= 1024 * 1024
            with Image.open(BytesIO(sent_bytes)) as image:
                image.load()
                assert image.size == (800, 800)
        else:
            assert sent_bytes == data
    finally:
        set_plugin_context(None)


@pytest.mark.asyncio
async def test_base64_html_fallback_and_invalid_input(mock_event):
    data = b"x" * 800_000
    renderer = MagicMock(render_single_image=AsyncMock(return_value=b"rendered"))
    context = MagicMock(send_message=AsyncMock(return_value={"message_id": "ok"}))
    strategy = HtmlCardFallbackStrategy(context, renderer)
    result = await strategy.send_with_status(mock_event, [Comp.Image.fromBytes(data)])
    assert result.accepted
    assert renderer.render_single_image.call_args.kwargs["image"] == data
    renderer.render_single_image.reset_mock()
    result = await strategy.send_with_status(
        mock_event, [Comp.Image(file="base64://!invalid!")]
    )
    assert not result.accepted
    renderer.render_single_image.assert_not_called()
    renderer.render_single_image.side_effect = RuntimeError("t2i failure details")
    result = await strategy.send_with_status(mock_event, [Comp.Image.fromBytes(data)])
    assert result.reason == "t2i failure details"


def test_local_and_remote_image_references(tmp_path, monkeypatch):
    path = tmp_path / "image with 空格.png"
    path.write_bytes(b"image")
    assert local_image_path(path) == path
    assert local_image_path(path.as_uri()) == path
    assert (
        local_image_path(path.as_uri().replace("file:///", "file://localhost/")) == path
    )

    def no_stat(self):
        raise AssertionError("non-local references must not access filesystem")

    monkeypatch.setattr(Path, "exists", no_stat)
    for ref in (
        "https://example.com/" + "a" * 10000,
        "http://example.com/img",
        "base64://" + "a" * 1000000,
        "file://remote/image",
    ):
        assert local_image_path(ref) is None


@pytest.mark.asyncio
async def test_html_renderer_rejects_upstream_error_page(monkeypatch):
    from astrbot_plugin_setu.src.infrastructure.sending import html_card_renderer

    monkeypatch.setattr(
        html_card_renderer.html_renderer,
        "render_custom_template",
        AsyncMock(return_value=b"<html>502 Bad Gateway</html>"),
    )
    with pytest.raises(UnidentifiedImageError):
        await html_card_renderer.HtmlCardRenderer().render_single_image(
            context=None, image=b"image", style_options={}
        )
