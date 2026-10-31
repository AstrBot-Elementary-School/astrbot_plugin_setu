"""共享 SQLite 中的每日运势。"""

from ...domain.fortune import FortuneRecord
from ...shared.cache import get_cache
from .database import get_database


class SQLiteFortuneRepo:
    def __init__(self):
        self.database = get_database()

    async def get_or_create(self, request, stars, refresh=False):
        database = self.database
        await database.cleanup()
        async with database.transaction() as db:
            args = (request.session_id, request.user_id, request.date_str)
            if refresh:
                await db.execute(
                    "UPDATE daily_fortune SET stars=?,setu_history_id=NULL WHERE session_id=? AND user_id=? AND date=?",
                    (stars, *args),
                )
            await db.execute(
                "INSERT INTO daily_fortune(session_id,user_id,date,stars) VALUES(?,?,?,?) ON CONFLICT(session_id,user_id,date) DO NOTHING",
                (*args, stars),
            )
            row = await (
                await db.execute(
                    "SELECT * FROM daily_fortune WHERE session_id=? AND user_id=? AND date=?",
                    args,
                )
            ).fetchone()
            record = FortuneRecord(
                row["id"],
                row["session_id"],
                row["user_id"],
                row["date"],
                row["stars"],
                row["setu_history_id"],
            )
            if refresh:
                self.invalidate(record.id)
            return record

    def invalidate(self, record_id):
        for path in (self.database.root / "cache" / "fortune").glob(f"{record_id}-*"):
            get_cache().remove(path)

    async def delete_fortunes(self, date_str, session_id=None):
        async with self.database.transaction():
            where = "date=?"
            args = [date_str]
            if session_id is not None:
                where += " AND session_id=?"
                args.append(session_id)
            rows = await (
                await self.database.connection.execute(
                    f"SELECT id FROM daily_fortune WHERE {where}", args
                )
            ).fetchall()
            await self.database.connection.execute(
                f"DELETE FROM daily_fortune WHERE {where}", args
            )
            for row in rows:
                self.invalidate(row["id"])
            return len(rows)

    async def attach_image(self, record_id, history_id):
        async with self.database.transaction():
            await self.database.connection.execute(
                "UPDATE daily_fortune SET setu_history_id=? WHERE id=? AND setu_history_id IS NULL",
                (history_id, record_id),
            )
