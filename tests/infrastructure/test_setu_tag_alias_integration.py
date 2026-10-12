"""标签解析共享辅助函数的集成式测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot_plugin_setu.src.application.setu.tag_resolution import (
    resolve_image_request_tags,
    resolve_user_tag_list,
    resolve_user_tags,
)


@pytest.mark.parametrize(
    ("raw", "expected_tags", "expected_r18"),
    [
        ("", [], False),
        ("girl", ["少女"], False),
        ("r18", [], True),
        ("girl R18", ["少女"], True),
        ("r18,girl，r18、cute", ["少女", "cute"], True),
        ("girlr18 r180", ["girlr18", "r180"], False),
        ("-r18", ["-r18"], False),
        (["blue archive", "r18", "girl"], ["blue archive", "少女"], True),
        (["white hair", "girl"], ["white hair", "少女"], False),
    ],
)
def test_image_request_r18_marker(raw, expected_tags, expected_r18):
    assert resolve_image_request_tags(raw, "少女=girl") == (
        expected_tags,
        expected_r18,
    )


def test_r18_marker_is_reserved_before_alias_resolution():
    assert resolve_image_request_tags("r18", "普通标签=r18") == ([], True)
    # 共用标签解析器仍允许本子将普通标签原样传入。
    assert resolve_user_tags("r18", "") == ["r18"]


class TestSetuTagAliasIntegration:
    """验证色图与本子可共享的标签别名解析。"""

    def test_resolve_tags_uses_configured_alias_map(self) -> None:
        config = SimpleNamespace(tag_alias="二次元=acg,anime")

        resolved = resolve_user_tags("acg cute", config.tag_alias)

        assert resolved == ["二次元", "cute"]

    def test_resolve_tags_from_list_uses_configured_alias_map(self) -> None:
        config = SimpleNamespace(tag_alias="少女=girl")

        resolved = resolve_user_tag_list(["girl", "kawaii"], config.tag_alias)

        assert resolved == ["少女", "kawaii"]

    def test_resolve_tags_from_list_keeps_multi_word_tags(self) -> None:
        config = SimpleNamespace(tag_alias="碧蓝档案=blue archive")

        resolved = resolve_user_tag_list(
            ["blue archive", "white hair"], config.tag_alias
        )

        assert resolved == ["碧蓝档案", "white hair"]
