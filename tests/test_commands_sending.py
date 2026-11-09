import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image


def event(sid="p:GroupMessage:g", admin=False, role="member", user="u"):
    extras = {}
    return SimpleNamespace(
        get_extra=extras.get,
        set_extra=extras.__setitem__,
        unified_msg_origin=sid,
        get_platform_id=lambda: "p",
        get_sender_id=lambda: user,
        get_sender_name=lambda: "昵称",
        get_self_id=lambda: "bot",
        get_group_id=lambda: sid.split(":")[-1] if ":GroupMessage:" in sid else "",
        is_admin=lambda: admin,
        message_obj=SimpleNamespace(sender=SimpleNamespace(role=role)),
        get_messages=lambda: [],
        plain_result=lambda text: text,
        stop_event=lambda: None,
    )


@pytest.mark.asyncio
async def test_native_commands_preference_at_refresh_and_permissions(tmp_path, load):
    main = load("main")
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.star_handler import star_handlers_registry

    handlers = {
        h.handler_name: h
        for h in star_handlers_registry.get_handlers_by_module_name(main.__name__)
    }
    tags = next(
        f
        for f in handlers["preference_tags"].event_filters
        if isinstance(f, CommandFilter)
    )
    assert tags.validate_and_convert_params(["猫耳", "白发"], tags.handler_params) == {
        "tags": "猫耳 白发"
    }
    theme = next(
        f
        for f in handlers["preference_theme"].event_filters
        if isinstance(f, CommandFilter)
    )
    assert theme.validate_and_convert_params(
        ["Blue", "Archive"], theme.handler_params
    ) == {"theme": "Blue Archive"}
    load("src.shared.cache").init_cache(tmp_path / "cache")
    dbmod = load("src.infrastructure.persistence.database")
    db = await dbmod.init_database(tmp_path)
    cfgmod = load("src.infrastructure.astrbot.config")
    cfgmod.init_config({"fortune": {"allow_user_refresh": True}})
    persistence = load("src.infrastructure.persistence")
    await persistence.init_access_control_repo(cfgmod.get_config().safety)
    await persistence.init_fortune_repo(tmp_path)
    handler = load(
        "src.infrastructure.astrbot.commands.fortune"
    ).FortuneCommandHandler()
    try:
        group_event = event()
        private_event = event("p:FriendMessage:u")
        await handler.preference(group_event, "theme", "我的世界")
        assert (await db.preference("u"))["theme"] == "minecraft"
        assert "minecraft" in await handler.preference(private_event)
        assert "minecraft" in await handler.preference(
            event("p:GroupMessage:another-group")
        )
        await handler.preference(private_event, "theme", " blue ARCHIVE ")
        assert (await db.preference("u"))["theme"] == "arona"
        await handler.preference(group_event, "theme", "随机")
        assert (await db.preference("u"))["theme"] == "random"
        with pytest.raises(ValueError, match="未知运势主题"):
            await handler.preference(group_event, "theme", "不存在的主题")
        assert (await db.preference("u"))["theme"] == "random"
        await handler.preference(group_event, "tags", '["猫耳","白发"]')
        assert json.loads((await db.preference("u"))["tags"]) == ["猫耳", "白发"]
        await handler.preference(private_event, "tags", None)
        assert (await db.preference("u"))["tags"] is None
        await handler.refresh(group_event)
        with pytest.raises(PermissionError):
            await handler.refresh(group_event, "target")
        import astrbot.api.message_components as Comp

        admin_event = event(role="admin")
        admin_event.get_messages = lambda: [Comp.At(qq="target")]
        results = [r async for r in handler.refresh_fortune_command(admin_event)]
        assert "已刷新该用户" in results[0]
        users = {
            r[0]
            for r in await (
                await db.connection.execute("SELECT user_id FROM daily_fortune")
            ).fetchall()
        }
        assert users == {"u", "target"}
        with pytest.raises(PermissionError):
            await handler.refresh_all(admin_event)
        await handler.refresh_all(event(admin=True))
        assert (
            await (
                await db.connection.execute("SELECT count(*) FROM daily_fortune")
            ).fetchone()
        )[0] == 0
    finally:
        await dbmod.close_database()
        cfgmod.clear_config()
        persistence.clear_repo()
        persistence.clear_fortune_repo()


@pytest.mark.asyncio
async def test_docx_and_images_cleanup_after_send(tmp_path, load):
    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    cfg = load("src.shared.config.models").SetuPluginConfig()
    context = SimpleNamespace(
        get_config=lambda **kw: {"platform_settings": {"reply_with_mention": False}},
        send_message=AsyncMock(return_value={"message_id": "sent"}),
    )
    load("src.infrastructure.astrbot.config").set_plugin_context(context)
    data = BytesIO()
    Image.new("RGB", (200, 300), "blue").save(data, format="PNG")
    service = load("src.infrastructure.sending.docx_service").R18DocxService(tmp_path)
    ev = event()
    ev.platform = SimpleNamespace(name="test")
    ev.chain_result = lambda chain: chain
    Payload = load("src.application.setu.dto").ImagePayload
    sender = load("src.infrastructure.sending.image_sender").ImageSender(
        cfg, docx_service=service
    )
    source = cache.root / "setu" / "source.png"
    cache.pin(source)
    cache.write(source, data.getvalue())
    payload = Payload(urls=(), raw_bytes=(), file_paths=(source,), r18=False, tags=())
    results = [r async for r in sender.send_images(payload, ev)]
    assert results[-1]["send_success"] and not source.exists()
    results = [
        r
        async for r in sender.send_images(
            Payload(urls=(), raw_bytes=(data.getvalue(),), r18=True, tags=()), ev
        )
    ]
    assert results[-1]["send_success"]
    assert context.send_message.await_count == 2
    assert not list((cache.root / "setu").glob("*.docx")) and not cache.active


@pytest.mark.asyncio
async def test_fortune_cache_theme_and_tags_keep_daily_stars(tmp_path, load):
    from unittest.mock import patch

    import astrbot.core
    import httpx

    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    dbmod = load("src.infrastructure.persistence.database")
    db = await dbmod.init_database(tmp_path)
    cfgmod = load("src.infrastructure.astrbot.config")
    cfgmod.init_config(
        {
            "cache": {"fortune": True},
            "fortune": {"allow_user_refresh": True, "card_theme": "endfield"},
        }
    )
    cfgmod.set_plugin_context(
        SimpleNamespace(
            get_config=lambda **kw: {"platform_settings": {"reply_with_mention": True}},
            send_message=AsyncMock(return_value={"message_id": "sent"}),
        )
    )
    persistence = load("src.infrastructure.persistence")
    await persistence.init_access_control_repo(cfgmod.get_config().safety)
    await persistence.init_fortune_repo(tmp_path)
    handler = load(
        "src.infrastructure.astrbot.commands.fortune"
    ).FortuneCommandHandler()
    data = BytesIO()
    Image.new("RGB", (20, 30), "blue").save(data, format="PNG")
    png = data.getvalue()
    Metadata = load("src.application.setu.dto").ImageMetadata
    Payload = load("src.application.setu.dto").ImagePayload
    payload = Payload(
        urls=("https://img.test/bg.png",),
        raw_bytes=(png,),
        r18=False,
        tags=(),
        items=(png,),
        images=(Metadata("https://img.test/bg.png", "https://source.test"),),
    )
    providers = load("src.infrastructure.providers")

    async def fetch(request, *, on_images):
        await on_images(payload.images)
        return payload

    provider = SimpleNamespace(fetch_and_download=AsyncMock(side_effect=fetch))
    t2i = SimpleNamespace(render_custom_template=AsyncMock(return_value=png))
    real_client = httpx.AsyncClient

    def client(**kw):
        return real_client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, content=png)),
            **kw,
        )

    ev = event()
    ev.platform = SimpleNamespace(name="test")
    ev.chain_result = lambda chain: chain
    try:
        with (
            patch.object(providers, "_provider", provider),
            patch.object(astrbot.core, "html_renderer", t2i),
            patch.object(httpx, "AsyncClient", client),
        ):
            assert await handler._get(ev) == "ok"
            import astrbot.api.message_components as Comp

            sent = cfgmod.get_plugin_context().send_message.await_args.args[1]
            assert isinstance(sent[0], Comp.At) and str(sent[0].qq) == "u"
            first = await (
                await db.connection.execute("SELECT * FROM daily_fortune")
            ).fetchone()
            files = list((cache.root / "fortune").iterdir())
            assert len(files) == 1
            await handler._get(ev)
            assert t2i.render_custom_template.await_count == 1
            stopped = []
            ev.stop_event = lambda: stopped.append(True)
            assert [result async for result in handler.fortune_command(ev)] == []
            assert stopped == [True]
            await handler.preference(ev, "theme", "minimal")
            assert not files[0].exists()
            await handler._get(ev)
            assert t2i.render_custom_template.await_count == 2
            await handler.preference(ev, "tags", '["猫耳","白发"]')
            await handler._get(ev)
            assert provider.fetch_and_download.await_args.args[0].tags == (
                "猫耳",
                "白发",
            )
            current = await (
                await db.connection.execute("SELECT * FROM daily_fortune")
            ).fetchone()
            assert first["stars"] == current["stars"] and first["id"] == current["id"]
            assert first["setu_history_id"] != current["setu_history_id"]
            await handler.refresh_all(event(admin=True))
            assert not list((cache.root / "fortune").iterdir()) and not cache.active
    finally:
        await dbmod.close_database()
        cfgmod.clear_config()
        persistence.clear_repo()
        persistence.clear_fortune_repo()


@pytest.mark.asyncio
async def test_pending_docx_and_retained_forward_napcat_routes(tmp_path, load):
    import astrbot.api.message_components as Comp

    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    cfg = load("src.shared.config.models").SetuPluginConfig()
    context = SimpleNamespace(
        get_config=lambda **kw: {"platform_settings": {"reply_with_mention": False}},
        send_message=AsyncMock(return_value=None),
    )
    load("src.infrastructure.astrbot.config").set_plugin_context(context)
    ev = event()
    ev.platform = SimpleNamespace(name="napcat")
    ev.chain_result = lambda chain: chain
    data = BytesIO()
    Image.new("RGB", (20, 30), "blue").save(data, format="PNG")
    service = load("src.infrastructure.sending.docx_service").R18DocxService(tmp_path)
    Payload = load("src.application.setu.dto").ImagePayload
    sender = load("src.infrastructure.sending.image_sender").ImageSender(
        cfg, docx_service=service
    )
    results = [
        r
        async for r in sender.send_images(
            Payload(urls=(), raw_bytes=(data.getvalue(),), r18=True, tags=()), ev
        )
    ]
    assert results[-1]["send_pending"]
    held = next(iter(cache.active))
    assert held.exists()
    from docx import Document

    assert len(Document(held).inline_shapes) == 1
    uploaded = []

    async def action(name, **params):
        assert held.exists() and held in cache.active
        uploaded.append((name, params))
        return {"status": "ok", "data": {"file_path": "/napcat/uploaded"}}

    ev.bot = SimpleNamespace(call_action=action)
    assert (
        await load("src.infrastructure.sending.napcat_stream").upload_file_stream(
            ev, held, chunk_size=4096
        )
        == "/napcat/uploaded"
    )
    assert uploaded[-1][1]["is_complete"]
    assert all(item[1]["expected_sha256"] for item in uploaded[:-1])
    cache.release(held)
    assert not held.exists()
    context.send_message.return_value = {"message_id": "forward"}
    forward = load("src.infrastructure.sending.send_strategies").ForwardSendStrategy(
        context
    )
    result = await forward.send_with_status(ev, [Comp.Image.fromBytes(data.getvalue())])
    assert result.accepted and result.message_ids == ("forward",)
    chain = context.send_message.await_args.args[1]
    assert isinstance(chain[0], Comp.Nodes)
    assert not cache.active


@pytest.mark.asyncio
async def test_reply_mentions_session_overrides_raw_receipts_and_special_messages(load):
    """真实消息组件贯穿发送边界，保证 @ 设置和媒体回执各自保留。"""
    import astrbot.api.message_components as Comp
    from astrbot.core.message.message_event_result import MessageEventResult

    strategies = load("src.infrastructure.sending.send_strategies")
    settings = {"p:GroupMessage:123": True, "p:GroupMessage:456": False}
    context = SimpleNamespace(
        get_config=lambda *, umo: {
            "platform_settings": {"reply_with_mention": settings.get(umo, True)}
        },
        send_message=AsyncMock(return_value={"message_id": "media"}),
    )

    def reply_event(sid="p:GroupMessage:123"):
        ev = event(sid, user="321")
        ev.platform = SimpleNamespace(name="aiocqhttp")
        ev.chain_result = lambda chain: MessageEventResult(chain=chain)
        ev.bot = SimpleNamespace(
            call_action=AsyncMock(return_value={"message_id": "raw"})
        )
        return ev

    direct = strategies.DirectSendStrategy(context)
    image = Comp.Image.fromBytes(b"test image")
    for sid, expected in (
        ("p:GroupMessage:123", True),
        ("p:GroupMessage:456", False),
        ("p:FriendMessage:321", False),
    ):
        ev = reply_event(sid)
        original = [image]
        result = await direct.send_with_status(ev, original)
        assert result.message_ids == ("media",)
        chain = context.send_message.await_args.args[1].chain
        assert any(isinstance(c, Comp.At) for c in chain) == expected
        assert original == [image]

    ev = reply_event()
    await direct.send_with_status(ev, [Comp.At(qq="321"), image], auto_revoke=True)
    params = ev.bot.call_action.await_args.kwargs
    assert [c["type"] for c in params["message"]] == ["at", "image"]
    assert params["group_id"] == 123
    assert params["message"][0]["data"]["qq"] == "321"

    # 普通发送失败后更换传输仍带 @，确认超时后则复用已有提醒。
    ev = reply_event()
    context.send_message.side_effect = RuntimeError("rejected")
    assert not (await direct.send_with_status(ev, [image])).accepted
    context.send_message.side_effect = None
    result = await direct.send_with_status(ev, [image], auto_revoke=True)
    assert result.message_ids == ("raw",)
    assert ev.bot.call_action.await_args.kwargs["message"][0]["type"] == "at"
    ev = reply_event()
    context.send_message.side_effect = TimeoutError("ack lost")
    assert (await direct.send_with_status(ev, [image])).pending
    context.send_message.side_effect = None
    await direct.send_with_status(ev, [image])
    assert not any(
        isinstance(c, Comp.At) for c in context.send_message.await_args.args[1].chain
    )

    # 提醒失败时保留错误；确认超时时继续发送媒体，避免重复提醒。
    ev = reply_event()
    file_chain = [Comp.File(file="/tmp/book.pdf", name="book.pdf")]
    context.send_message.side_effect = RuntimeError("notice rejected")
    result = await direct.send_with_status(ev, file_chain, auto_revoke=True)
    assert not result.accepted and "notice rejected" in result.reason
    ev.bot.call_action.assert_not_awaited()
    context.send_message.side_effect = TimeoutError("notice ack lost")
    result = await direct.send_with_status(ev, file_chain, auto_revoke=True)
    assert result.message_ids == ("raw",)
    assert len(ev.bot.call_action.await_args.kwargs["message"]) == 1
    context.send_message.side_effect = None

    for raw in (False, True):
        for kind in ("file", "forward"):
            ev = reply_event()
            context.send_message.reset_mock()
            if kind == "file":

                async def send():
                    return await direct.send_with_status(
                        ev, [Comp.File(file="/tmp/book.pdf", name="book.pdf")], raw
                    )
            else:
                forward = strategies.ForwardSendStrategy(context)

                async def send():
                    return await forward.send_with_status(ev, [image], raw)

            result = await send()
            assert result.message_ids == (("raw",) if raw else ("media",))
            notice = context.send_message.await_args_list[0]
            assert notice.args[0] == ev.unified_msg_origin
            assert len(notice.args[1].chain) == 1
            ats = [c for c in notice.args[1].chain if isinstance(c, Comp.At)]
            assert len(ats) == 1 and str(ats[0].qq) == "321"
            if not raw:
                media_chain = context.send_message.await_args.args[1].chain
                assert len(media_chain) == 1
                assert isinstance(
                    media_chain[0], Comp.File if kind == "file" else Comp.Nodes
                )
            count = context.send_message.await_count
            await send()
            assert context.send_message.await_count == count + (0 if raw else 1)
