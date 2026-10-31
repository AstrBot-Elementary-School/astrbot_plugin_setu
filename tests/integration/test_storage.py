import asyncio
import importlib
import json
import sqlite3
from datetime import date, timedelta
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import pytest


@pytest.mark.asyncio
async def test_daily_identity_history_retention_and_preference(tmp_path, load):
    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    module = load("src.infrastructure.persistence.database")
    db = await module.init_database(tmp_path)
    try:
        repo = load(
            "src.infrastructure.persistence.sqlite_fortune_repository"
        ).SQLiteFortuneRepo()
        Request = load("src.domain.fortune").FortuneGenerationRequest
        Image = load("src.application.setu.dto").ImageMetadata
        today = date.today().isoformat()
        request = Request("u", "name", today, "p:GroupMessage:g")
        records = await asyncio.gather(
            *(repo.get_or_create(request, i % 8) for i in range(20))
        )
        assert len({r.id for r in records}) == 1
        other = await repo.get_or_create(
            Request("u", "name", today, "p:GroupMessage:other"), 7
        )
        assert other.id != records[0].id
        ids = await db.add_history(
            request.session_id,
            "u",
            [
                Image("https://proxy/1", "https://source/1", ("upstream",)),
                Image("https://proxy/2", "https://api"),
                Image("https://proxy/3", "https://api"),
            ],
            ["input"],
        )
        await repo.attach_image(records[0].id, ids[0])
        rows = await (
            await db.connection.execute("SELECT * FROM setu_history ORDER BY id")
        ).fetchall()
        assert json.loads(rows[0]["tags"]) == ["upstream"]
        assert json.loads(rows[1]["tags"]) == ["input"]
        assert rows[0]["image_url"] == "https://proxy/1"
        empty = await db.add_history(
            request.session_id, "u", [Image("https://proxy/empty", "https://api")], []
        )
        assert (
            await (
                await db.connection.execute(
                    "SELECT tags FROM setu_history WHERE id=?", empty
                )
            ).fetchone()
        )[0] is None
        await db.set_preference("u", "theme", "arona")
        await db.set_preference("u", "tags", '["猫耳", "白发"]')
        assert (await db.preference("u"))["theme"] == "arona"
        old = (date.today() - timedelta(days=30)).isoformat()
        boundary = (date.today() - timedelta(days=29)).isoformat()
        await db.connection.execute("UPDATE setu_history SET date=?", (old,))
        await db.connection.commit()
        expired = await repo.get_or_create(
            Request("old", "old", old, request.session_id), 2
        )
        kept = await repo.get_or_create(
            Request("boundary", "b", boundary, request.session_id), 2
        )
        cached = cache.root / "fortune" / f"{expired.id}-test.png"
        cache.write(cached, b"card")
        expired_image = (
            cache.root / "setu" / (uuid5(NAMESPACE_URL, "https://proxy/2").hex + ".png")
        )
        retained_image = (
            cache.root / "setu" / (uuid5(NAMESPACE_URL, "https://proxy/1").hex + ".png")
        )
        cache.write(expired_image, b"expired")
        cache.write(retained_image, b"retained")
        db.cleanup_date = None
        await db.cleanup()
        assert not cached.exists()
        assert not expired_image.exists() and retained_image.exists()
        assert [
            r[0]
            for r in await (
                await db.connection.execute("SELECT id FROM setu_history")
            ).fetchall()
        ] == ids[:1]
        assert await (
            await db.connection.execute(
                "SELECT id FROM daily_fortune WHERE id=?", (kept.id,)
            )
        ).fetchone()
        assert set(p.name for p in tmp_path.iterdir()) == {"db.sqlite", "cache"}
    finally:
        await module.close_database()
        load("src.shared.cache").clear_cache()


@pytest.mark.asyncio
async def test_migration_commit_rollback_and_cleanup_resume(tmp_path, load):
    module = load("src.infrastructure.persistence.database")
    migration = importlib.import_module(module.__package__ + ".migrations.0001_initial")
    load("src.shared.cache").init_cache(tmp_path / "cache")
    old = tmp_path / "fortune"
    old.mkdir()
    with sqlite3.connect(old / "fortune.db") as source:
        source.execute(
            "CREATE TABLE fortune_data(user_id TEXT, date_str TEXT, stars INTEGER, img_url TEXT, session_id TEXT)"
        )
        source.executemany(
            "INSERT INTO fortune_data VALUES(?,?,?,?,?)",
            [
                (
                    "good",
                    date.today().isoformat(),
                    4,
                    "https://image",
                    "p:GroupMessage:g",
                ),
                ("missing", date.today().isoformat(), 1, None, None),
            ],
        )
    taskfile = tmp_path / "revoke_tasks.json"
    bad = {
        "task_id": "task",
        "target": "message",
        "platform_id": "p",
        "due_at": 2000000000,
        "message_id": "123",
    }
    taskfile.write_text(json.dumps({"tasks": [bad]}))
    with pytest.raises(ValueError, match="SID"):
        await module.Database(tmp_path).initialize()
    assert old.exists() and taskfile.exists()
    with sqlite3.connect(tmp_path / "db.sqlite") as source:
        assert source.execute("SELECT count(*) FROM migration").fetchone()[0] == 0
        assert not source.execute(
            "SELECT name FROM sqlite_master WHERE name='daily_fortune'"
        ).fetchone()
    bad["session_id"] = "p:GroupMessage:g"
    taskfile.write_text(json.dumps({"tasks": [bad]}))
    with (
        patch.object(migration, "cleanup", side_effect=OSError("cleanup interrupted")),
        pytest.raises(OSError, match="interrupted"),
    ):
        await module.Database(tmp_path).initialize()
    assert old.exists()
    db = module.Database(tmp_path)
    await db.initialize()
    try:
        assert not old.exists() and not taskfile.exists()
        assert (
            await (
                await db.connection.execute("SELECT count(*) FROM daily_fortune")
            ).fetchone()
        )[0] == 1
        assert (
            await (
                await db.connection.execute("SELECT count(*) FROM migration")
            ).fetchone()
        )[0] == 1
        assert (
            await (
                await db.connection.execute("SELECT session_id FROM setu_schedule_task")
            ).fetchone()
        )[0] == "p:GroupMessage:g"
    finally:
        await db.close()
