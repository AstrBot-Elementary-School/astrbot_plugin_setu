"""Feature regressions runnable without AstrBot: python tests/test_feature_switches.py.

Execute the production entry-point definitions with isolated dependencies so
disabled features can be verified without initializing a bot or network client.
Pydantic v2 is required for the real configuration model.
"""

from __future__ import annotations

import ast
import json
import re
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
MODELS = runpy.run_path(str(ROOT / "src/shared/config/models.py"))
Config = MODELS["SetuPluginConfig"]


def definitions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        )
    ]
    nodes += [node for node in tree.body if getattr(node, "name", None) in names]
    exec(  # noqa: S102
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
            path,
            "exec",
        ),
        namespace,
    )
    return namespace


class FeatureSwitchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = Config()
        path = "src/infrastructure/astrbot/feature_switches.py"
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        tree.body = [
            n for n in tree.body if not (isinstance(n, ast.ImportFrom) and n.level)
        ]
        self.namespace = {"get_config": lambda: self.config}
        exec(compile(tree, path, "exec"), self.namespace)  # noqa: S102
        self.event = SimpleNamespace(plain_result=lambda text: text)

    def handler(self, name):
        return definitions(
            f"src/infrastructure/astrbot/commands/{name}.py",
            {
                "setu": ["SetuCommandHandler"],
                "fortune": ["FortuneCommandHandler"],
                "session_config": ["SessionConfigCommandHandler"],
            }[name],
            dict(self.namespace),
        )[
            {
                "setu": "SetuCommandHandler",
                "fortune": "FortuneCommandHandler",
                "session_config": "SessionConfigCommandHandler",
            }[name]
        ]

    def test_schema_defaults_match_model(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        for section, field in [
            ("doujinshi", "enabled"),
            ("llm_tools", "enabled"),
            ("triggers", "natural_language_enabled"),
            ("fortune", "enabled"),
        ]:
            with self.subTest(section=section):
                self.assertTrue(getattr(getattr(self.config, section), field))
                self.assertEqual(
                    schema[section]["items"][field]["default"],
                    getattr(getattr(self.config, section), field),
                )

    async def test_doujinshi_disabled_before_request_lock(self):
        self.config.doujinshi.enabled = False
        cls = self.handler("setu")
        instance = object.__new__(cls)
        results = [x async for x in instance.random_doujinshi_command(self.event)]
        self.assertEqual(
            results,
            [self.config.resolve_message("feature_disabled", feature="随机本子")],
        )

    async def test_all_fortune_entry_points_disabled(self):
        self.config.fortune.enabled = False
        cls = self.handler("fortune")
        instance = object.__new__(cls)
        expected = self.config.resolve_message("feature_disabled", feature="今日运势")
        for name in cls.__dict__:
            if name.endswith("_command") or name.startswith("_llm_"):
                with self.subTest(entry=name):
                    result = getattr(instance, name)(self.event)
                    if name.startswith("_llm_"):
                        self.assertEqual(await result, expected)
                    else:
                        self.assertEqual([x async for x in result], [expected])

    async def test_llm_disabled_blocks_stale_handlers(self):
        self.config.llm_tools.enabled = False
        for module in ["setu", "fortune", "session_config"]:
            cls = self.handler(module)
            instance = object.__new__(cls)
            for name in cls.__dict__:
                if name.startswith("_llm_"):
                    with self.subTest(module=module, entry=name):
                        self.assertEqual(
                            await getattr(instance, name)(self.event),
                            self.config.resolve_message(
                                "feature_disabled", feature="LLM 工具"
                            ),
                        )

    def test_disabled_tools_not_registered(self):
        for module in ["setu", "fortune", "session_config"]:
            with self.subTest(module=module):
                self.config.llm_tools.enabled = False
                ns = dict(self.namespace)
                ns["llm_tools"] = MagicMock()
                definitions(
                    f"src/infrastructure/astrbot/commands/{module}.py",
                    ["register_llm_tools"],
                    ns,
                )
                ns["register_llm_tools"]()
                ns["llm_tools"].add_func.assert_not_called()

    def test_disabled_fortune_skips_tool_registration_and_renderer(self):
        self.config.fortune.enabled = False
        ns = dict(self.namespace)
        ns["llm_tools"] = MagicMock()
        definitions(
            "src/infrastructure/astrbot/commands/fortune.py", ["register_llm_tools"], ns
        )
        ns["register_llm_tools"]()
        ns["llm_tools"].add_func.assert_not_called()
        cls = self.handler("fortune")
        self.assertIsNone(cls()._renderer)

    def test_disabled_doujinshi_skips_service_initialization(self):
        self.config.doujinshi.enabled = False
        cls = self.handler("setu")
        self.assertIsNone(cls(data_dir=ROOT)._doujinshi_service)

    async def test_natural_language_gate_and_enabled_routing(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        names = {
            "SETU_REGEX_PATTERN",
            "DOUJINSHI_REGEX_PATTERN",
            "FORTUNE_REGEX_PATTERN",
        }
        ns = dict(self.namespace, re=re)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) in names for t in node.targets
            ):
                exec(  # noqa: S102
                    compile(
                        ast.Module(body=[node], type_ignores=[]), "main.py", "exec"
                    ),
                    ns,
                )
        definitions("main.py", ["_route_regex_command"], ns)
        calls = []

        async def picture(event):
            calls.append(event.message_str)
            yield "image"

        self.event.message_str = "来一张色图"
        handler = SimpleNamespace(get_random_picture=picture)
        self.config.triggers.natural_language_enabled = False
        self.assertEqual(
            [x async for x in ns["_route_regex_command"](self.event, handler, None)], []
        )
        self.assertEqual(calls, [])
        self.config.triggers.natural_language_enabled = True
        self.assertEqual(
            [x async for x in ns["_route_regex_command"](self.event, handler, None)],
            ["image"],
        )

    async def test_enabled_gate_preserves_arguments_and_results(self):
        @self.namespace["require_feature"]("doujinshi", "随机本子")
        async def action(self, event, tags):
            yield tags

        self.assertEqual([x async for x in action(None, self.event, "tag")], ["tag"])

    async def test_disabled_notice_can_be_silenced(self):
        self.config.doujinshi.enabled = False
        self.config.messages.feature_disabled.enabled = False
        cls = self.handler("setu")
        self.assertEqual(
            [x async for x in object.__new__(cls).random_doujinshi_command(self.event)],
            [],
        )

    async def test_initialization_skips_disabled_features_but_recovers_revokes(self):
        self.config.fortune.enabled = False
        self.config.llm_tools.enabled = False
        ns = dict(self.namespace)
        ns.update(
            init_config=lambda raw: self.config,
            set_plugin_context=MagicMock(),
            StarTools=SimpleNamespace(get_data_dir=lambda name: ROOT),
            Path=Path,
            init_provider_from_config=MagicMock(),
            SetuCommandHandler=MagicMock(),
            FortuneCommandHandler=MagicMock(),
            SessionConfigCommandHandler=MagicMock(),
            logger=MagicMock(),
        )
        for name in [
            "init_access_control_repo",
            "init_fortune_repo",
            "init_session_config_repo",
            "init_send_cache",
            "init_revoke_scheduler",
        ]:
            ns[name] = AsyncMock()
        for name in [
            "register_setu_llm_tools",
            "register_fortune_llm_tools",
            "register_session_config_llm_tools",
        ]:
            ns[name] = MagicMock()
        definitions("main.py", ["_fortune_auto_refresh_enabled"], ns)
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        method = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "initialize"
        )
        method.decorator_list = []
        module = ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__", names=[ast.alias(name="annotations")], level=0
                ),
                method,
            ],
            type_ignores=[],
        )
        exec(compile(ast.fix_missing_locations(module), "main.py", "exec"), ns)  # noqa: S102
        plugin = SimpleNamespace(
            name="setu",
            context=object(),
            _runtime_plugin_config=dict,
            _heal_runtime_plugin_config=lambda raw: raw,
        )
        await ns["initialize"](plugin)
        ns["init_fortune_repo"].assert_not_awaited()
        for name in [
            "register_setu_llm_tools",
            "register_fortune_llm_tools",
            "register_session_config_llm_tools",
        ]:
            ns[name].assert_not_called()
        ns["init_revoke_scheduler"].assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
