"""装配主题资源并调用 AstrBot 渲染。"""

import base64
import json
import mimetypes
import random
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import yaml
from jinja2 import Environment, StrictUndefined

THEMES = ("arona", "endfield", "persona5", "minecraft", "minimal")
RENDER_WIDTHS = {
    "arona": 640,
    "endfield": 780,
    "persona5": 828,
    "minecraft": 528,
    "minimal": 488,
}


class FortuneRenderer:
    def __init__(self, card_theme="random"):
        self.card_theme = card_theme
        self.root = Path(__file__).resolve().parents[2] / "template" / "fortune"
        self.aliases = {name: name for name in (*THEMES, "random")}
        self.aliases["随机"] = "random"
        for theme in THEMES:
            path = self.root / theme / "template.yaml"
            aliases = yaml.safe_load(path.read_text(encoding="utf-8"))["aliases"]
            if not isinstance(aliases, list):
                raise TypeError(f"{path} 的 aliases 需要填写字符串数组")
            for alias in aliases:
                if not isinstance(alias, str) or not alias.strip():
                    raise ValueError(f"{path} 中的别名需要填写非空字符串")
                key = alias.strip().casefold()
                if key in self.aliases and self.aliases[key] != theme:
                    raise ValueError(f"主题别名重复：{alias}")
                self.aliases[key] = theme
        self.environment = Environment(autoescape=True, undefined=StrictUndefined)
        self._assets = {}
        self.versions = {}

    def resolve_theme(self, theme):
        key = theme.strip().casefold()
        if key not in self.aliases:
            raise ValueError(
                f"未知运势主题：{theme}。可选主题：{'、'.join((*THEMES, 'random'))}"
            )
        return self.aliases[key]

    def choose_theme(self, theme=None, random_themes=THEMES[:-1]):
        selected = self.resolve_theme(theme or self.card_theme)
        if selected == "random":
            selected = random.choice(random_themes)
        return selected

    def assets(self, theme):
        if theme not in self._assets:
            root = self.root / theme
            css = (root / "index.css").read_text()

            def embed(match):
                name = match.group(1).strip(" \"'")
                if name.startswith(("data:", "https:", "http:", "#")):
                    return match.group(0)
                path = (root / name).resolve()
                data = base64.b64encode(path.read_bytes()).decode()
                return f"url('data:{mimetypes.guess_type(path)[0] or 'application/octet-stream'};base64,{data}')"

            css = re.sub(r"url\(([^)]+)\)", embed, css)
            text = json.loads((root / "text.json").read_text())
            js = (root / "index.js").read_text() if (root / "index.js").exists() else ""
            source = (root / "index.jinja2").read_text()
            template = self.environment.from_string(source)
            self.versions[theme] = uuid5(
                NAMESPACE_URL, source + css + js + json.dumps(text, ensure_ascii=False)
            ).hex
            self._assets[theme] = (template, css, js, text)
        return self._assets[theme]

    def render(self, fortune, image=None, card_theme=None):
        template, css, js, text = self.assets(self.choose_theme(card_theme))
        return template.render(
            username=fortune["username"],
            date_str=fortune["date_str"],
            stars=fortune["stars"],
            image=image,
            css=css,
            js=js,
            text=text,
        )

    def format_text(self, record, theme):
        text = self.assets(theme)[3]
        key = str(record.star_count)
        message = random.choice(text["messages"][key])
        tip = random.choice(text["tip"][key])
        return (
            f"{record.date_str} · {text['titles'][record.star_count]}\n{message}\n{tip}"
        )

    async def render_to_image(self, fortune, image=None, card_theme=None):
        from astrbot.core import html_renderer

        theme = self.choose_theme(card_theme)
        _, css, js, text = self.assets(theme)
        # 让 AstrBot 将脚本注入 <head>，保留 DOCTYPE 的标准渲染模式。
        output = await html_renderer.render_custom_template(
            tmpl_str=(self.root / theme / "index.jinja2").read_text(),
            tmpl_data={
                "username": fortune["username"],
                "date_str": fortune["date_str"],
                "stars": fortune["stars"],
                "image": image,
                "css": css,
                "js": js,
                "text": text,
            },
            return_url=False,
            options={
                "full_page": True,
                "type": "png",
                "scale": "css",
                "omit_background": True,
                "viewport_width": RENDER_WIDTHS[theme],
                "viewport_height": 1,
            },
        )
        return output if isinstance(output, bytes) else Path(output).read_bytes()
