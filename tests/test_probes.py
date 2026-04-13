"""Tests for probes.py — generic environment detection primitives."""

import json

import probes


def test_probe_shell(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.delenv("PSModulePath", raising=False)
    assert probes.probe_shell() == "bash"


def test_probe_shell_zsh(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.delenv("PSModulePath", raising=False)
    assert probes.probe_shell() == "zsh"


def test_probe_shell_powershell(monkeypatch):
    monkeypatch.setenv("PSModulePath", "/some/path")
    assert probes.probe_shell() == "powershell"


def test_probe_plugin(mock_home, installed_plugins):
    assert probes.probe_plugin("notify-linux") is True
    assert probes.probe_plugin("nonexistent") is False


def test_probe_mcp_from_installed(mock_home, installed_plugins):
    assert probes.probe_mcp("notify-linux") is True
    assert probes.probe_mcp("nonexistent") is False


def test_probe_mcp_from_settings_local(mock_home):
    """MCPs registered in settings.local.json are detected."""
    settings_local = mock_home / ".claude" / "settings.local.json"
    settings_local.write_text(json.dumps({
        "mcpServers": {
            "slack": {"command": "npx", "args": ["-y", "@anthropic/slack-mcp"]},
        }
    }))
    assert probes.probe_mcp("slack") is True
    assert probes.probe_mcp("nonexistent") is False


def test_probe_mcp_from_claude_json(mock_home):
    """MCPs registered in ~/.claude.json are detected."""
    claude_json = mock_home / ".claude.json"
    claude_json.write_text(json.dumps({
        "mcpServers": {
            "gmail-organizer": {"command": "node", "args": ["server.js"]},
        }
    }))
    assert probes.probe_mcp("gmail-organizer") is True
    assert probes.probe_mcp("nonexistent") is False


def test_gather_facts_list_values(monkeypatch):
    """List values in environment reqs expand into individual fact entries."""
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    env_reqs = [{"os": ["linux", "darwin", "windows"]}]
    facts = probes.gather_facts(env_reqs)
    assert facts["os:linux"] is True
    assert facts["os:darwin"] is False
    assert facts["os:windows"] is False


def test_gather_facts(monkeypatch):
    monkeypatch.delenv("PSModulePath", raising=False)
    env_reqs = [
        {"os": "linux", "binary": "python"},
        {"os": "darwin"},
    ]
    facts = probes.gather_facts(env_reqs)
    assert "os:linux" in facts
    assert "os:darwin" in facts
    assert "binary:python" in facts
    # Each key should be a bool
    for v in facts.values():
        assert isinstance(v, bool)


