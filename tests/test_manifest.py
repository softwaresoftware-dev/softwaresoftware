"""Tests for plugin manifest — required fields and version consistency."""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))


def _read_json(path):
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def plugin_json():
    return _read_json(os.path.join(ROOT, ".claude-plugin", "plugin.json"))


@pytest.fixture
def pyproject():
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


def test_required_fields(plugin_json):
    for field in ["name", "description", "version", "author", "keywords"]:
        assert field in plugin_json, f"Missing required field: {field}"


def test_name(plugin_json):
    assert plugin_json["name"] == "softwaresoftware"


def test_semver(plugin_json):
    assert re.match(r"^\d+\.\d+\.\d+$", plugin_json["version"])


def test_version_matches_pyproject(plugin_json, pyproject):
    assert plugin_json["version"] == pyproject["project"]["version"]


def test_mcp_server_config(plugin_json):
    assert "mcpServers" in plugin_json
    assert "softwaresoftware" in plugin_json["mcpServers"]
    server = plugin_json["mcpServers"]["softwaresoftware"]
    assert server["command"] == "uv"
    assert server["args"][:3] == ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}"]
    assert "server.py" in server["args"]


def test_author(plugin_json):
    assert plugin_json["author"]["name"] == "Thatcher"


# --- userConfig schema validation (added to prevent regressions like the
# `enum` field in claude-browser-bridge 3.3.0 that broke install). Schema:
# https://code.claude.com/docs/en/plugins-reference.md#user-configuration ---

import json as _json
import os as _os

USER_CONFIG_COMMON_KEYS = {"type", "title", "description", "default", "required", "sensitive"}
USER_CONFIG_TYPE_KEYS = {
    "string": USER_CONFIG_COMMON_KEYS | {"multiple"},
    "number": USER_CONFIG_COMMON_KEYS | {"min", "max"},
    "boolean": USER_CONFIG_COMMON_KEYS,
    "directory": USER_CONFIG_COMMON_KEYS,
    "file": USER_CONFIG_COMMON_KEYS,
}


def _load_manifest_for_uc():
    root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    with open(_os.path.join(root, ".claude-plugin", "plugin.json")) as f:
        return _json.load(f)


def test_user_config_types():
    """Every userConfig entry must declare a recognized type."""
    plugin_json = _load_manifest_for_uc()
    for name, entry in plugin_json.get("userConfig", {}).items():
        assert "type" in entry, f"userConfig.{name} missing 'type'"
        assert entry["type"] in USER_CONFIG_TYPE_KEYS, (
            f"userConfig.{name}.type={entry['type']!r} is not a recognized "
            f"type. Valid: {sorted(USER_CONFIG_TYPE_KEYS)}"
        )


def test_user_config_schema_strict():
    """userConfig entries must only use keys from the official schema.

    Catches regressions like an `enum` field — the Claude Code manifest schema
    does not support `enum`, `pattern`, or arbitrary JSON Schema keywords.
    """
    plugin_json = _load_manifest_for_uc()
    for name, entry in plugin_json.get("userConfig", {}).items():
        allowed = USER_CONFIG_TYPE_KEYS.get(entry.get("type"), USER_CONFIG_COMMON_KEYS)
        unknown = set(entry.keys()) - allowed
        assert not unknown, (
            f"userConfig.{name} contains unknown keys: {sorted(unknown)}. "
            f"Allowed for type={entry.get('type')!r}: {sorted(allowed)}. "
            f"See https://code.claude.com/docs/en/plugins-reference.md#user-configuration"
        )
