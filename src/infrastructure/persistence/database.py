"""插件共享数据库及历史窗口。"""

import asyncio
import importlib
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import aiosqlite

from ...shared.cache import get_cache


class Database:
    def __init__(self, root: Path):
        self.root = root
        self.connection = None
        self.lock = asyncio.Lock()
        self.cleanup_date = None

    async def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.connection = await aiosqlite.connect(self.root / "db.sqlite")
        self.connection.row_factory = aiosqlite.Row
        try:
            await self.connection.execute("PRAGMA foreign_keys=ON")
            await self.connection.execute(
                "CREATE TABLE IF NOT EXISTS migration(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            await self.connection.commit()
            for path in sorted(
                Path(__file__).with_name("migrations").glob("[0-9]*_*.py")
            ):
                version = int(path.stem.split("_", 1)[0])
                row = await (
                    await self.connection.execute(
                        "SELECT 1 FROM migration WHERE version=?", (version,)
                    )
                ).fetchone()
                module = importlib.import_module(
                    f"{__package__}.migrations.{path.stem}"
                )
                if row is None:
                    try:
                        await self.connection.execute("BEGIN")
                        await module.upgrade(self.connection, self.root)
                        await self.connection.execute(
                            "INSERT INTO migration VALUES(?,?,?)",
                            (version, path.stem, datetime.now().isoformat()),
                        )
                        await self.connection.commit()
                    except BaseException:
                        await self.connection.rollback()
                        raise
                await asyncio.to_thread(module.cleanup, self.root)
            await self.cleanup()
        except BaseException:
            await self.close()
            raise

    async def cleanup(self):
        today = date.today()
        async with self.lock:
            if self.cleanup_date == today:
                return
            cutoff = (today - timedelta(days=29)).isoformat()
            rows = await (
                await self.connection.execute(
                    "SELECT id FROM daily_fortune WHERE date < ?", (cutoff,)
                )
            ).fetchall()
            try:
                await self.connection.execute("BEGIN")
                await self.connection.execute(
                    "DELETE FROM daily_fortune WHERE date < ?", (cutoff,)
                )
                images = await (
                    await self.connection.execute(
                        "SELECT DISTINCT image_url FROM setu_history WHERE date < ? AND id NOT IN (SELECT setu_history_id FROM daily_fortune WHERE setu_history_id IS NOT NULL)",
                        (cutoff,),
                    )
                ).fetchall()
                await self.connection.execute(
                    "DELETE FROM setu_history WHERE date < ? AND id NOT IN (SELECT setu_history_id FROM daily_fortune WHERE setu_history_id IS NOT NULL)",
                    (cutoff,),
                )
                retained = {
                    row[0]
                    for row in await (
                        await self.connection.execute(
                            "SELECT DISTINCT image_url FROM setu_history"
                        )
                    ).fetchall()
                }
                await self.connection.commit()
            except BaseException:
                await self.connection.rollback()
                raise
            for image in images:
                if image["image_url"] not in retained:
                    key = uuid5(NAMESPACE_URL, image["image_url"]).hex
                    for file in (self.root / "cache" / "setu").glob(f"{key}.*"):
                        get_cache().remove(file)
            for row in rows:
                for file in (self.root / "cache" / "fortune").glob(f"{row['id']}-*"):
                    get_cache().remove(file)
            self.cleanup_date = today

    @asynccontextmanager
    async def transaction(self):
        await self.cleanup()
        async with self.lock:
            try:
                await self.connection.execute("BEGIN")
                yield self.connection
                await self.connection.commit()
            except BaseException:
                await self.connection.rollback()
                raise

    async def add_history(self, session_id, user_id, images, tags):
        await self.cleanup()
        ids = []
        async with self.transaction() as db:
            for image in images:
                cursor = await db.execute(
                    "INSERT INTO setu_history(session_id,user_id,date,tags,source_url,image_url) VALUES(?,?,?,?,?,?)",
                    (
                        session_id,
                        user_id,
                        datetime.now().isoformat(),
                        json.dumps(image.tags or tags, ensure_ascii=False)
                        if image.tags or tags
                        else None,
                        image.source_url,
                        image.image_url,
                    ),
                )
                ids.append(cursor.lastrowid)
        return ids

    async def preference(self, user_id):
        await self.cleanup()
        row = await (
            await self.connection.execute(
                "SELECT theme,tags FROM user_preference WHERE user_id=?",
                (user_id,),
            )
        ).fetchone()
        return dict(row) if row else {"theme": None, "tags": None}

    async def set_preference(self, user_id, field, value):
        if field not in {"theme", "tags"}:
            raise ValueError(field)
        await self.cleanup()
        async with self.transaction() as db:
            await db.execute(
                f"INSERT INTO user_preference(user_id,{field}) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET {field}=excluded.{field}",
                (user_id, value),
            )

    async def close(self):
        if self.connection is not None:
            await self.connection.close()
            self.connection = None


_database = None


async def init_database(root):
    global _database
    db = Database(Path(root))
    await db.initialize()
    _database = db
    return db


def get_database():
    if _database is None:
        raise RuntimeError("插件数据库尚未初始化")
    return _database


async def close_database():
    global _database
    if _database is not None:
        await _database.close()
        _database = None
