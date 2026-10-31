import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image


def event(sid="p:GroupMessage:g", admin=False, role="member", user="u"):
    return SimpleNamespace(
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
    from astrbot.core.star.filter.command_group import CommandGroupFilter
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
    primary = next(
        f
        for f in handlers["setu_command"].event_filters
        if isinstance(f, CommandFilter)
    )
    assert primary.command_name == "色图" and primary.alias == {"setu"}
    group = next(
        f
        for f in handlers["preference"].event_filters
        if isinstance(f, CommandGroupFilter)
    )
    assert {f.command_name for f in group.sub_command_filters} == {
        "查看",
        "主题",
        "标签",
        "重置主题",
        "重置标签",
    }
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
        await handler.preference(group_event, "theme", "minecraft")
        assert "minecraft" in await handler.preference(private_event)
        assert "minecraft" in await handler.preference(
            event("p:GroupMessage:another-group")
        )
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
        send_message=AsyncMock(return_value={"message_id": "sent"})
    )
    load("src.infrastructure.astrbot.config").set_plugin_context(context)
    data = BytesIO()
    Image.new("RGB", (200, 300), "blue").save(data, format="PNG")
    service = load("src.infrastructure.sending.docx_service").R18DocxService(tmp_path)
    path = service.create_docx_with_images([data.getvalue()], [])
    from docx import Document

    assert len(Document(path).inline_shapes) == 1
    cache.release(path)
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
        {"cache": {"fortune": True}, "fortune": {"allow_user_refresh": True}}
    )
    cfgmod.set_plugin_context(
        SimpleNamespace(send_message=AsyncMock(return_value={"message_id": "sent"}))
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
            first = await (
                await db.connection.execute("SELECT * FROM daily_fortune")
            ).fetchone()
            files = list((cache.root / "fortune").iterdir())
            assert len(files) == 1
            await handler._get(ev)
            assert t2i.render_custom_template.await_count == 1
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
    context = SimpleNamespace(send_message=AsyncMock(return_value=None))
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
