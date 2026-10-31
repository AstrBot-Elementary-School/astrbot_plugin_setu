"""统一数据库；旧目录只在提交成功后清理。"""

import json
import shutil
import sqlite3
from datetime import date, timedelta


async def upgrade(db, root):
    statements = [
        "CREATE TABLE setu_history(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,user_id TEXT NOT NULL,date TEXT NOT NULL,tags TEXT,source_url TEXT,image_url TEXT NOT NULL)",
        "CREATE TABLE daily_fortune(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,user_id TEXT NOT NULL,date TEXT NOT NULL,stars INTEGER NOT NULL,setu_history_id INTEGER REFERENCES setu_history(id),UNIQUE(session_id,user_id,date))",
        "CREATE TABLE user_preference(user_id TEXT PRIMARY KEY NOT NULL,theme TEXT,tags TEXT)",
        "CREATE TABLE setu_schedule_task(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,target TEXT NOT NULL,due_at REAL NOT NULL,payload TEXT NOT NULL)",
        "CREATE INDEX setu_history_date ON setu_history(date)",
        "CREATE INDEX daily_fortune_date ON daily_fortune(date)",
    ]
    for sql in statements:
        await db.execute(sql)
    old = root / "fortune" / "fortune.db"
    if old.exists():
        with sqlite3.connect(f"file:{old}?mode=ro", uri=True) as source:
            source.row_factory = sqlite3.Row
            columns = {
                row[1] for row in source.execute("PRAGMA table_info(fortune_data)")
            }
            if "session_id" in columns:
                cutoff = (date.today() - timedelta(days=29)).isoformat()
                for row in source.execute(
                    "SELECT * FROM fortune_data WHERE date_str >= ?", (cutoff,)
                ):
                    sid = row["session_id"]
                    if not sid or len(sid.split(":", 2)) != 3:
                        continue
                    history_id = None
                    if row["img_url"]:
                        cursor = await db.execute(
                            "INSERT INTO setu_history(session_id,user_id,date,image_url) VALUES(?,?,?,?)",
                            (sid, row["user_id"], row["date_str"], row["img_url"]),
                        )
                        history_id = cursor.lastrowid
                    await db.execute(
                        "INSERT INTO daily_fortune(session_id,user_id,date,stars,setu_history_id) VALUES(?,?,?,?,?)",
                        (
                            sid,
                            row["user_id"],
                            row["date_str"],
                            row["stars"],
                            history_id,
                        ),
                    )
    for name in ("revoke_tasks.json", "doujinshi_file_cleanup_tasks.json"):
        path = root / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        tasks = payload["tasks"]
        for original in tasks:
            task = dict(original)
            if name == "doujinshi_file_cleanup_tasks.json":
                task["target"] = "group_file"
            sid = task.get("session_id")
            if not sid and task.get("platform_id") and task.get("group_id"):
                sid = f"{task['platform_id']}:GroupMessage:{task['group_id']}"
            if not sid or len(sid.split(":", 2)) != 3:
                raise ValueError(f"{name} 中的任务缺少完整 SID：{task}")
            target = task["target"]
            if target == "message":
                required = ("message_id",)
                fields = ("message_id", "failure_count")
            elif target == "group_file":
                required = ("group_id", "file_name")
                fields = (
                    "group_id",
                    "file_id",
                    "file_name",
                    "before_file_ids",
                    "expected_file_size",
                    "failure_count",
                )
                if not task.get("file_id") and "before_file_ids" not in task:
                    raise ValueError(f"{name} 中的群文件任务缺少识别信息：{original}")
            else:
                raise ValueError(f"{name} 中的任务目标无效：{original}")
            if any(not task.get(key) for key in required):
                raise ValueError(f"{name} 中的任务缺少目标字段：{original}")
            data = {key: task[key] for key in fields if key in task}
            values = (
                task["task_id"],
                sid,
                target,
                task["due_at"],
                json.dumps(data, ensure_ascii=False, sort_keys=True),
            )
            previous = await (
                await db.execute(
                    "SELECT * FROM setu_schedule_task WHERE id=?", (task["task_id"],)
                )
            ).fetchone()
            if previous is not None:
                if tuple(previous) != values:
                    raise ValueError(f"{name} 中的任务 ID 冲突：{original}")
            else:
                await db.execute(
                    "INSERT INTO setu_schedule_task VALUES(?,?,?,?,?)", values
                )


def cleanup(root):
    for name in ("fortune", "send_cache", "doujinshi"):
        path = root / name
        if path.exists():
            shutil.rmtree(path)
    for name in (
        "config.json",
        "session_overrides.json",
        "revoke_tasks.json",
        "doujinshi_file_cleanup_tasks.json",
        "config_templates_migrated_v1",
        "config_templates_migrated_v1.tmp",
    ):
        (root / name).unlink(missing_ok=True)

    for pattern in (
        ".revoke_tasks.json.*.tmp",
        ".doujinshi_file_cleanup_tasks.json.*.tmp",
    ):
        for path in root.glob(pattern):
            path.unlink()
