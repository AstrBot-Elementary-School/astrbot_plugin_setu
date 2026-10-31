"""可跨插件重启恢复的 OneBot 撤回与群文件删除调度。"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

from astrbot.api.event import AstrMessageEvent

from ...shared import get_logger
from ..astrbot.session_identity import get_event_session_identity
from ..persistence.database import get_database
from .platform_capabilities import is_onebot_like_platform

logger = get_logger()

_MESSAGE_TARGET = "message"
_GROUP_FILE_TARGET = "group_file"
_MAX_CONSECUTIVE_FAILURES = 3


@dataclass(frozen=True, slots=True)
class GroupFile:
    """OneBot 群根目录中的文件摘要。"""

    file_id: str
    file_name: str
    file_size: int | None


@dataclass(frozen=True, slots=True)
class RevokeTask:
    """可恢复的 OneBot 删除任务。"""

    task_id: str
    target: str
    session_id: str
    due_at: float
    message_id: str | None = None
    group_id: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    before_file_ids: tuple[str, ...] = ()
    expected_file_size: int | None = None
    failure_count: int = 0


class RecoverableRevokeScheduler:
    """统一维护消息撤回与群文件删除的持久化任务。"""

    def __init__(self, data_dir: Path | str, context: object) -> None:
        self._database = get_database()
        self._context = context
        self._records: dict[str, RevokeTask] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """加载待删除任务，迁移旧本子队列并按到期时间恢复。"""
        rows = await (
            await self._database.connection.execute("SELECT * FROM setu_schedule_task")
        ).fetchall()
        records = [
            RevokeTask(
                task_id=row["id"],
                session_id=row["session_id"],
                target=row["target"],
                due_at=row["due_at"],
                **json.loads(row["payload"]),
            )
            for row in rows
        ]
        async with self._lock:
            self._records = {record.task_id: record for record in records}
            for record in records:
                self._schedule_record(record)

    async def stop(self) -> None:
        """停止内存计时协程，保留持久化任务供下次启动恢复。"""
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def schedule_revoke(
        self,
        event: AstrMessageEvent,
        message_id: str,
        delay: int,
    ) -> bool:
        """持久化登记一条 OneBot 消息撤回任务。"""
        normalized_id = str(message_id or "").strip()
        if not normalized_id:
            logger.warning("[revoke] 跳过登记：message_id 为空")
            return False
        if not _is_onebot_event(event):
            logger.warning(
                "[revoke] 跳过登记：当前平台不是 OneBot，message_id=%s", normalized_id
            )
            return False

        platform_id = _event_text(event, "get_platform_id")
        if not platform_id:
            logger.warning(
                "[revoke] 跳过登记：缺少平台 ID，message_id=%s", normalized_id
            )
            return False

        try:
            client = _event_client(event)
        except RuntimeError as exc:
            logger.warning("[revoke] 跳过登记：%s", exc)
            return False
        if not _supports_delete_msg(client):
            logger.warning(
                "[revoke] 跳过登记：delete_msg 不受支持，message_id=%s", normalized_id
            )
            return False

        record = RevokeTask(
            task_id=uuid4().hex,
            target=_MESSAGE_TARGET,
            session_id=get_event_session_identity(event).session_id,
            due_at=time() + max(0, int(delay)),
            message_id=normalized_id,
        )
        await self._register(record)
        logger.info(
            "[revoke] 已登记可恢复消息撤回: platform_id=%s, message_id=%s, delay=%ss",
            platform_id,
            normalized_id,
            delay,
        )
        return True

    async def snapshot_group_file_ids(
        self, event: AstrMessageEvent
    ) -> frozenset[str] | None:
        """读取发送前的群根目录文件 ID，用于发送后识别新增文件。"""
        if not _is_onebot_event(event):
            return None
        try:
            files = await self._list_group_files(event)
        except Exception as exc:
            logger.warning("[revoke] 无法读取发送前群文件列表: %s", exc)
            return None
        return frozenset(file.file_id for file in files)

    async def schedule_group_file_revoke(
        self,
        event: AstrMessageEvent,
        *,
        before_file_ids: frozenset[str],
        file_name: str,
        expected_file_size: int | None,
        delay: int,
    ) -> bool:
        """持久化群文件删除任务，并在可见时提前锁定文件 ID。"""
        if delay <= 0:
            return False
        if not _is_onebot_event(event):
            logger.warning("[revoke] 跳过群文件登记：当前平台不是 OneBot")
            return False

        group_id = _event_text(event, "get_group_id")
        platform_id = _event_text(event, "get_platform_id")
        normalized_name = file_name.strip()
        if not group_id or not platform_id or not normalized_name:
            logger.warning("[revoke] 跳过群文件登记：缺少群号、平台 ID 或文件名")
            return False

        record = RevokeTask(
            task_id=uuid4().hex,
            target=_GROUP_FILE_TARGET,
            session_id=get_event_session_identity(event).session_id,
            due_at=time() + delay,
            group_id=group_id,
            file_name=normalized_name,
            before_file_ids=tuple(sorted(before_file_ids)),
            expected_file_size=expected_file_size,
        )
        await self._register(record)

        try:
            file_id = await self._resolve_group_file_id(_event_client(event), record)
        except Exception as exc:
            logger.warning(
                "[revoke] 发送后无法读取群文件列表；已保留待识别任务: "
                "group_id=%s, file_name=%s, error=%s",
                group_id,
                normalized_name,
                exc,
            )
            return True

        if file_id is None:
            logger.info(
                "[revoke] 群文件暂未可见；已保留待识别任务至到期删除: "
                "group_id=%s, file_name=%s",
                group_id,
                normalized_name,
            )
            return True

        await self._replace_record(replace(record, file_id=file_id))
        logger.info(
            "[revoke] 已登记可恢复群文件删除: group_id=%s, file_id=%s, delay=%ss",
            group_id,
            file_id,
            delay,
        )
        return True

    async def _register(self, record: RevokeTask) -> None:
        async with self._lock:
            self._records[record.task_id] = record
            await self._persist_records()
            self._schedule_record(record)

    async def _replace_record(self, record: RevokeTask) -> None:
        """用已解析的目标信息更新已持久化任务。"""
        async with self._lock:
            if record.task_id not in self._records:
                return
            self._records[record.task_id] = record
            await self._persist_records()

    async def _list_group_files(self, event: AstrMessageEvent) -> tuple[GroupFile, ...]:
        group_id = _event_text(event, "get_group_id")
        if not group_id:
            raise ValueError("当前消息不是群聊")
        return await self._list_group_files_for_group(_event_client(event), group_id)

    async def _list_group_files_for_group(
        self, client: Any, group_id: str
    ) -> tuple[GroupFile, ...]:
        response = await _call_onebot_action(
            client, "get_group_root_files", group_id=group_id
        )
        return _parse_group_files(response)

    async def _resolve_group_file_id(
        self, client: Any, record: RevokeTask
    ) -> str | None:
        """根据发送前快照和文件特征定位唯一新增群文件。"""
        files = await self._list_group_files_for_group(
            client, _required_task_value(record.group_id)
        )
        candidates = _new_group_file_candidates(files, record)
        return candidates[0].file_id if len(candidates) == 1 else None

    def _schedule_record(self, record: RevokeTask) -> None:
        if record.task_id in self._tasks:
            return
        task = asyncio.create_task(
            self._delete_when_due(record.task_id, record.due_at),
            name=f"setu_revoke_{record.target}_{record.task_id}",
        )
        self._tasks[record.task_id] = task
        task.add_done_callback(
            lambda completed, task_id=record.task_id: self._tasks.pop(task_id, None)
        )

    async def _delete_when_due(self, task_id: str, due_at: float) -> None:
        record: RevokeTask | None = None
        try:
            await asyncio.sleep(max(0.0, due_at - time()))
            async with self._lock:
                record = self._records.get(task_id)
            if record is None:
                return
            client = self._get_client_for_task(record)
            if record.target == _MESSAGE_TARGET:
                await _call_delete_msg(client, _required_task_value(record.message_id))
            else:
                file_id = record.file_id
                if file_id is None:
                    file_id = await self._resolve_group_file_id(client, record)
                if file_id is None:
                    raise RuntimeError(
                        "到期时未能唯一识别本子群文件: "
                        f"group_id={record.group_id}, file_name={record.file_name}"
                    )
                await _call_onebot_action(
                    client,
                    "delete_group_file",
                    group_id=_required_task_value(record.group_id),
                    file_id=file_id,
                )
        except asyncio.CancelledError:
            logger.debug("[revoke] 已停止等待删除: task_id=%s", task_id)
            raise
        except Exception as exc:
            if record is None:
                logger.warning(
                    "[revoke] 删除任务启动失败，无法登记失败次数: task_id=%s, error=%s",
                    task_id,
                    exc,
                )
                return
            failure_state = await self._record_delete_failure(record)
            if failure_state is None:
                logger.warning(
                    "[revoke] 删除失败，但任务已不在队列中: "
                    "task_id=%s, target=%s, error=%s",
                    record.task_id,
                    record.target,
                    exc,
                )
                return
            failure_count, removed = failure_state
            if removed:
                logger.warning(
                    "[revoke] 删除连续失败达到上限，已移除任务记录: "
                    "task_id=%s, target=%s, failure_count=%s, error=%s",
                    record.task_id,
                    record.target,
                    failure_count,
                    exc,
                )
            else:
                logger.warning(
                    "[revoke] 删除失败，保留任务供下次启动恢复: "
                    "task_id=%s, target=%s, failure_count=%s/%s, error=%s",
                    record.task_id,
                    record.target,
                    failure_count,
                    _MAX_CONSECUTIVE_FAILURES,
                    exc,
                )
            return

        async with self._lock:
            if self._records.pop(task_id, None) is not None:
                await self._persist_records()
        logger.info(
            "[revoke] 已执行删除: task_id=%s, target=%s",
            record.task_id,
            record.target,
        )

    async def _record_delete_failure(
        self, record: RevokeTask
    ) -> tuple[int, bool] | None:
        """持久化一次实际删除失败，并在第三次失败时丢弃任务。"""
        async with self._lock:
            current = self._records.get(record.task_id)
            if current is None:
                return None
            failure_count = current.failure_count + 1
            reached_limit = failure_count >= _MAX_CONSECUTIVE_FAILURES
            if reached_limit:
                self._records.pop(record.task_id)
            else:
                self._records[record.task_id] = replace(
                    current, failure_count=failure_count
                )
            await self._persist_records()
        return failure_count, reached_limit

    def _get_client_for_task(self, record: RevokeTask) -> Any:
        get_platform_inst = _callable_attr(self._context, "get_platform_inst")
        if get_platform_inst is None:
            raise RuntimeError("AstrBot context 不支持按平台 ID 获取适配器")
        platform = get_platform_inst(record.session_id.split(":", 2)[0])
        if platform is None:
            raise RuntimeError(
                f"找不到平台适配器: {record.session_id.split(':', 2)[0]}"
            )
        get_client = _callable_attr(platform, "get_client")
        if get_client is None:
            raise RuntimeError(
                f"平台不支持 OneBot 客户端: {record.session_id.split(':', 2)[0]}"
            )
        return get_client()

    async def _persist_records(self) -> None:
        await self._database.cleanup()
        async with self._database.lock:
            db = self._database.connection
            try:
                await db.execute("DELETE FROM setu_schedule_task")
                for record in self._records.values():
                    if record.target == _MESSAGE_TARGET:
                        payload = {"message_id": record.message_id}
                    else:
                        payload = {
                            "group_id": record.group_id,
                            "file_id": record.file_id,
                        }
                        if record.file_id is None:
                            payload.update(
                                file_name=record.file_name,
                                before_file_ids=record.before_file_ids,
                            )
                            if record.expected_file_size is not None:
                                payload["expected_file_size"] = (
                                    record.expected_file_size
                                )
                    if record.failure_count:
                        payload["failure_count"] = record.failure_count
                    await db.execute(
                        "INSERT INTO setu_schedule_task VALUES(?,?,?,?,?)",
                        (
                            record.task_id,
                            record.session_id,
                            record.target,
                            record.due_at,
                            json.dumps(payload),
                        ),
                    )
                await db.commit()
            except BaseException:
                await db.rollback()
                raise


_scheduler: RecoverableRevokeScheduler | None = None


async def init_revoke_scheduler(
    data_dir: Path | str,
    context: object,
) -> RecoverableRevokeScheduler:
    """初始化统一可恢复撤回调度器。"""
    global _scheduler
    if _scheduler is not None:
        await _scheduler.stop()
    _scheduler = RecoverableRevokeScheduler(data_dir, context)
    await _scheduler.initialize()
    return _scheduler


def get_revoke_scheduler() -> RecoverableRevokeScheduler | None:
    """返回已初始化的统一可恢复撤回调度器。"""
    return _scheduler


async def stop_revoke_scheduler() -> None:
    """停止内存计时协程，保留任务供下一次启动恢复。"""
    global _scheduler
    if _scheduler is None:
        return
    await _scheduler.stop()
    _scheduler = None


async def schedule_revoke(
    event: AstrMessageEvent,
    message_id: str,
    delay: int,
) -> bool:
    """通过统一可恢复调度器登记消息撤回。"""
    scheduler = get_revoke_scheduler()
    if scheduler is None:
        logger.warning("[revoke] 调度器尚未初始化，未登记 message_id=%s", message_id)
        return False
    return await scheduler.schedule_revoke(event, message_id, delay)


def _required_task_value(value: str | None) -> str:
    if value is None:
        raise RuntimeError("持久化撤回任务缺少必要目标字段")
    return value


def _event_text(event: AstrMessageEvent, method_name: str) -> str:
    method = _callable_attr(event, method_name)
    if method is None:
        return ""
    value = method()
    return str(value).strip() if value else ""


def _is_onebot_event(event: AstrMessageEvent) -> bool:
    return is_onebot_like_platform(_platform_name(event))


def _platform_name(event: AstrMessageEvent) -> str | None:
    platform = getattr(event, "platform", None)
    name = getattr(platform, "name", None)
    if isinstance(name, str) and name:
        return name
    getter = _callable_attr(event, "get_platform_name")
    if getter is None:
        return None
    value = getter()
    return str(value) if value else None


def _event_client(event: AstrMessageEvent) -> Any:
    client = getattr(event, "bot", None) or getattr(event, "_bot", None)
    if client is None:
        raise RuntimeError("当前事件不提供 OneBot 客户端")
    return client


def _supports_delete_msg(client: Any) -> bool:
    return (
        _callable_attr(client, "delete_msg") is not None
        or _callable_attr(getattr(client, "api", None), "call_action") is not None
        or _callable_attr(client, "call_action") is not None
    )


async def _call_delete_msg(client: Any, message_id: str) -> Any:
    delete_msg = _callable_attr(client, "delete_msg")
    if delete_msg is not None:
        return await _maybe_await(delete_msg(message_id=message_id))
    return await _call_onebot_action(client, "delete_msg", message_id=message_id)


async def _call_onebot_action(client: Any, action: str, **kwargs: object) -> Any:
    call_action = _callable_attr(client, "call_action")
    if call_action is None:
        call_action = _callable_attr(getattr(client, "api", None), "call_action")
    if call_action is None:
        raise RuntimeError(f"OneBot 客户端不支持 {action}")
    result = await _maybe_await(call_action(action, **kwargs))
    if isinstance(result, Mapping):
        status = result.get("status")
        retcode = result.get("retcode")
        if status in {"failed", "error"} or (
            isinstance(retcode, int) and not isinstance(retcode, bool) and retcode != 0
        ):
            raise RuntimeError(f"OneBot action {action} 返回失败: {result}")
    return result


def _parse_group_files(response: object) -> tuple[GroupFile, ...]:
    files: list[GroupFile] = []
    for item in _group_file_items(response):
        if not isinstance(item, Mapping):
            continue
        file_id = item.get("file_id")
        file_name = item.get("file_name")
        if not isinstance(file_id, str) or not file_id:
            continue
        if not isinstance(file_name, str) or not file_name:
            continue
        files.append(
            GroupFile(
                file_id=file_id,
                file_name=file_name,
                file_size=_parse_file_size(item.get("file_size")),
            )
        )
    return tuple(files)


def _group_file_items(response: object) -> list[object]:
    payload = response
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping | list):
        payload = payload["data"]
    if isinstance(payload, Mapping):
        for key in ("files", "root_files"):
            files = payload.get(key)
            if isinstance(files, list):
                return files
    return payload if isinstance(payload, list) else []


def _parse_file_size(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _matches_expected_size(actual: int | None, expected: int | None) -> bool:
    return actual is None or expected is None or actual == expected


def _new_group_file_candidates(
    files: tuple[GroupFile, ...], record: RevokeTask
) -> list[GroupFile]:
    """筛选发送快照之后出现且与待删除 PDF 一致的群文件。"""
    file_name = _required_task_value(record.file_name)
    before_file_ids = frozenset(record.before_file_ids)
    return [
        file
        for file in files
        if file.file_id not in before_file_ids
        and file.file_name == file_name
        and _matches_expected_size(file.file_size, record.expected_file_size)
    ]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _callable_attr(obj: object | None, name: str) -> Any | None:
    if obj is None:
        return None
    value = getattr(obj, name, None)
    return value if callable(value) else None


__all__ = [
    "RecoverableRevokeScheduler",
    "RevokeTask",
    "get_revoke_scheduler",
    "init_revoke_scheduler",
    "schedule_revoke",
    "stop_revoke_scheduler",
]
