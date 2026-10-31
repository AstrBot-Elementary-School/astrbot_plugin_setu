# Adapted from astrbot_plugin_dna/scripts/ci (GPL-3.0), FlanChanXwO.
"""使用官方 AstrBot PluginManager 验证插件加载与生命周期。

该脚本只用于 PR/本地兼容性检查。它会把插件复制到临时 ``ASTRBOT_ROOT``，
再直接调用官方 ``PluginManager.load()``；不连接真实平台、不读取真实账号，且
只把插件初始化所需的本地文件写入临时根目录。
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypeVar

_STABLE_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?P<prefix>\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"token|secret|password|passwd|cookie|authorization|private[_-]?key)\b"
    r"\s*['\"]?\s*[:=]\s*['\"]?)(?P<value>[^,\s;\]}\"']+)"
)
_BEARER_RE = re.compile(r"(?i)(?<![A-Za-z0-9])Bearer\s+[^,\s;\]}]+")
_COOKIE_HEADER_RE = re.compile(r"(?im)\b(?:Cookie|Set-Cookie):\s*[^\r\n]+")
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://[^/\s:@]+:)[^@\s]+@")
_TOKEN_SHAPED_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:ghp_|github_pat_|sk-|xox[baprs]-|AKIA)[A-Za-z0-9_./-]+"
)
_SENSITIVE_ENV_NAME_RE = re.compile(
    r"(?i)(?:token|secret|password|passwd|cookie|authorization|api[_-]?key|"
    r"private[_-]?key|client[_-]?secret)"
)
# 只捕获普通异常和协作取消；不捕获 KeyboardInterrupt/SystemExit，避免把进程终止伪装成检查失败。
_CATCHABLE_ERRORS = (Exception, asyncio.CancelledError)
_EXCLUDED_NAMES = {
    ".git",
    "tmp",
    ".firecrawl",
    ".playwright-cli",
    ".serena",
    ".repo",
    ".DS_Store",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data",
    "cookies.json",
    "cookie.json",
    "cookies.txt",
    "secrets.json",
    "token.json",
}

_T = TypeVar("_T")


class LoaderCheckError(RuntimeError):
    """带有明确阶段名的 loader 检查错误。"""

    def __init__(self, phase: str, message: str) -> None:
        self.phase = phase
        super().__init__(f"[{phase}] {message}")


def select_latest_stable_version(tags: Iterable[str]) -> str:
    """从 tag 中选择最高的正式三段式 SemVer，排除所有预发布版本。"""

    candidates: list[tuple[tuple[int, int, int], str]] = []
    for raw_tag in tags:
        if not isinstance(raw_tag, str):
            continue
        tag = raw_tag.strip()
        match = _STABLE_VERSION_RE.fullmatch(tag)
        if match is None:
            continue
        candidates.append((tuple(int(part) for part in match.groups()), tag))
    if not candidates:
        raise ValueError("没有找到符合正式 stable 版本格式的 AstrBot release tag")
    return max(candidates, key=lambda item: item[0])[1]


def _is_excluded_name(name: str) -> bool:
    lowered = name.lower()
    if name in _EXCLUDED_NAMES or lowered in _EXCLUDED_NAMES:
        return True
    if name.startswith(".env"):
        return True
    return lowered.endswith((".sqlite", ".sqlite3", ".db", ".log", ".pyc"))


def _validate_plugin_name(plugin_name: str) -> None:
    if _PLUGIN_NAME_RE.fullmatch(plugin_name) is None:
        raise ValueError(
            f"插件名必须是可导入的单一 Python 目录名，实际为 {plugin_name!r}",
        )


def _copy_plugin_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for entry in source.iterdir():
        if _is_excluded_name(entry.name):
            continue
        if entry.is_symlink():
            # 不跟随可能指向仓库外或宿主机秘密的链接，避免 staging 越界。
            raise ValueError(f"插件源码包含不允许 staging 的符号链接: {entry}")
        target = destination / entry.name
        if entry.is_dir():
            _copy_plugin_tree(entry, target)
        elif entry.is_file():
            shutil.copy2(entry, target)
        else:
            raise OSError(f"无法 staging 非普通文件: {entry}")


def stage_plugin(
    *,
    plugin_dir: str | Path,
    astrbot_root: str | Path,
    plugin_name: str,
) -> Path:
    """把插件当前源码复制到临时 AstrBot 根下并排除运行期/仓库数据。"""

    source = Path(plugin_dir).expanduser().resolve()
    root = Path(astrbot_root).expanduser().resolve()
    _validate_plugin_name(plugin_name)
    if not source.is_dir():
        raise ValueError(f"插件目录不存在或不是目录: {source}")

    # 防止把目标目录放进源码目录后递归复制；临时根本来就不应是源码子目录。
    if root == source or source in root.parents:
        raise ValueError("ASTRBOT_ROOT 不能位于插件源码目录内")
    if root.exists() and not root.is_dir():
        raise ValueError(f"ASTRBOT_ROOT 不是目录: {root}")
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"ASTRBOT_ROOT 必须为空的临时目录: {root}")

    destination = root / "data" / "plugins" / plugin_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    (root / "data" / "__init__.py").touch()
    (root / "data" / "plugins" / "__init__.py").touch()
    _copy_plugin_tree(source, destination)
    return destination


def _read_plugin_metadata(plugin_dir: Path, plugin_name: str) -> tuple[str, str]:
    metadata_path = next(
        (
            plugin_dir / filename
            for filename in ("metadata.yaml", "metadata.yml")
            if (plugin_dir / filename).is_file()
        ),
        None,
    )
    if metadata_path is None:
        raise LoaderCheckError("metadata", "缺少 metadata.yaml 或 metadata.yml")

    try:
        import yaml

        raw = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise LoaderCheckError(
            "metadata",
            f"无法读取 {metadata_path.name}: {type(error).__name__}: {error}",
        ) from error
    if not isinstance(raw, Mapping):
        raise LoaderCheckError("metadata", "metadata 必须解析为对象")

    name = raw.get("name")
    version = raw.get("version")
    astrbot_version = raw.get("astrbot_version")
    if not isinstance(name, str) or not name.strip():
        raise LoaderCheckError("metadata", "metadata.name 不能为空")
    if name != plugin_name:
        raise LoaderCheckError(
            "metadata",
            f"metadata.name={name!r} 与插件目录名 {plugin_name!r} 不一致",
        )
    if not isinstance(version, str) or not version.strip():
        raise LoaderCheckError("metadata", "metadata.version 不能为空")
    return version, astrbot_version or ""


def _write_ci_plugin_config(astrbot_root: Path, plugin_name: str) -> None:
    config_path = astrbot_root / "data" / "config" / f"{plugin_name}_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _prepend_sys_path(*paths: Path) -> list[str]:
    inserted: list[str] = []
    for path in paths:
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
            inserted.append(value)
    return inserted


def _remove_sys_path(values: Sequence[str]) -> None:
    for value in values:
        try:
            sys.path.remove(value)
        except ValueError:
            # 同一进程内若官方模块主动重排 sys.path，目标值已不在路径中。
            continue


def _build_official_context(context_cls: type[Any], config: Any) -> Any:
    """按官方 Context 的真实签名传入最小依赖，不自定义替代 Context。"""

    parameters = inspect.signature(context_cls).parameters
    kwargs: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        if name in {"self", "cls"}:
            continue
        if name in {"config", "astrbot_config"}:
            kwargs[name] = config
        elif parameter.default is inspect.Parameter.empty:
            # Context 构造函数只保存这些宿主管理器；loader 检查不启动真实平台。
            kwargs[name] = None
    if "config" not in kwargs and "astrbot_config" not in kwargs:
        raise TypeError("官方 Context 构造函数没有可识别的配置参数")
    return context_cls(**kwargs)


def _tracking_manager_class(manager_cls: type[Any]) -> type[Any]:
    if not hasattr(manager_cls, "_cleanup_plugin_state"):
        return manager_cls

    class TrackingPluginManager(manager_cls):
        """在官方清理前保留失败初始化实例。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.captured_metadata: list[Any] = []
            super().__init__(*args, **kwargs)

        def _cleanup_plugin_state(self, *args: Any, **kwargs: Any) -> Any:
            get_all_stars = getattr(self.context, "get_all_stars", None)
            if callable(get_all_stars):
                self.captured_metadata.extend(tuple(get_all_stars()))
            return super()._cleanup_plugin_state(*args, **kwargs)

    return TrackingPluginManager


def _build_base_runtime(
    astrbot_source: Path,
    _astrbot_version: str,
    astrbot_root: Path,
    plugin_name: str,
) -> LoaderRuntime:
    """建立官方 Context/PluginManager，供同一套 loader 逻辑调用。"""

    import astrbot

    if not Path(astrbot.__file__).resolve().is_relative_to(astrbot_source):
        raise LoaderCheckError(
            "runtime", f"未载入指定 AstrBot 源码: {astrbot.__file__}"
        )
    _write_ci_plugin_config(astrbot_root, plugin_name)
    from astrbot.api.star import Context
    from astrbot.core import AstrBotConfig
    from astrbot.core.star.star_manager import PluginManager

    config = AstrBotConfig(
        config_path=str(astrbot_root / "data" / "cmd_config.json"),
    )
    context = _build_official_context(Context, config)
    # 避免同一解释器内的测试/重复调用复用旧 Web API 列表。
    if isinstance(getattr(Context, "registered_web_apis", None), list):
        Context.registered_web_apis = []
    manager_cls = _tracking_manager_class(PluginManager)
    manager = manager_cls(context, config)
    return LoaderRuntime(context=context, plugin_manager=manager)


def _find_metadata(runtime: LoaderRuntime, plugin_name: str) -> Any | None:
    get_all_stars = getattr(runtime.context, "get_all_stars", None)
    if not callable(get_all_stars):
        raise LoaderCheckError("registration", "官方 Context 缺少 get_all_stars()")
    stars = get_all_stars()
    if stars is None:
        raise LoaderCheckError("registration", "官方 loader 未返回 Star registry")
    for metadata in reversed(tuple(stars)):
        if (
            getattr(metadata, "root_dir_name", None) == plugin_name
            or getattr(metadata, "name", None) == plugin_name
        ):
            return metadata
    return None


def _find_loaded_plugin(runtime: LoaderRuntime, plugin_name: str) -> Any | None:
    if runtime.loaded_plugin is not None:
        return runtime.loaded_plugin

    metadata = _find_metadata(runtime, plugin_name)
    if metadata is not None:
        plugin = getattr(metadata, "star_cls", None)
        if plugin is not None:
            return plugin

    manager = runtime.plugin_manager
    for captured_metadata in getattr(manager, "captured_metadata", ()):
        if (
            getattr(captured_metadata, "root_dir_name", None) == plugin_name
            or getattr(captured_metadata, "name", None) == plugin_name
        ):
            plugin = getattr(captured_metadata, "star_cls", None)
            if plugin is not None:
                return plugin
    for attribute in ("captured_plugin", "loaded_plugin", "plugin"):
        plugin = getattr(manager, attribute, None)
        if plugin is not None:
            return plugin
    return None


def _validate_command_registration(
    staged_plugin: Path, metadata: Any
) -> tuple[int, int]:
    """通过官方 registry 确认本插件的命令实际注册。"""
    module_file = Path(metadata.module.__file__).resolve()
    if module_file.parent != staged_plugin:
        raise LoaderCheckError(
            "registration", f"载入了 staging 之外的插件: {module_file}"
        )
    handlers = tuple(getattr(metadata, "star_handler_full_names", ()) or ())
    cfg = metadata.star_cls._plugin_config
    general = cfg["setu_general"]
    expected = set()
    if general["natural_language_enabled"]:
        expected.add("regex_command")
    if general["commands_enabled"]:
        expected.update({"setu_command", "random_doujinshi_command"})
        if cfg["fortune"]["enabled"]:
            expected.update(
                {
                    "fortune_command",
                    "fortune_refresh_command",
                    "fortune_refresh_all_command",
                    "preference",
                    "preference_show",
                    "preference_theme",
                    "preference_tags",
                    "preference_reset_theme",
                    "preference_reset_tags",
                }
            )
    expected_names = {f"{metadata.module_path}_{name}" for name in expected}
    if set(handlers) != expected_names:
        raise LoaderCheckError(
            "registration",
            f"handler 注册不符: expected={sorted(expected_names)}, actual={sorted(handlers)}",
        )
    return len(expected - {"regex_command"}), len(handlers)


def _infer_phase_from_traceback_text(default_phase: str, error_trace: str) -> str:
    if default_phase == "load" and re.search(r", in _?initialize\b", error_trace):
        return "initialize"
    return default_phase


def _official_load_failure(
    runtime: LoaderRuntime,
    plugin_name: str,
    detail: object,
) -> LoaderCheckError:
    """保留官方 loader 捕获的原始失败记录，而不是把它降级为空错误。"""

    record: Mapping[str, object] | None = None
    records = getattr(runtime.plugin_manager, "failed_plugin_dict", None)
    if isinstance(records, Mapping):
        candidate = records.get(plugin_name)
        if isinstance(candidate, Mapping):
            record = candidate

    error_text = record.get("error") if record is not None else None
    traceback_text = record.get("traceback") if record is not None else None
    phase = _infer_phase_from_traceback_text(
        "load",
        traceback_text if isinstance(traceback_text, str) else "",
    )
    details = ["official loader returned failure"]
    if isinstance(error_text, str) and error_text.strip():
        details.append(f"plugin error: {error_text}")
    if detail is not None and str(detail).strip():
        details.append(f"loader detail: {detail}")
    if isinstance(traceback_text, str) and traceback_text.strip():
        details.append(f"official traceback:\n{traceback_text}")
    return LoaderCheckError(phase, "\n".join(details))


def _await_if_needed(value: _T | Awaitable[_T]) -> Awaitable[_T]:
    if inspect.isawaitable(value):
        return value

    async def _resolved() -> _T:
        return value

    return _resolved()


def _infer_phase(default_phase: str, error: BaseException) -> str:
    if default_phase == "load":
        for frame in traceback.extract_tb(error.__traceback__):
            if frame.name in {"initialize", "_initialize"}:
                return "initialize"
    return default_phase


def _wrap_error(default_phase: str, error: BaseException) -> LoaderCheckError:
    if isinstance(error, LoaderCheckError):
        return error
    phase = _infer_phase(default_phase, error)
    wrapped = LoaderCheckError(
        phase,
        f"{type(error).__name__}: {error}",
    )
    wrapped.__cause__ = error
    return wrapped


def _append_error_note(target: BaseException, phase: str, error: BaseException) -> None:
    target.add_note(
        f"cleanup phase={phase} failed: {type(error).__name__}: {error}\n"
        + "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )


def _git_commit(plugin_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(plugin_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = result.stdout.strip()
    return commit or "unavailable"


def _sensitive_environment_values() -> tuple[str, ...]:
    values = {
        value
        for name, value in os.environ.items()
        if _SENSITIVE_ENV_NAME_RE.search(name) and len(value) >= 4
    }
    return tuple(sorted(values, key=len, reverse=True))


def _redact_sensitive_text(text: str) -> str:
    """在 CI 错误上下文中遮蔽常见凭据形态和当前环境中的敏感值。"""

    redacted = _COOKIE_HEADER_RE.sub("[REDACTED-COOKIE]", text)
    redacted = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", redacted)
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", redacted)
    redacted = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('prefix')}[REDACTED]",
        redacted,
    )
    redacted = _TOKEN_SHAPED_RE.sub("[REDACTED-TOKEN]", redacted)
    for value in _sensitive_environment_values():
        redacted = redacted.replace(value, "[REDACTED-ENV]")
    return redacted


def _format_failure(
    error: BaseException,
    *,
    astrbot_version: str,
    plugin_name: str,
    plugin_dir: Path,
) -> str:
    phase = getattr(error, "phase", "unknown")
    lines = [
        f"phase: {phase}",
        f"error_type: {type(error).__name__}",
        f"error: {error}",
        f"astrbot_version: {astrbot_version}",
        f"plugin: {plugin_name}",
        f"commit: {_git_commit(plugin_dir)}",
        "full traceback:",
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    ]
    return _redact_sensitive_text("\n".join(lines))


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """一次运行时快照；对象身份用于区分本轮 lifecycle 新增的资源。"""

    handlers: tuple[object, ...] = ()
    tools: tuple[object, ...] = ()
    web_apis: tuple[object, ...] = ()
    tasks: tuple[asyncio.Task[Any], ...] = ()


@dataclass(slots=True)
class LoaderRuntime:
    """官方 Context/PluginManager、运行时快照和 harness 清理回调。"""

    context: Any
    plugin_manager: Any
    loaded_plugin: Any | None = None
    cleanup_callbacks: tuple[Callable[[], object], ...] = ()
    snapshot_state: Callable[[], RuntimeSnapshot] | None = None


@dataclass(frozen=True, slots=True)
class LoaderReport:
    """一次 lifecycle 检查的可审计结果。"""

    astrbot_version: str
    plugin_name: str
    plugin_version: str
    load_succeeded: bool
    initialize_succeeded: bool
    terminate_succeeded: bool
    unbind_succeeded: bool
    resource_cleanup_succeeded: bool
    command_count: int
    handler_count: int
    registered_handler_count: int
    registered_tool_count: int
    registered_web_api_count: int
    background_task_count: int


def _build_official_runtime(
    astrbot_source: Path,
    astrbot_version: str,
    astrbot_root: Path,
    plugin_name: str,
) -> LoaderRuntime:
    base_runtime = _build_base_runtime(
        astrbot_source,
        astrbot_version,
        astrbot_root,
        plugin_name,
    )

    # 使用 AstrBot 的全局工具 registry，让注册与卸载检查观察到同一份状态。
    from astrbot.core.provider.register import llm_tools
    from astrbot.core.star.star_handler import star_handlers_registry

    provider_manager = getattr(base_runtime.context, "provider_manager", None)
    if provider_manager is None:
        base_runtime.context.provider_manager = SimpleNamespace(llm_tools=llm_tools)
    elif getattr(provider_manager, "llm_tools", None) is None:
        provider_manager.llm_tools = llm_tools

    def snapshot_state() -> RuntimeSnapshot:
        web_apis = tuple(getattr(base_runtime.context, "registered_web_apis", ()))
        pending_tasks = tuple(task for task in asyncio.all_tasks() if not task.done())
        return RuntimeSnapshot(
            handlers=tuple(star_handlers_registry),
            tools=tuple(llm_tools.func_list),
            web_apis=web_apis,
            tasks=pending_tasks,
        )

    return LoaderRuntime(
        context=base_runtime.context,
        plugin_manager=base_runtime.plugin_manager,
        loaded_plugin=base_runtime.loaded_plugin,
        cleanup_callbacks=base_runtime.cleanup_callbacks,
        snapshot_state=snapshot_state,
    )


def _added(before: tuple[object, ...], after: tuple[object, ...]) -> tuple[object, ...]:
    before_ids = {id(item) for item in before}
    return tuple(item for item in after if id(item) not in before_ids)


def _delta(before: RuntimeSnapshot, after: RuntimeSnapshot) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        handlers=_added(before.handlers, after.handlers),
        tools=_added(before.tools, after.tools),
        web_apis=_added(before.web_apis, after.web_apis),
        tasks=tuple(
            task
            for task in _added(before.tasks, after.tasks)
            if isinstance(task, asyncio.Task) and not task.done()
        ),
    )


def _describe_handler(handler: object) -> str:
    for attribute in ("handler_name", "full_name", "name"):
        value = getattr(handler, attribute, None)
        if isinstance(value, str) and value:
            return value
    return type(handler).__name__


def _describe_tool(tool: object) -> str:
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) and name else type(tool).__name__


def _describe_web_api(api: object) -> str:
    if isinstance(api, tuple) and api:
        route = api[0]
        methods = api[2] if len(api) > 2 else None
        return f"{route!s} {methods!s}"
    return type(api).__name__


def _describe_task(task: asyncio.Task[Any]) -> str:
    name = task.get_name()
    coro = task.get_coro()
    code = getattr(coro, "cr_code", None)
    if code is not None:
        return f"{name}: {code.co_qualname} ({code.co_filename}:{code.co_firstlineno})"
    return f"{name}: {coro!r}"


def _format_items(items: tuple[object, ...], formatter: Callable[[object], str]) -> str:
    return ", ".join(formatter(item) for item in items)


def _assert_registration_is_observable(added: RuntimeSnapshot, config) -> None:
    """防止 lifecycle 检查在没有实际覆盖注册动作时假绿。"""

    missing: list[str] = []
    expected_tools = {
        "get_setu_image",
        "get_today_fortune",
        "refresh_my_fortune",
        "refresh_group_fortune",
        "refresh_all_fortune",
    }
    if not config["setu_general"]["llm_tools_enabled"]:
        expected_tools = set()
    elif not config["fortune"]["enabled"]:
        expected_tools = {"get_setu_image"}
    tools = {_describe_tool(tool) for tool in added.tools}
    if tools != expected_tools:
        missing.append(
            f"tools: expected={sorted(expected_tools)}, actual={sorted(tools)}"
        )
    if added.web_apis:
        raise LoaderCheckError("registration", "插件不应注册已删除的 Pages API")
    if missing:
        raise LoaderCheckError(
            "registration",
            "lifecycle 没有观察到预期的运行时注册: " + ", ".join(missing),
        )


def _assert_no_runtime_residue(
    baseline: RuntimeSnapshot, final: RuntimeSnapshot
) -> None:
    residue = _delta(baseline, final)
    details: list[str] = []
    if residue.handlers:
        details.append("handlers=" + _format_items(residue.handlers, _describe_handler))
    if residue.tools:
        details.append("tools=" + _format_items(residue.tools, _describe_tool))
    if residue.web_apis:
        details.append("web_apis=" + _format_items(residue.web_apis, _describe_web_api))
    if residue.tasks:
        details.append(
            "tasks=" + ", ".join(_describe_task(task) for task in residue.tasks)
        )
    if details:
        raise LoaderCheckError(
            "resource cleanup",
            "插件卸载后仍存在本轮 lifecycle 新增的运行时资源: " + "; ".join(details),
        )


async def run_loader_check(
    *,
    astrbot_source: str | Path,
    astrbot_version: str,
    plugin_dir: str | Path,
    astrbot_root: str | Path,
    plugin_name: str,
    config: dict[str, Any] | None = None,
    reload_config: dict[str, Any] | None = None,
    runtime_factory: Callable[..., LoaderRuntime | Awaitable[LoaderRuntime]]
    | None = None,
) -> LoaderReport:
    """执行 load → official terminate/unbind → residue check。"""

    source = Path(astrbot_source).expanduser().resolve()
    plugin = Path(plugin_dir).expanduser().resolve()
    root = Path(astrbot_root).expanduser().resolve()
    if not isinstance(astrbot_version, str) or not astrbot_version.strip():
        raise ValueError("AstrBot 版本标识不能为空")
    _validate_plugin_name(plugin_name)
    if not source.is_dir():
        raise ValueError(f"AstrBot 源码目录不存在或不是目录: {source}")

    root_was_present = root.exists()
    staged_plugin: Path | None = None
    runtime: LoaderRuntime | None = None
    metadata: Any | None = None
    loaded_plugin: Any | None = None
    baseline: RuntimeSnapshot | None = None
    report: LoaderReport | None = None
    failure: LoaderCheckError | None = None
    cleanup_errors: list[tuple[str, BaseException]] = []
    terminate_succeeded = False
    unbind_succeeded = False
    resource_cleanup_succeeded = False
    phase = "setup"
    previous_root = os.environ.get("ASTRBOT_ROOT")
    previous_reload = os.environ.get("ASTRBOT_RELOAD")
    inserted_paths: list[str] = []

    try:
        os.environ["ASTRBOT_ROOT"] = str(root)
        os.environ["ASTRBOT_RELOAD"] = "0"

        phase = "staging"
        staged_plugin = stage_plugin(
            plugin_dir=plugin,
            astrbot_root=root,
            plugin_name=plugin_name,
        )
        if config is not None:
            config_path = root / "data" / "config" / f"{plugin_name}_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, ensure_ascii=False))
        plugin_version, _plugin_astrbot_spec = _read_plugin_metadata(
            staged_plugin,
            plugin_name,
        )
        inserted_paths = _prepend_sys_path(source, root)

        phase = "runtime"
        factory = runtime_factory or _build_official_runtime
        runtime = await _await_if_needed(
            factory(source, astrbot_version, root, plugin_name),
        )
        if not isinstance(runtime, LoaderRuntime):
            raise TypeError("runtime_factory 必须返回 LoaderRuntime")
        if not callable(runtime.snapshot_state):
            raise TypeError("LoaderRuntime 必须提供 snapshot_state()")
        baseline = runtime.snapshot_state()

        phase = "load"
        load_result = await _await_if_needed(
            runtime.plugin_manager.load(specified_dir_name=plugin_name),
        )
        if not isinstance(load_result, tuple) or not load_result:
            raise TypeError(
                "官方 PluginManager.load() 返回值不是 (success, error) 元组"
            )
        if not bool(load_result[0]):
            detail = load_result[1] if len(load_result) > 1 else None
            raise _official_load_failure(runtime, plugin_name, detail)

        phase = "registration"
        metadata = _find_metadata(runtime, plugin_name)
        if metadata is None:
            raise LoaderCheckError(
                "registration",
                f"official loader 成功返回，但未发现已注册插件 {plugin_name}",
            )
        loaded_plugin = getattr(metadata, "star_cls", None)
        if loaded_plugin is None:
            raise LoaderCheckError("instantiation", f"插件 {plugin_name} 没有可用实例")
        initialize = getattr(loaded_plugin, "initialize", None)
        if not callable(initialize):
            raise LoaderCheckError("initialize", "插件实例没有 initialize()")

        command_count, handler_count = _validate_command_registration(
            staged_plugin,
            metadata,
        )
        loaded_snapshot = runtime.snapshot_state()
        registered = _delta(baseline, loaded_snapshot)
        _assert_registration_is_observable(registered, loaded_plugin._plugin_config)

        if reload_config is not None:
            config_path = root / "data" / "config" / f"{plugin_name}_config.json"
            config_path.write_text(json.dumps(reload_config, ensure_ascii=False))
            phase = "reload"
            success, detail = await runtime.plugin_manager.reload(
                specified_plugin_name=plugin_name
            )
            if not success:
                raise _official_load_failure(runtime, plugin_name, detail)
            metadata = _find_metadata(runtime, plugin_name)
            loaded_plugin = metadata.star_cls
            command_count, handler_count = _validate_command_registration(
                staged_plugin, metadata
            )
            registered = _delta(baseline, runtime.snapshot_state())
            _assert_registration_is_observable(registered, loaded_plugin._plugin_config)

        report = LoaderReport(
            astrbot_version=astrbot_version,
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            load_succeeded=True,
            initialize_succeeded=True,
            terminate_succeeded=False,
            unbind_succeeded=False,
            resource_cleanup_succeeded=False,
            command_count=command_count,
            handler_count=handler_count,
            registered_handler_count=len(registered.handlers),
            registered_tool_count=len(registered.tools),
            registered_web_api_count=len(registered.web_apis),
            background_task_count=len(registered.tasks),
        )
    except _CATCHABLE_ERRORS as error:
        failure = _wrap_error(phase, error)
    finally:
        if runtime is not None:
            if metadata is None:
                try:
                    metadata = _find_metadata(runtime, plugin_name)
                except _CATCHABLE_ERRORS as error:
                    cleanup_errors.append(("registration", error))

            # 只有 load 已经形成完整报告时，才声明必须完成官方卸载契约；失败加载
            # 仍保留旧 harness 的 best-effort terminate，避免覆盖真正的加载错误。
            if report is not None and metadata is not None:
                try:
                    terminate = getattr(
                        runtime.plugin_manager, "_terminate_plugin", None
                    )
                    if not callable(terminate):
                        raise TypeError("官方 PluginManager 缺少 _terminate_plugin()")
                    await _await_if_needed(terminate(metadata))
                    terminate_succeeded = True
                except _CATCHABLE_ERRORS as error:
                    cleanup_errors.append(("terminate", error))

                try:
                    module_path = getattr(metadata, "module_path", None)
                    if not isinstance(module_path, str) or not module_path:
                        raise TypeError(
                            "插件 metadata 缺少 module_path，无法执行官方 unbind"
                        )
                    unbind = getattr(runtime.plugin_manager, "_unbind_plugin", None)
                    if not callable(unbind):
                        raise TypeError("官方 PluginManager 缺少 _unbind_plugin()")
                    await _await_if_needed(
                        unbind(
                            getattr(metadata, "name", None) or plugin_name, module_path
                        ),
                    )
                    unbind_succeeded = True
                except _CATCHABLE_ERRORS as error:
                    cleanup_errors.append(("unbind", error))

                if baseline is not None and callable(runtime.snapshot_state):
                    try:
                        _assert_no_runtime_residue(baseline, runtime.snapshot_state())
                        resource_cleanup_succeeded = True
                    except _CATCHABLE_ERRORS as error:
                        cleanup_errors.append(("resource cleanup", error))
            else:
                if loaded_plugin is None:
                    try:
                        loaded_plugin = _find_loaded_plugin(runtime, plugin_name)
                    except _CATCHABLE_ERRORS as error:
                        cleanup_errors.append(("registration", error))
                if loaded_plugin is not None:
                    try:
                        terminate = getattr(loaded_plugin, "terminate", None)
                        if not callable(terminate):
                            raise TypeError("插件实例没有 terminate()")
                        await _await_if_needed(terminate())
                    except _CATCHABLE_ERRORS as error:
                        cleanup_errors.append(("terminate", error))

            for callback in reversed(runtime.cleanup_callbacks):
                try:
                    await _await_if_needed(callback())
                except _CATCHABLE_ERRORS as error:
                    cleanup_errors.append(("runtime cleanup", error))

        if not root_was_present and root.exists():
            try:
                shutil.rmtree(root)
            except _CATCHABLE_ERRORS as error:
                cleanup_errors.append(("temporary root cleanup", error))

        _remove_sys_path(inserted_paths)
        if previous_root is None:
            os.environ.pop("ASTRBOT_ROOT", None)
        else:
            os.environ["ASTRBOT_ROOT"] = previous_root
        if previous_reload is None:
            os.environ.pop("ASTRBOT_RELOAD", None)
        else:
            os.environ["ASTRBOT_RELOAD"] = previous_reload

    if failure is not None:
        for cleanup_phase, error in cleanup_errors:
            _append_error_note(failure, cleanup_phase, error)
        raise failure
    if cleanup_errors:
        cleanup_phase, first_error = cleanup_errors[0]
        cleanup_failure = _wrap_error(cleanup_phase, first_error)
        for extra_phase, error in cleanup_errors[1:]:
            _append_error_note(cleanup_failure, extra_phase, error)
        raise cleanup_failure
    if report is None:
        raise LoaderCheckError("unknown", "lifecycle 未生成检查报告")

    return replace(
        report,
        terminate_succeeded=terminate_succeeded,
        unbind_succeeded=unbind_succeeded,
        resource_cleanup_succeeded=resource_cleanup_succeeded,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用官方 AstrBot PluginManager 检查插件完整生命周期",
    )
    parser.add_argument("--astrbot-source", required=True, help="官方 AstrBot 源码目录")
    parser.add_argument(
        "--astrbot-version", required=True, help="被测 AstrBot 版本或 ref"
    )
    parser.add_argument("--plugin-dir", required=True, help="当前插件源码目录")
    parser.add_argument("--astrbot-root", required=True, help="临时 ASTRBOT_ROOT")
    parser.add_argument("--plugin-name", required=True, help="插件目录名")
    parser.add_argument("--config", help="合成插件配置 JSON 文件，仅用于生命周期检查")
    parser.add_argument(
        "--reload-config", help="首次注册检查后写入此合成配置并执行官方重载"
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    plugin_dir = Path(args.plugin_dir).expanduser().resolve()
    try:
        report = asyncio.run(
            run_loader_check(
                astrbot_source=args.astrbot_source,
                astrbot_version=args.astrbot_version,
                plugin_dir=plugin_dir,
                astrbot_root=args.astrbot_root,
                plugin_name=args.plugin_name,
                config=json.loads(Path(args.config).read_text())
                if args.config
                else None,
                reload_config=json.loads(Path(args.reload_config).read_text())
                if args.reload_config
                else None,
            ),
        )
    except _CATCHABLE_ERRORS as error:
        # 复用旧 harness 的完整 traceback + 凭据脱敏输出。
        print(
            _format_failure(
                error,
                astrbot_version=args.astrbot_version,
                plugin_name=args.plugin_name,
                plugin_dir=plugin_dir,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        "AstrBot plugin lifecycle passed: "
        f"astrbot={report.astrbot_version}, "
        f"plugin={report.plugin_name}@{report.plugin_version}, "
        f"commands={report.command_count}, handlers={report.registered_handler_count}, "
        f"tools={report.registered_tool_count}, web_apis={report.registered_web_api_count}, "
        f"background_tasks={report.background_task_count}, "
        "terminate=ok, unbind=ok, cleanup=ok"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
