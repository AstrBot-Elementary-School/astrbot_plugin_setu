"""SQLite implementation for fortune data persistence."""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ...application.ports import FortuneRepository
from ...domain.fortune.entities import FortuneGenerationRequest, FortuneRecord


class SQLiteFortuneRepo(FortuneRepository):
    """SQLite-backed fortune repository implementation."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._db_path = data_dir / "fortune.db"
        self._cache_dir = data_dir / "cache"
        self._db_lock = asyncio.Lock()
        self._cache_lock = asyncio.Lock()
        self._db_inited = False
        self._last_cleanup_date: str | None = None

    async def initialize(self) -> None:
        """Initialize database and cache directory."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        await self._init_db()
        today = datetime.date.today().isoformat()
        await self.cleanup_expired_cache(today)
        self._db_inited = True
        logger.info("[fortune] Database initialized at %s", self._db_path)

    async def _init_db(self) -> None:
        """Initialize database tables."""
        import aiosqlite

        async with self._db_lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fortune_data (
                        user_id   TEXT NOT NULL,
                        username  TEXT,
                        date_str  TEXT NOT NULL,
                        title     TEXT NOT NULL,
                        stars     INTEGER NOT NULL,
                        desc_text TEXT NOT NULL,
                        extra     TEXT NOT NULL,
                        theme     TEXT NOT NULL,
                        image_cached INTEGER DEFAULT 0,
                        img_url   TEXT,
                        last_view_date TEXT,
                        group_id  TEXT,
                        session_id TEXT,
                        PRIMARY KEY (user_id, date_str)
                    )
                    """
                )
                await db.commit()
                await self._migrate_db(db)

    async def _migrate_db(self, db: Any) -> None:
        """Database migration: add missing columns."""
        cursor = await db.execute("PRAGMA table_info(fortune_data)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "img_url" not in column_names:
            await db.execute("ALTER TABLE fortune_data ADD COLUMN img_url TEXT")
            await db.commit()

        if "username" not in column_names:
            await db.execute("ALTER TABLE fortune_data ADD COLUMN username TEXT")
            await db.commit()

        if "last_view_date" not in column_names:
            await db.execute("ALTER TABLE fortune_data ADD COLUMN last_view_date TEXT")
            await db.commit()

        if "group_id" not in column_names:
            await db.execute("ALTER TABLE fortune_data ADD COLUMN group_id TEXT")
            await db.commit()
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_fortune_group ON fortune_data(group_id, date_str)"
            )
            await db.commit()

        if "session_id" not in column_names:
            await db.execute("ALTER TABLE fortune_data ADD COLUMN session_id TEXT")
            await db.commit()

    def _row_to_record(
        self, row: tuple, user_id: str, username: str, date_str: str
    ) -> FortuneRecord:
        """Convert a database row to FortuneRecord."""
        stored_username = row[9] if len(row) > 9 else None
        return FortuneRecord(
            user_id=user_id,
            username=username or stored_username or user_id,
            date_str=date_str,
            title=row[0],
            star_count=row[1],
            description=row[2],
            extra_message=row[3],
            theme_color=row[4],
            image_cached=bool(row[5]),
            img_url=row[6],
            last_view_date=row[7] if len(row) > 7 else date_str,
            group_id=row[8] if len(row) > 8 else None,
            session_id=row[10] if len(row) > 10 else None,
        )

    async def get_today_fortune(
        self, request: FortuneGenerationRequest
    ) -> FortuneRecord | None:
        """Get fortune for today."""
        import aiosqlite

        async with self._db_lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                cursor = await db.execute(
                    "SELECT title, stars, desc_text, extra, theme, image_cached, img_url, last_view_date, group_id, username, session_id "
                    "FROM fortune_data WHERE user_id = ? AND date_str = ?",
                    (request.user_id, request.date_str),
                )
                row = await cursor.fetchone()
                if row:
                    return self._row_to_record(
                        row, request.user_id, request.username, request.date_str
                    )
        return None

    async def save_fortune(self, record: FortuneRecord) -> bool:
        """Save or update fortune record."""
        import aiosqlite

        try:
            async with self._db_lock:
                async with aiosqlite.connect(str(self._db_path)) as db:
                    await db.execute(
                        "INSERT OR REPLACE INTO fortune_data "
                        "(user_id, username, date_str, title, stars, desc_text, extra, theme, image_cached, img_url, last_view_date, group_id, session_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            record.user_id,
                            record.username,
                            record.date_str,
                            record.title,
                            record.star_count,
                            record.description,
                            record.extra_message,
                            record.theme_color,
                            int(record.image_cached),
                            record.img_url,
                            record.last_view_date,
                            record.group_id,
                            record.session_id,
                        ),
                    )
                    await db.commit()
            return True
        except Exception as exc:
            logger.warning("[fortune] Failed to save fortune: %s", exc)
            return False

    async def delete_fortune(self, user_id: str, date_str: str) -> bool:
        """Delete fortune record."""
        import aiosqlite

        try:
            async with self._db_lock:
                async with aiosqlite.connect(str(self._db_path)) as db:
                    await db.execute(
                        "DELETE FROM fortune_data WHERE user_id = ? AND date_str = ?",
                        (user_id, date_str),
                    )
                    await db.commit()
            return True
        except Exception as exc:
            logger.warning("[fortune] Failed to delete fortune: %s", exc)
            return False

    async def delete_group_fortunes(self, group_id: str, date_str: str) -> int:
        """Delete all fortune records for a group on a given date."""
        import aiosqlite

        async with self._db_lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM fortune_data WHERE date_str = ? AND (group_id = ? OR group_id IS NULL)",
                    (date_str, group_id),
                )
                row = await cursor.fetchone()
                count = row[0] if row else 0

                await db.execute(
                    "DELETE FROM fortune_data WHERE date_str = ? AND (group_id = ? OR group_id IS NULL)",
                    (date_str, group_id),
                )
                await db.commit()

        return count

    async def delete_all_fortunes(self, date_str: str) -> int:
        """Delete all fortune records for a given date."""
        import aiosqlite

        async with self._db_lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM fortune_data WHERE date_str = ?",
                    (date_str,),
                )
                row = await cursor.fetchone()
                count = row[0] if row else 0

                await db.execute(
                    "DELETE FROM fortune_data WHERE date_str = ?",
                    (date_str,),
                )
                await db.commit()

        return count

    async def get_active_users(self, days: int = 3) -> list[str]:
        """Get list of active users (viewed fortune within N days)."""
        import aiosqlite

        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        async with self._db_lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                cursor = await db.execute(
                    "SELECT DISTINCT user_id FROM fortune_data WHERE COALESCE(last_view_date, date_str) >= ?",
                    (cutoff,),
                )
                rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_active_fortune_requests(
        self, days: int = 3, date_str: str | None = None
    ) -> list[FortuneGenerationRequest]:
        """Get latest generation request data for recently active users."""
        import aiosqlite

        target_date = date_str or datetime.date.today().isoformat()
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        async with self._db_lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                cursor = await db.execute(
                    """
                    SELECT user_id,
                           COALESCE(NULLIF(username, ''), user_id) AS username,
                           group_id, session_id
                    FROM fortune_data
                    WHERE COALESCE(last_view_date, date_str) >= ?
                    ORDER BY user_id,
                             COALESCE(last_view_date, date_str) DESC,
                             date_str DESC,
                             rowid DESC
                    """,
                    (cutoff,),
                )
                rows = await cursor.fetchall()

        requests: list[FortuneGenerationRequest] = []
        seen: set[str] = set()
        for user_id, username, group_id, session_id in rows:
            if user_id in seen:
                continue
            seen.add(user_id)
            requests.append(
                FortuneGenerationRequest(
                    user_id=str(user_id),
                    username=str(username or user_id),
                    date_str=target_date,
                    group_id=str(group_id) if group_id else None,
                    session_id=str(session_id) if session_id else None,
                )
            )
        return requests

    async def get_cached_image_path(self, user_id: str, date_str: str) -> Any | None:
        """Get cached image path for fortune."""
        cache_path = self._cache_dir / f"{user_id}_{date_str}.jpg"
        if cache_path.exists():
            return cache_path
        return None

    async def save_cached_image(
        self, user_id: str, date_str: str, image_data: bytes, img_url: str | None
    ) -> Any:
        """Save image to cache."""
        cache_path = self._cache_dir / f"{user_id}_{date_str}.jpg"

        async with self._cache_lock:
            await asyncio.to_thread(cache_path.write_bytes, image_data)

        import aiosqlite

        async with self._db_lock:
            async with aiosqlite.connect(str(self._db_path)) as db:
                await db.execute(
                    "UPDATE fortune_data SET image_cached = 1, img_url = ? "
                    "WHERE user_id = ? AND date_str = ?",
                    (img_url, user_id, date_str),
                )
                await db.commit()

        return cache_path

    async def delete_cached_image(self, user_id: str, date_str: str) -> bool:
        """Delete cached image."""
        cache_path = self._cache_dir / f"{user_id}_{date_str}.jpg"
        try:
            async with self._cache_lock:
                if cache_path.exists():
                    cache_path.unlink()
                    return True
        except OSError:
            pass
        return False

    async def cleanup_expired_cache(self, date_str: str) -> int:
        """Clean up cache files from before given date."""
        if self._last_cleanup_date == date_str:
            return 0

        removed = 0
        removed_size = 0

        try:
            async with self._cache_lock:
                for file_path in self._cache_dir.iterdir():
                    if not file_path.is_file():
                        continue
                    try:
                        file_name = file_path.stem
                        parts = file_name.rsplit("_", 1)
                        if len(parts) >= 2:
                            file_date = parts[-1]
                            if file_date != date_str:
                                file_size = file_path.stat().st_size
                                file_path.unlink()
                                removed += 1
                                removed_size += file_size
                        else:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            removed += 1
                            removed_size += file_size
                    except (OSError, ValueError):
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            removed += 1
                            removed_size += file_size
                        except OSError:
                            pass

            if removed > 0:
                logger.info(
                    "[fortune] Cleaned up %d expired cache files (%.2f MB)",
                    removed,
                    removed_size / 1024 / 1024,
                )

            self._last_cleanup_date = date_str

        except OSError as exc:
            logger.warning("[fortune] Failed to cleanup cache: %s", exc)

        return removed
