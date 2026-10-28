"""Tests for image sender transport behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import astrbot.api.message_components as Comp
import pytest
from astrbot_plugin_setu.src.application.setu import ImagePayload
from astrbot_plugin_setu.src.infrastructure.astrbot.config import (
    clear_config,
    set_plugin_context,
)
from astrbot_plugin_setu.src.infrastructure.sending import image_sender
from astrbot_plugin_setu.src.infrastructure.sending.dto import SendOptions
from astrbot_plugin_setu.src.infrastructure.sending.image_sender import ImageSender
from astrbot_plugin_setu.src.infrastructure.sending.revoke_scheduler import (
    RecoverableRevokeScheduler,
)
from astrbot_plugin_setu.src.infrastructure.sending.send_strategies import (
    DirectSendStrategy,
    ForwardSendStrategy,
)
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig
from astrbot_plugin_setu.src.shared.send_cache import clear_send_cache, init_send_cache


def with_napcat_transport(config_dict: dict[str, Any], **values: Any) -> dict[str, Any]:
    """Return config dict with a NapCat platform transport template."""
    updated = config_dict.copy()
    updated["delivery"] = {
        **config_dict["delivery"],
        "platform_transports": [{"__template_key": "napcat", **values}],
    }
    return updated


@pytest.fixture(autouse=True)
def reset_singletons() -> None:
    """Keep config/context singletons isolated."""
    clear_config()
    clear_send_cache()
    yield
    clear_send_cache()
    clear_config()


@pytest.mark.asyncio
async def test_send_images_streams_on_fallback(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    """A failed normal path send uses NapCat stream upload and retries once."""
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    sent_results: list[Any] = []

    async def send_message(_origin: str, result: Any) -> Any:
        sent_results.append(result)
        if len(sent_results) == 1:
            raise RuntimeError("direct image send failed")
        return {"message_id": "streamed"}

    context.send_message.side_effect = send_message
    set_plugin_context(context)

    mock_event.platform.name = "aiocqhttp"
    mock_event.bot = MagicMock()
    mock_event.bot.api = None

    async def call_action(action: str, **params: Any) -> dict[str, Any]:
        assert action == "upload_file_stream"
        if params.get("is_complete"):
            return {
                "status": "ok",
                "retcode": 0,
                "data": {"file_path": "stream://image"},
            }
        return {"status": "ok", "retcode": 0, "data": {}}

    mock_event.bot.call_action = AsyncMock(side_effect=call_action)

    config = SetuPluginConfig(**sample_config_dict)
    payload = ImagePayload(
        urls=("https://example.com/image.jpg",),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1}]
    assert len(sent_results) == 3
    retried_chain = sent_results[1].result_chain
    assert retried_chain[0].file == "stream://image"
    assert mock_event.bot.call_action.called


@pytest.mark.asyncio
async def test_send_images_does_not_fallback_when_send_ack_times_out(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    """平台确认超时时不立刻降级，避免原图稍后送达时重复发送 fallback。"""
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    context.send_message = AsyncMock(side_effect=TimeoutError("adapter ack timeout"))
    set_plugin_context(context)

    mock_event.platform.name = "aiocqhttp"
    mock_event.bot = MagicMock()
    mock_event.bot.call_action = AsyncMock()

    config = SetuPluginConfig(**sample_config_dict)
    payload = ImagePayload(
        urls=("https://example.com/image.jpg",),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1, "send_pending": True}]
    assert context.send_message.await_count == 2
    mock_event.bot.call_action.assert_not_called()


@pytest.mark.asyncio
async def test_send_images_treats_napcat_none_ack_as_pending(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    """NapCat 未返回 message id 时不立刻降级，避免延迟送达后重复发图。"""
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    context.send_message = AsyncMock(return_value=None)
    set_plugin_context(context)

    mock_event.platform.name = "napcat"
    mock_event.bot = MagicMock()
    mock_event.bot.call_action = AsyncMock()

    config = SetuPluginConfig(**sample_config_dict)
    payload = ImagePayload(
        urls=("https://example.com/image.jpg",),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1, "send_pending": True}]
    assert context.send_message.await_count == 2
    mock_event.bot.call_action.assert_not_called()


@pytest.mark.asyncio
async def test_send_images_reports_partial_batch_failure(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    """部分批次失败时不能把整体发送报告为成功。"""
    image_paths: list[Path] = []
    for index in range(9):
        image_path = tmp_path / f"image-{index}.jpg"
        image_path.write_bytes(f"image-data-{index}".encode())
        image_paths.append(image_path)

    context = MagicMock()
    sent_results: list[Any] = []

    async def send_message(_origin: str, result: Any) -> dict[str, str]:
        sent_results.append(result)
        if len(sent_results) == 2:
            raise RuntimeError("second batch failed")
        return {"message_id": "first-batch"}

    context.send_message = AsyncMock(side_effect=send_message)
    set_plugin_context(context)

    mock_event.platform.name = "aiocqhttp"
    mock_event.bot = MagicMock()
    mock_event.bot.call_action = AsyncMock()

    config_dict = sample_config_dict
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "send_mode": "image",
        "napcat_stream_mode": "disabled",
    }
    config_dict["delivery"] = {
        **config_dict["delivery"],
        "html_card_strategy": "never",
    }
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=tuple(f"https://example.com/image-{index}.jpg" for index in range(9)),
        raw_bytes=(),
        file_paths=tuple(image_paths),
        items=tuple(image_paths),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results[-1:] == [
        {"send_success": False, "image_count": 9, "partial_failure": True}
    ]
    assert context.send_message.await_count == 2
    mock_event.bot.call_action.assert_not_called()


@pytest.mark.asyncio
async def test_send_images_does_not_fallback_when_forward_ack_times_out(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    """合并转发确认超时时同样不触发流式或 HTML 降级。"""
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    image_a.write_bytes(b"image-a")
    image_b.write_bytes(b"image-b")

    context = MagicMock()
    context.send_message = AsyncMock(side_effect=TimeoutError("forward ack timeout"))
    set_plugin_context(context)

    mock_event.platform.name = "aiocqhttp"
    mock_event.bot = MagicMock()
    mock_event.bot.call_action = AsyncMock()

    config_dict = sample_config_dict
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=("https://example.com/a.jpg", "https://example.com/b.jpg"),
        raw_bytes=(),
        file_paths=(image_a, image_b),
        items=(image_a, image_b),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 2, "send_pending": True}]
    assert context.send_message.await_count == 2
    mock_event.bot.call_action.assert_not_called()


@pytest.mark.asyncio
async def test_send_images_materializes_local_files_before_direct_send(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    sent_results: list[Any] = []

    async def send_message(_origin: str, result: Any) -> dict[str, str]:
        sent_results.append(result)
        return {"message_id": "ok"}

    context.send_message = AsyncMock(side_effect=send_message)
    set_plugin_context(context)

    config_dict = with_napcat_transport(sample_config_dict, stream_mode="disabled")
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=(),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1}]
    image_comp = sent_results[0].result_chain[0]
    assert isinstance(image_comp, Comp.Image)
    assert isinstance(image_comp.file, str)
    assert image_comp.file.startswith("base64://")


@pytest.mark.asyncio
async def test_send_images_passthroughs_local_file_when_always_enabled(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    image_path = tmp_path / "shared" / "image.jpg"
    image_path.parent.mkdir()
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    context.send_message = AsyncMock(return_value={"message_id": "found"})
    set_plugin_context(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "ok"})

    config_dict = with_napcat_transport(
        sample_config_dict,
        local_file_mode="always",
        local_file_allowed_roots=[str(tmp_path / "shared")],
    )
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=(),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1}]
    mock_event.bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[{"type": "image", "data": {"file": image_path.resolve().as_uri()}}],
    )
    assert context.send_message.await_count == 1


@pytest.mark.asyncio
async def test_send_images_local_file_fallback_runs_before_stream(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    image_path = tmp_path / "shared" / "image.jpg"
    image_path.parent.mkdir()
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    sent_results: list[Any] = []

    async def send_message(_origin: str, result: Any) -> Any:
        sent_results.append(result)
        raise RuntimeError("direct image send failed")

    context.send_message.side_effect = send_message
    set_plugin_context(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "ok"})
    mock_event.bot.call_action = AsyncMock()

    config_dict = with_napcat_transport(
        sample_config_dict,
        local_file_mode="fallback",
        local_file_allowed_roots=[str(tmp_path / "shared")],
        stream_mode="fallback",
    )
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=(),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1}]
    mock_event.bot.send_group_msg.assert_awaited_once()
    mock_event.bot.call_action.assert_not_called()
    assert len(sent_results) == 2


@pytest.mark.asyncio
async def test_send_images_uses_fixed_stream_chunk_size(
    tmp_path: Path, mock_event, sample_config_dict, monkeypatch
) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")
    captured: dict[str, int] = {}

    async def fake_upload_file_stream(
        event: Any,
        file_path: Path,
        *,
        chunk_size: int,
    ) -> str:
        captured["chunk_size"] = chunk_size
        return "stream://image"

    monkeypatch.setattr(image_sender, "upload_file_stream", fake_upload_file_stream)

    context = MagicMock()
    context.send_message = AsyncMock(return_value={"message_id": "found"})
    set_plugin_context(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "ok"})

    config_dict = with_napcat_transport(
        sample_config_dict, stream_mode="always", stream_chunk_kb=512
    )
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=(),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1}]
    assert captured["chunk_size"] == 64 * 1024


@pytest.mark.asyncio
async def test_local_file_passthrough_allows_send_cache_root(
    tmp_path: Path, sample_config_dict
) -> None:
    cache = await init_send_cache(
        tmp_path,
        enabled=True,
        ttl_hours=1,
        max_items=10,
        cleanup_on_start=False,
    )
    image_path = cache.root / "image.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"image-data")

    config = SetuPluginConfig(**sample_config_dict)
    options = SendOptions(
        send_mode="image",
        use_html_card=False,
        auto_revoke=False,
        revoke_delay=30,
        r18_docx_mode=False,
    )
    sender = ImageSender(config)

    chain = sender._local_file_passthrough_chain(
        [Comp.Image.fromFileSystem(str(image_path))], options
    )

    assert chain is not None
    assert chain[0].file == image_path.resolve().as_uri()


def test_local_file_passthrough_rejects_untrusted_paths(
    tmp_path: Path, sample_config_dict
) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / "image.jpg"
    outside_file.write_bytes(b"image-data")
    symlink_path = allowed_root / "linked.jpg"
    symlink_path.symlink_to(outside_file)

    config = SetuPluginConfig(**sample_config_dict)
    options = SendOptions(
        send_mode="image",
        use_html_card=False,
        auto_revoke=False,
        revoke_delay=30,
        r18_docx_mode=False,
        napcat_local_file_allowed_roots=(str(allowed_root),),
    )
    sender = ImageSender(config)

    assert (
        sender._local_file_passthrough_chain(
            [Comp.Image.fromFileSystem(str(outside_file))], options
        )
        is None
    )
    assert (
        sender._local_file_passthrough_chain(
            [Comp.Image.fromFileSystem(str(symlink_path))], options
        )
        is None
    )
    assert sender._trusted_local_file_path(Path(outside_file.name), options) is None
    assert sender._trusted_local_file_path(outside_root, options) is None
    assert (
        sender._trusted_local_file_path(outside_root / "missing.jpg", options) is None
    )


@pytest.mark.asyncio
async def test_html_card_only_preserves_pending_send_status(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    context.send_message = AsyncMock(side_effect=TimeoutError("html ack timeout"))
    set_plugin_context(context)

    class FakeHtmlRenderer:
        async def render_single_image(self, **kwargs) -> bytes:
            return b"html-card"

    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **config_dict["delivery"],
        "html_card_strategy": "always",
    }
    config_dict["messages"] = {
        **sample_config_dict.get("messages", {}),
        "found": {"enabled": False, "text": "找到 {count} 张符合要求的图片~"},
    }
    config = SetuPluginConfig(**config_dict)
    sender = ImageSender(config)
    sender.set_html_renderer(FakeHtmlRenderer())
    payload = ImagePayload(
        urls=("https://example.com/image.jpg",),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [item async for item in sender.send_images(payload, mock_event)]

    assert results == [{"send_success": True, "image_count": 1, "send_pending": True}]


@pytest.mark.asyncio
async def test_direct_send_strategy_passthroughs_napcat_stream_refs(mock_event) -> None:
    """NapCat 也走 OneBot 图片引用直通，避免 stream:// 被普通链路改写。"""
    context = MagicMock()
    strategy = DirectSendStrategy(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "ok"})

    success = await strategy.send(mock_event, [Comp.Image(file="stream://image")])

    assert success is True
    mock_event.bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[{"type": "image", "data": {"file": "stream://image"}}],
    )


@pytest.mark.asyncio
async def test_direct_send_strategy_keeps_file_uri_on_normal_chain_by_default(
    tmp_path: Path, mock_event
) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")
    context = MagicMock()
    context.send_message = AsyncMock(return_value={"message_id": "ok"})
    strategy = DirectSendStrategy(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock()

    success = await strategy.send(mock_event, [Comp.Image(file=image_path.as_uri())])

    assert success is True
    context.send_message.assert_awaited_once()
    mock_event.bot.send_group_msg.assert_not_called()


@pytest.mark.asyncio
async def test_direct_send_strategy_passthroughs_file_uri_when_allowed(
    tmp_path: Path, mock_event
) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")
    context = MagicMock()
    strategy = DirectSendStrategy(context, allow_file_uri_passthrough=True)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "ok"})

    success = await strategy.send(mock_event, [Comp.Image(file=image_path.as_uri())])

    assert success is True
    mock_event.bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[{"type": "image", "data": {"file": image_path.as_uri()}}],
    )


@pytest.mark.asyncio
async def test_direct_send_strategy_keeps_none_passthrough_ack_pending(
    mock_event,
) -> None:
    """OneBot 直通已尝试但无确认时，不再落回普通发送链路。"""
    context = MagicMock()
    context.send_message = AsyncMock()
    strategy = DirectSendStrategy(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value=None)

    result = await strategy.send_with_status(
        mock_event,
        [Comp.Image(file="stream://image")],
    )

    assert result.accepted is True
    assert result.pending is True
    mock_event.bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[{"type": "image", "data": {"file": "stream://image"}}],
    )
    context.send_message.assert_not_called()


@pytest.mark.parametrize(
    ("scope", "is_r18", "revoke_delay", "expected_scheduled"),
    [
        ("none", False, 30, 0),
        ("sfw", False, 30, 1),
        ("sfw", True, 30, 0),
        ("r18", False, 30, 0),
        ("r18", True, 30, 1),
        ("all", False, 30, 1),
        ("all", True, 30, 1),
        ("all", False, 0, 0),
    ],
)
@pytest.mark.asyncio
async def test_send_images_schedules_revoke_by_scope(
    tmp_path: Path,
    mock_event,
    sample_config_dict,
    monkeypatch,
    scope: str,
    is_r18: bool,
    revoke_delay: int,
    expected_scheduled: int,
) -> None:
    """自动撤回范围按 SFW/R18/全部/关闭计算。"""
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")
    scheduled: list[tuple[str, int]] = []

    async def fake_schedule_revoke(_event: Any, message_id: str, delay: int) -> bool:
        scheduled.append((message_id, delay))
        return True

    monkeypatch.setattr(image_sender, "schedule_revoke", fake_schedule_revoke)

    context = MagicMock()
    context.send_message = AsyncMock(return_value={"message_id": "normal"})
    set_plugin_context(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "raw"})

    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "auto_revoke_scope": scope,
        "auto_revoke_targets": ["setu"],
        "auto_revoke_delay": revoke_delay,
        "r18_docx_mode": False,
    }
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=(),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=is_r18,
        tags=(),
    )

    results = [
        item async for item in ImageSender(config).send_images(payload, mock_event)
    ]

    assert results == [{"send_success": True, "image_count": 1}]
    assert len(scheduled) == expected_scheduled
    if expected_scheduled:
        assert scheduled == [("raw", revoke_delay)]
        mock_event.bot.send_group_msg.assert_awaited_once()
    else:
        mock_event.bot.send_group_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_send_strategy_returns_raw_message_id_for_auto_revoke(
    mock_event,
) -> None:
    """启用撤回时直发图片走 OneBot raw action 并回传 message_id。"""
    context = MagicMock()
    context.send_message = AsyncMock()
    strategy = DirectSendStrategy(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "raw"})

    result = await strategy.send_with_status(
        mock_event,
        [Comp.Image.fromBytes(b"image-data")],
        auto_revoke=True,
    )

    assert result.accepted is True
    assert result.message_ids == ("raw",)
    context.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_forward_send_strategy_returns_raw_message_id_for_auto_revoke(
    mock_event,
) -> None:
    """启用撤回时合并转发走 OneBot raw action 并回传 message_id。"""
    context = MagicMock()
    context.send_message = AsyncMock()
    strategy = ForwardSendStrategy(context)

    mock_event.platform.name = "napcat"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.get_self_id.return_value = "10000"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_forward_msg = AsyncMock(
        return_value={"data": {"message_id": "forward"}}
    )

    result = await strategy.send_with_status(
        mock_event,
        [Comp.Image.fromBytes(b"image-a"), Comp.Image.fromBytes(b"image-b")],
        auto_revoke=True,
    )

    assert result.accepted is True
    assert result.message_ids == ("forward",)
    mock_event.bot.send_group_forward_msg.assert_awaited_once()
    context.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_recoverable_revoke_scheduler_calls_delete_msg(
    tmp_path: Path, mock_event
) -> None:
    """可恢复调度器到期后通过 OneBot delete_msg 撤回消息。"""

    mock_event.platform.name = "napcat"
    mock_event.get_platform_id.return_value = "onebot-main"
    mock_event.bot = MagicMock()
    mock_event.bot.call_action = AsyncMock(return_value={"status": "ok"})
    platform = MagicMock()
    platform.get_client.return_value = mock_event.bot
    context = MagicMock()
    context.get_platform_inst.return_value = platform
    scheduler = RecoverableRevokeScheduler(tmp_path, context)

    await scheduler.initialize()
    assert await scheduler.schedule_revoke(mock_event, "123", 0) is True
    await asyncio.gather(*tuple(scheduler._tasks.values()))

    mock_event.bot.call_action.assert_awaited_once_with("delete_msg", message_id="123")
    assert scheduler.storage_path.read_text(encoding="utf-8")
    await scheduler.stop()


@pytest.mark.asyncio
async def test_send_images_ignores_legacy_send_failed_toggle(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    context.send_message = AsyncMock(side_effect=RuntimeError("send failed"))
    set_plugin_context(context)

    mock_event.platform.name = "unknown-platform"
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        "fetching": {"enabled": False, "text": "正在获取图片，请稍候..."},
        "found": {"enabled": False, "text": "找到 {count} 张符合要求的图片~"},
        "send_failed": {"enabled": False, "text": "图片发送失败，请稍后再试。"},
    }
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=("https://example.com/image.jpg",),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    sender = ImageSender(config)
    sender.set_html_renderer(
        MagicMock(
            render_single_image=AsyncMock(side_effect=RuntimeError("t2i unavailable"))
        )
    )
    results = [item async for item in sender.send_images(payload, mock_event)]

    assert len(results) == 1
    mock_event.plain_result.assert_called_with("图片发送失败，请稍后再试。")


@pytest.mark.asyncio
async def test_r18_docx_missing_service_never_sends_images(
    mock_event, sample_config_dict
):
    config = SetuPluginConfig(**sample_config_dict)
    sender = ImageSender(config)
    sender._build_options = AsyncMock(
        return_value=SendOptions(
            send_mode="image",
            use_html_card=False,
            auto_revoke=False,
            revoke_delay=30,
            r18_docx_mode=True,
        )
    )
    context = MagicMock()
    context.send_message = AsyncMock(return_value={"message_id": "123"})
    set_plugin_context(context)
    payload = ImagePayload(
        urls=(), raw_bytes=(b"image",), file_paths=(), r18=True, tags=()
    )
    results = [item async for item in sender.send_images(payload, mock_event)]
    context.send_message.assert_not_called()
    assert not any(
        isinstance(item, dict) and item.get("send_success") for item in results
    )
    mock_event.plain_result.assert_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["success", "failed", "pending", "generation_failed", "read_failed"]
)
async def test_r18_docx_delivery_terminal_states(
    tmp_path, mock_event, sample_config_dict, outcome
):
    from astrbot_plugin_setu.src.infrastructure.sending.docx_service import (
        R18DocxService,
    )
    from astrbot_plugin_setu.src.infrastructure.sending.dto import SendAttemptResult

    from tests.infrastructure.test_docx_service import image_bytes

    service = R18DocxService(tmp_path)
    if outcome == "generation_failed":
        service.create_docx_with_images = MagicMock(side_effect=OSError("disk full"))
    sender = ImageSender(
        SetuPluginConfig(**sample_config_dict),
        docx_service=service,
    )
    sender._build_options = AsyncMock(
        return_value=SendOptions(
            send_mode="image",
            use_html_card=False,
            auto_revoke=True,
            revoke_delay=30,
            r18_docx_mode=True,
        )
    )
    sender._schedule_revoke_for_result = AsyncMock(return_value=1)
    sender._send_post_delivery_messages = AsyncMock()
    set_plugin_context(MagicMock())
    results_by_outcome = {
        "success": SendAttemptResult.success("123"),
        "failed": SendAttemptResult.failed("rejected"),
        "pending": SendAttemptResult.pending_delivery("timeout"),
    }
    send = AsyncMock(return_value=results_by_outcome.get(outcome))
    payload = ImagePayload(
        urls=(),
        raw_bytes=(image_bytes("PNG"),),
        file_paths=(),
        items=(tmp_path / "missing.png",) if outcome == "read_failed" else (),
        r18=True,
        tags=(),
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(DirectSendStrategy, "send_with_status", send)
        results = [item async for item in sender.send_images(payload, mock_event)]
    if outcome in {"generation_failed", "read_failed"}:
        send.assert_not_called()
    else:
        send.assert_awaited_once()
        chain = send.call_args.args[1]
        assert len(chain) == 1 and isinstance(chain[0], Comp.File)
        from docx import Document

        assert len(Document(chain[0].file).inline_shapes) == 1
    statuses = [item for item in results if isinstance(item, dict)]
    if outcome in {"success", "pending"}:
        assert statuses == [
            {
                "send_success": True,
                "image_count": 1,
                **({"send_pending": True} if outcome == "pending" else {}),
            }
        ]
        assert sender._schedule_revoke_for_result.call_args.args[1].message_ids == (
            ("123",) if outcome == "success" else ()
        )
    else:
        assert statuses == []
        mock_event.plain_result.assert_called()
        sender._schedule_revoke_for_result.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("r18,docx_enabled", [(False, True), (True, False)])
async def test_non_docx_requests_keep_image_delivery(
    mock_event, sample_config_dict, r18, docx_enabled
):
    context = MagicMock()
    context.send_message = AsyncMock(return_value={"message_id": "123"})
    set_plugin_context(context)
    sender = ImageSender(SetuPluginConfig(**sample_config_dict))
    sender._build_options = AsyncMock(
        return_value=SendOptions(
            send_mode="image",
            use_html_card=False,
            auto_revoke=False,
            revoke_delay=30,
            r18_docx_mode=docx_enabled,
        )
    )
    payload = ImagePayload(
        urls=(), raw_bytes=(b"image",), file_paths=(), r18=r18, tags=()
    )
    results = [item async for item in sender.send_images(payload, mock_event)]
    assert results == [{"send_success": True, "image_count": 1}]
    assert isinstance(
        context.send_message.call_args_list[0].args[1].result_chain[0], Comp.Image
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("targets,expected", [(["fortune"], True), (["setu"], False)])
async def test_fortune_transport_uses_its_own_revoke_policy(
    mock_event, targets, expected
):
    config = SetuPluginConfig(
        delivery={
            "send_mode": "forward",
            "r18_docx_mode": True,
            "auto_revoke_targets": targets,
            "auto_revoke_scope": "all",
            "compress_enabled": True,
            "compress_max_mb": 9,
            "platform_transports": [
                {
                    "__template_key": "napcat",
                    "stream_mode": "always",
                    "local_file_mode": "fallback",
                    "local_file_allowed_roots": ["/shared"],
                }
            ],
        }
    )
    sender = ImageSender(config, content_type="fortune")
    options = await sender._build_options(mock_event, is_r18=True)
    assert options.send_mode == "image"
    assert options.r18_docx_mode is False
    assert options.auto_revoke is expected
    assert options.compress_enabled and options.compress_max_mb == 9
    assert options.napcat_stream_mode == "always"
    assert options.napcat_local_file_allowed_roots == ("/shared",)
    sender._send_plain_text = AsyncMock()
    await sender._send_post_delivery_messages(mock_event, 1, options, False, 1)
    sender._send_plain_text.assert_not_awaited()
