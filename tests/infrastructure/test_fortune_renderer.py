"""Keep user text out of fortune-card HTML markup."""

from astrbot_plugin_setu.src.infrastructure.astrbot.fortune_renderer import (  # type: ignore[import-not-found]
    FortuneRenderer,
)
from jinja2 import Template  # type: ignore[import-untyped,import-not-found]


def test_user_text_is_escaped_in_local_and_t2i_templates():
    fortune = {
        "username": "<img src=x>",
        "description": "<script>alert(1)</script>",
        "extra_message": "<iframe src=x></iframe>",
        "star_count": 3,
        "max_stars": 7,
        "title": "小吉",
        "date_str": "2026-10-29",
        "theme_color": "theme-gray",
    }
    for card_theme, marker in (
        ("endfield", "endfield-dossier"),
        ("blue_archive", "ba-shittim-card"),
        ("persona_5", "p5-fortune-card"),
        ("default", "kivotos-shard-card"),
    ):
        renderer = FortuneRenderer(card_theme=card_theme)
        data = renderer.build_template_data(fortune)
        t2i_html = Template(renderer._get_template()).render(**data)

        for html in (renderer.render(fortune), t2i_html):
            assert marker in html
            assert "<img src=x>" not in html
            assert "<script>alert(1)</script>" not in html
            assert "<iframe src=x>" not in html
            if "username" in data:
                assert "&lt;img src=x&gt;" in html
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
            assert "&lt;iframe src=x&gt;&lt;/iframe&gt;" in html
            assert html.count('<span class="star-glyph">') == 3


def test_random_card_theme_selects_new_templates():
    renderer = FortuneRenderer(card_theme="random")
    html = renderer.render(
        {
            "username": "Sensei",
            "star_count": 5,
            "max_stars": 7,
            "title": "吉",
            "date_str": "2026-10-29",
            "description": "好运",
            "extra_message": "",
            "theme_color": "theme-gray",
        }
    )
    assert (
        ("endfield-dossier" in html)
        or ("ba-shittim-card" in html)
        or ("p5-fortune-card" in html)
    )
