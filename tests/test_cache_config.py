import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest


def test_shared_cache_capacity_and_leases(tmp_path, load):
    Cache = load("src.shared.cache").Cache
    cache = Cache(tmp_path, limit=16)
    held = tmp_path / "setu" / "held"
    cache.pin(held)
    cache.write(held, b"12345678")
    with pytest.raises(OSError, match="空间不足"):
        cache.write(tmp_path / "doujinshi" / "large", b"x" * 17)
    assert held.read_bytes() == b"12345678"
    assert not (tmp_path / "doujinshi" / "large").exists()

    def write(i):
        try:
            cache.write(tmp_path / "fortune" / str(i), b"x" * 8)
        except OSError as exc:
            assert "空间不足" in str(exc)

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(write, range(6)))
    assert sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file()) <= 16
    cache.remove(held)
    assert held.exists()
    cache.release(held, keep=True)
    assert not held.exists()


@pytest.mark.asyncio
async def test_concurrent_same_url_cache(tmp_path, load):
    cache = load("src.shared.cache").init_cache(tmp_path / "cache")
    disk = await load("src.shared.send_cache").init_send_cache(tmp_path, enabled=True)
    first, second = await asyncio.gather(
        disk.reserve("https://image/a.png"), disk.reserve("https://image/a.png")
    )
    assert first.temp_path != second.temp_path
    cache.write(first.temp_path, b"abc")
    cache.write(second.temp_path, b"def")
    paths = await asyncio.gather(disk.commit(first), disk.commit(second))
    assert paths[0] == paths[1]
    assert paths[0].read_bytes() == b"abc"
    cache.release(paths[0], keep=True)
    cache.release(paths[1], keep=True)
    assert not cache.active


def test_invalid_template_types_and_duplicate_entries_preserve_valid_values(load):
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text()
    )
    heal = load("src.infrastructure.config").heal_astrbot_plugin_config
    config, _ = heal(
        {
            "safety": [
                {"__template_key": []},
                {
                    "__template_key": "setu",
                    "mode": "blacklist",
                    "blocked_sids": ["p:GroupMessage:g"],
                },
                {"__template_key": "setu", "mode": "none"},
            ],
            "session_configs": [
                {"__template_key": "fortune", "session_id": []},
                {
                    "__template_key": "fortune",
                    "session_id": "p:GroupMessage:g",
                    "tags": "猫耳",
                },
            ],
        },
        schema,
    )
    assert config["safety"][0]["blocked_sids"] == ["p:GroupMessage:g"]
    assert len(config["safety"]) == 1
    assert config["session_configs"][0]["tags"] == "猫耳"


def test_custom_api_survives_save_reload(load):
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text()
    )
    heal = load("src.infrastructure.config").heal_astrbot_plugin_config
    providers = load("src.infrastructure.providers")
    Config = load("src.shared.config.models").SetuPluginConfig
    cleaned, _ = heal(
        {
            "setu_general": {"api_type": "custom"},
            "fortune": {"tags": ""},
            "api": {
                "custom_api_configs": [
                    {"__template_key": "api_template", "url": "  "},
                    {
                        "__template_key": "api_template",
                        "url": "https://example.org/images",
                        "parser_type": "json",
                        "json_path": " ",
                    },
                    {
                        "__template_key": "api_template",
                        "url": "https://example.org/images",
                        "timeout": 0,
                        "method": "",
                        "parser_type": "",
                    },
                ]
            },
        },
        schema,
    )
    assert len(cleaned["api"]["custom_api_configs"]) == 1
    api = cleaned["api"]["custom_api_configs"][0]
    assert api["__template_key"] == "api_template"
    assert (api["timeout"], api["method"], api["parser_type"]) == (30, "GET", "auto")
    assert cleaned["fortune"]["tags"] == ""
    assert cleaned["setu_general"]["api_type"] == "custom"
    assert heal(json.loads(json.dumps(cleaned)), schema) == (cleaned, [])
    providers.init_provider_from_config(Config.model_validate(cleaned))
    providers.clear_provider()
