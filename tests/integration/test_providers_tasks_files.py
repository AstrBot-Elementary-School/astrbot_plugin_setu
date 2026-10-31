import asyncio
import json
import zipfile
from io import BytesIO
from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from PIL import Image, PdfParser


@pytest.mark.asyncio
async def test_provider_download_preserves_returned_urls_and_metadata(tmp_path, load):
    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    await load("src.shared.send_cache").init_send_cache(tmp_path, enabled=False)
    dbmod = load("src.infrastructure.persistence.database")
    db = await dbmod.init_database(tmp_path)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        if request.url.host == "api.lolicon.app":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "pid": 42,
                            "tags": ["上游"],
                            "urls": {"original": "https://i.pximg.net/a.png"},
                        }
                    ]
                },
            )
        if request.url.host == "sex.nyan.run":
            return httpx.Response(
                200, json={"data": [{"url": "https://returned.proxy/b.png"}]}
            )
        if request.url.host == "custom.test":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "url": "https://cdn.test/c.png",
                            "source_url": "https://art.test/c",
                            "tags": ["白发"],
                        }
                    ]
                },
            )
        return httpx.Response(200, content=b"image")

    real_client = httpx.AsyncClient

    def factory(**kw):
        return real_client(transport=httpx.MockTransport(respond), **kw)

    providers = load("src.infrastructure.providers")
    multi = providers.MultiApiProvider(
        [
            providers.LoliconProvider(proxy="configured.proxy"),
            providers.SexNyanRunProvider(),
        ]
    )
    Request = load("src.domain.setu").SetuRequest
    try:
        with patch.object(httpx, "AsyncClient", factory):
            for _ in range(2):
                payload = await multi.fetch_and_download(
                    Request.from_user_input(
                        count=1, tags=["输入"], r18=False, max_replenish_rounds=1
                    ),
                    on_images=lambda images: db.add_history(
                        "p:GroupMessage:g", "u", images, ["输入"]
                    ),
                )
                assert payload.raw_bytes == (b"image",)
            custom = providers.CustomApiProvider(
                {"url": "https://custom.test/api?num={num}"},
                {"type": "json", "json_path": "$.data[*].url"},
            )
            with patch.object(
                load("src.infrastructure.providers.custom"),
                "_validate_url",
                AsyncMock(side_effect=lambda url: (url, None)),
            ):
                payload = await custom.fetch_and_download(
                    Request.from_user_input(
                        count=1, tags=[], r18=False, max_replenish_rounds=1
                    ),
                    on_images=lambda images: db.add_history(
                        "p:GroupMessage:g", "u", images, []
                    ),
                )
        rows = await (
            await db.connection.execute("SELECT * FROM setu_history ORDER BY id")
        ).fetchall()
        assert rows[0]["image_url"] == "https://i.pximg.net/a.png"
        assert rows[0]["source_url"] == "https://www.pixiv.net/artworks/42"
        assert json.loads(rows[0]["tags"]) == ["上游"]
        assert rows[1]["image_url"] == "https://returned.proxy/b.png"
        assert rows[1]["source_url"] == providers.SexNyanRunProvider.API_URL
        assert json.loads(rows[1]["tags"]) == ["输入"]
        assert rows[2]["source_url"] == "https://art.test/c"
        assert json.loads(rows[2]["tags"]) == ["白发"]
        assert "https://configured.proxy/a.png" in calls
        assert not cache.active and not any(p.is_file() for p in cache.root.rglob("*"))
    finally:
        await dbmod.close_database()


@pytest.mark.asyncio
async def test_migrated_message_and_group_file_tasks_restart_and_execute(
    tmp_path, load
):
    load("src.shared.cache").init_cache(tmp_path / "cache")
    (tmp_path / "revoke_tasks.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "m",
                        "target": "message",
                        "session_id": "p:GroupMessage:g",
                        "due_at": time() + 3600,
                        "message_id": "123",
                    }
                ]
            }
        )
    )
    (tmp_path / "doujinshi_file_cleanup_tasks.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "f",
                        "platform_id": "p",
                        "group_id": "g",
                        "file_id": "file",
                        "file_name": "book.pdf",
                        "due_at": time() + 3600,
                    }
                ]
            }
        )
    )
    dbmod = load("src.infrastructure.persistence.database")
    db = await dbmod.init_database(tmp_path)
    action = AsyncMock(return_value={"status": "ok", "retcode": 0})
    context = SimpleNamespace(
        get_platform_inst=lambda name: SimpleNamespace(
            get_client=lambda: SimpleNamespace(call_action=action)
        )
    )
    Scheduler = load(
        "src.infrastructure.sending.revoke_scheduler"
    ).RecoverableRevokeScheduler
    scheduler = Scheduler(tmp_path, context)
    try:
        await scheduler.initialize()
        assert len(scheduler._tasks) == 2
        await scheduler.stop()
        assert (
            await (
                await db.connection.execute("SELECT count(*) FROM setu_schedule_task")
            ).fetchone()
        )[0] == 2
        async with db.transaction() as connection:
            await connection.execute(
                "UPDATE setu_schedule_task SET due_at=?", (time() - 1,)
            )
        await scheduler.initialize()
        await asyncio.gather(*tuple(scheduler._tasks.values()))
        assert (
            await (
                await db.connection.execute("SELECT count(*) FROM setu_schedule_task")
            ).fetchone()
        )[0] == 0
        assert {call.args[0] for call in action.await_args_list} == {
            "delete_msg",
            "delete_group_file",
        }
    finally:
        await scheduler.stop()
        await dbmod.close_database()


@pytest.mark.asyncio
async def test_doujinshi_pdf_zip_and_failed_generation_cleanup(tmp_path, load):
    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    data = BytesIO()
    Image.new("RGB", (40, 60), "red").save(data, format="PNG")

    def respond(request):
        if request.url.path == "/api":
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "title": "book",
                    "pages": [
                        {"url": "https://cdn.test/1.png"},
                        {"url": "https://cdn.test/2.png"},
                    ],
                },
            )
        return httpx.Response(
            200, content=data.getvalue(), headers={"content-type": "image/png"}
        )

    service = load("src.infrastructure.doujinshi").DoujinshiService(tmp_path)
    service.API_URL = "https://test/api"
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for mode in ("pdf", "archive"):
            generated = await service.fetch_random_file(
                ["tag"], mode=mode, client=client
            )
            assert generated.path in cache.active
            if mode == "archive":
                with zipfile.ZipFile(generated.path) as archive:
                    assert archive.namelist() == ["page-0001.png", "page-0002.png"]
            else:
                assert generated.path.read_bytes().startswith(b"%PDF")
                with PdfParser.PdfParser(filename=str(generated.path)) as pdf:
                    assert len(pdf.pages) == 2
            cache.release(generated.path)
        cache.limit = 1
        with pytest.raises(OSError, match="空间不足"):
            await service.fetch_random_file(mode="archive", client=client)
    assert not cache.active and not list((cache.root / "doujinshi").iterdir())


@pytest.mark.asyncio
async def test_download_failure_keeps_history_and_releases_files(tmp_path, load):
    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    cache.limit = 128
    await load("src.shared.send_cache").init_send_cache(tmp_path, enabled=True)
    dbmod = load("src.infrastructure.persistence.database")
    db = await dbmod.init_database(tmp_path)
    Base = load("src.infrastructure.providers.base").DownloadingSetuImageProvider
    Metadata = load("src.application.setu.dto").ImageMetadata

    class Provider(Base):
        async def fetch_images(self, **kw):
            return [
                Metadata("https://img.test/small.png", "https://api.test"),
                Metadata("https://img.test/large.png", "https://api.test"),
            ]

    real_client = httpx.AsyncClient

    def respond(request):
        return httpx.Response(
            200, content=b"x" * (8 if request.url.path == "/small.png" else 1024)
        )

    def factory(**kw):
        return real_client(transport=httpx.MockTransport(respond), **kw)

    Request = load("src.domain.setu").SetuRequest
    try:
        with (
            patch.object(httpx, "AsyncClient", factory),
            pytest.raises(OSError, match="空间不足"),
        ):
            await Provider().fetch_and_download(
                Request.from_user_input(
                    count=2, tags=["输入"], r18=False, max_replenish_rounds=1
                ),
                on_images=lambda images: db.add_history(
                    "p:GroupMessage:g", "u", images, ["输入"]
                ),
            )
        assert (
            await (
                await db.connection.execute("SELECT count(*) FROM setu_history")
            ).fetchone()
        )[0] == 2
        assert not cache.active
        assert not list(cache.root.rglob("*.part"))
        assert (
            sum(f.stat().st_size for f in cache.root.rglob("*") if f.is_file()) <= 128
        )
    finally:
        await dbmod.close_database()
