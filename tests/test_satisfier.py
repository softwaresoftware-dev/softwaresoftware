"""Tests for resolver.find_satisfier — runtime capability satisfier lookup.

find_satisfier picks where a capability will be served at spawn time:
locally-installed plugin, loaded third-party MCP, or nothing.
Order is preference: local plugin > MCP > none.
"""

import resolver


def test_find_satisfier_picks_installed_plugin(mock_home, marketplace_json, installed_plugins):
    """notify-linux is installed and provides 'notification'."""
    result = resolver.find_satisfier("notification")
    assert result["type"] == "plugin"
    assert result["name"] == "notify-linux"


def test_find_satisfier_picks_loaded_mcp_when_no_plugin(mock_home, marketplace_json, monkeypatch):
    """When no plugin is installed, a loaded third-party MCP satisfies."""
    import probes
    monkeypatch.setattr(probes, "probe_mcp", lambda name: name == "slack")
    result = resolver.find_satisfier("channel")
    assert result["type"] == "mcp"
    assert result["name"] == "slack"


def test_find_satisfier_local_plugin_wins_over_mcp(mock_home, marketplace_json, installed_plugins, monkeypatch):
    """A local plugin is preferred over a loaded MCP for the same capability."""
    import probes
    monkeypatch.setattr(probes, "probe_mcp", lambda name: True)
    result = resolver.find_satisfier("notification")
    assert result["type"] == "plugin"
    assert result["name"] == "notify-linux"


def test_find_satisfier_returns_none_when_nothing_satisfies(mock_home, marketplace_json):
    """Capability that nothing local provides → none."""
    result = resolver.find_satisfier("never-heard-of-it")
    assert result["type"] == "none"
