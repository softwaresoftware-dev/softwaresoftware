"""Tests for resolver.find_satisfier — runtime capability satisfier lookup.

find_satisfier picks where a capability will be served at spawn time:
locally-installed plugin, loaded third-party MCP, mesh host, or nothing.
Order is preference: local plugin > MCP > host > none. A local satisfier
avoids a cross-host hop, so it always wins when present.
"""

import json
from unittest.mock import patch

import resolver


def test_find_satisfier_picks_installed_plugin(mock_home, marketplace_json, installed_plugins):
    """notify-linux is installed and provides 'notification'."""
    with patch("mesh.list_hosts", return_value=[]):
        result = resolver.find_satisfier("notification")
    assert result["type"] == "plugin"
    assert result["name"] == "notify-linux"


def test_find_satisfier_picks_loaded_mcp_when_no_plugin(mock_home, marketplace_json, monkeypatch):
    """When no plugin is installed, a loaded third-party MCP satisfies."""
    import probes
    monkeypatch.setattr(probes, "probe_mcp", lambda name: name == "slack")
    with patch("mesh.list_hosts", return_value=[]):
        result = resolver.find_satisfier("channel")
    assert result["type"] == "mcp"
    assert result["name"] == "slack"


def test_find_satisfier_picks_host_when_no_local(mock_home, marketplace_json):
    """When no plugin/MCP satisfies, fall through to a mesh host."""
    fake_hosts = [
        {"host": "local-yocal", "self": True, "capabilities": []},
        {"host": "pixel-7-pro", "self": False, "capabilities": ["sms-send"]},
    ]
    with patch("mesh.list_hosts", return_value=fake_hosts):
        result = resolver.find_satisfier("sms-send")
    assert result["type"] == "host"
    assert result["host"] == "pixel-7-pro"


def test_find_satisfier_returns_none_when_nothing_satisfies(mock_home, marketplace_json):
    """Capability that nothing in the world provides → none."""
    with patch("mesh.list_hosts", return_value=[]):
        result = resolver.find_satisfier("never-heard-of-it")
    assert result["type"] == "none"


def test_find_satisfier_local_plugin_wins_over_host(mock_home, marketplace_json, installed_plugins):
    """Local plugin always preferred even if a host also advertises — saves a hop."""
    fake_hosts = [
        {"host": "pixel-7-pro", "self": False, "capabilities": ["notification"]},
    ]
    with patch("mesh.list_hosts", return_value=fake_hosts):
        result = resolver.find_satisfier("notification")
    assert result["type"] == "plugin"
    assert result["name"] == "notify-linux"


def test_find_satisfier_mcp_wins_over_host(mock_home, marketplace_json, monkeypatch):
    """Loaded local MCP preferred over a remote host."""
    import probes
    monkeypatch.setattr(probes, "probe_mcp", lambda name: name == "slack")
    fake_hosts = [
        {"host": "pixel-7-pro", "self": False, "capabilities": ["channel"]},
    ]
    with patch("mesh.list_hosts", return_value=fake_hosts):
        result = resolver.find_satisfier("channel")
    assert result["type"] == "mcp"
    assert result["name"] == "slack"


def test_find_satisfier_self_host_treated_as_local(mock_home, marketplace_json):
    """If the self-host advertises the capability, prefer a 'host' result with self=true.

    Rationale: the resolver's caller (taskpilot) interprets host=self as 'spawn
    here', avoiding any forwarding. We don't want to silently downgrade to
    type=none just because no plugin was installed.
    """
    fake_hosts = [
        {"host": "local-yocal", "self": True, "capabilities": ["sms-send"]},
    ]
    with patch("mesh.list_hosts", return_value=fake_hosts):
        result = resolver.find_satisfier("sms-send")
    assert result["type"] == "host"
    assert result["host"] == "local-yocal"
    assert result["self"] is True
