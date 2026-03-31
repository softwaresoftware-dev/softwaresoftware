"""Tests for registry.py — marketplace and plugin reading."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import registry


def test_get_installed_plugins_empty(mock_home):
    assert registry.get_installed_plugins() == {}


def test_get_installed_plugins(mock_home, installed_plugins):
    result = registry.get_installed_plugins()
    assert "notify-linux@nov-plugins" in result


def test_get_marketplace_plugins(mock_home, marketplace_json):
    plugins = registry.get_marketplace_plugins()
    assert len(plugins) == 8
    names = [p["name"] for p in plugins]
    assert "cardwatch" in names
    assert "notify-linux" in names


def test_get_marketplace_plugins_missing(mock_home):
    assert registry.get_marketplace_plugins("nonexistent") == []


def test_find_marketplace_plugin(mock_home, marketplace_json):
    plugin = registry.find_marketplace_plugin("cardwatch")
    assert plugin is not None
    assert plugin["name"] == "cardwatch"
    assert plugin["requires"] == ["notification"]


def test_find_marketplace_plugin_missing(mock_home, marketplace_json):
    assert registry.find_marketplace_plugin("nonexistent") is None


def test_get_providers(mock_home, marketplace_json):
    providers = registry.get_providers("notification")
    assert len(providers) == 2
    names = [p["name"] for p in providers]
    assert "notify-linux" in names
    assert "notify-macos" in names


def test_get_providers_none(mock_home, marketplace_json):
    assert registry.get_providers("nonexistent") == []


def test_is_plugin_installed(mock_home, installed_plugins):
    assert registry.is_plugin_installed("notify-linux") is True
    assert registry.is_plugin_installed("cardwatch") is False


def test_get_plugin_manifest(mock_home, installed_plugins):
    manifest = registry.get_plugin_manifest("notify-linux@nov-plugins")
    assert manifest is not None
    assert manifest["name"] == "notify-linux"
    assert "notify-linux" in manifest["mcpServers"]


def test_get_plugin_manifest_missing(mock_home):
    assert registry.get_plugin_manifest("nonexistent@nov-plugins") is None


def test_get_enabled_plugins(mock_home):
    settings_path = mock_home / ".claude" / "settings.json"
    settings_path.write_text(json.dumps({
        "enabledPlugins": {"liteframe@nov-plugins": True}
    }))
    result = registry.get_enabled_plugins()
    assert result == {"liteframe@nov-plugins": True}
