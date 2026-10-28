"""Keep user text out of fortune-card HTML markup."""

from astrbot_plugin_setu.src.infrastructure.astrbot.fortune_renderer import (
    FortuneRenderer,
)
from jinja2 import Template


def test_user_text_is_escaped_in_local_and_t2i_templates():
    renderer = FortuneRenderer()
    fortune = {
        "username": "<img src=x>",
        "description": "<script>alert(1)</script>",
        "extra_message": "<iframe src=x></iframe>",
        "star_count": 3,
    }
    data = renderer.build_template_data(fortune)
    t2i_html = Template(renderer._get_template()).render(**data)

    for html in (renderer.render(fortune), t2i_html):
        assert "<img src=x>" not in html
        assert "<script>alert(1)</script>" not in html
        assert "<iframe src=x>" not in html
        assert "&lt;img src=x&gt;" in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "&lt;iframe src=x&gt;&lt;/iframe&gt;" in html
        assert html.count('<span class="star">') == 3
