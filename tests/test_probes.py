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


# --- probe_binary python-awareness (Windows) ---


def test_probe_binary_found_directly(monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda name: "/usr/bin/tmux" if name == "tmux" else None)
    assert probes.probe_binary("tmux") is True
    assert probes.probe_binary("nonexistent") is False


def test_probe_binary_python3_falls_back_to_python(monkeypatch):
    """On Windows, python3 doesn't exist but python.exe does — probe must fall back."""
    monkeypatch.setattr(
        probes.shutil, "which",
        lambda name: "C:\\Python312\\python.exe" if name == "python" else None,
    )
    assert probes.probe_binary("python3") is True


def test_probe_binary_windowsapps_stub_is_not_found(monkeypatch):
    """The WindowsApps Store stub must not count as a real binary."""
    stub = "C:\\Users\\u\\AppData\\Local\\Microsoft\\WindowsApps\\python3.exe"
    monkeypatch.setattr(probes.shutil, "which", lambda name: stub)
    assert probes.probe_binary("python3") is False


def test_probe_binary_stub_python3_falls_back_to_real_python(monkeypatch):
    """python3 resolves to a Store stub but a real python.exe exists elsewhere."""
    def fake_which(name):
        if name == "python3":
            return "C:\\Users\\u\\AppData\\Local\\Microsoft\\WindowsApps\\python3.exe"
        if name == "python":
            return "C:\\Python312\\python.exe"
        return None
    monkeypatch.setattr(probes.shutil, "which", fake_which)
    assert probes.probe_binary("python3") is True


def test_probe_binary_fallback_is_generic(monkeypatch):
    """Non-python binaries get no fallback — a missing binary stays missing."""
    monkeypatch.setattr(probes.shutil, "which", lambda name: None)
    assert probes.probe_binary("tmux") is False


# --- probe robustness against malformed values (fix: never crash install plans) ---


def test_probe_port_value_malformed():
    assert probes._probe_port_value("notaport") is False
    assert probes._probe_port_value("host:notanumber") is False
    assert probes._probe_port_value("") is False
    assert probes._probe_port_value(None) is False
    assert probes._probe_port_value(12345) is False
    assert probes._probe_port_value({"host": "x"}) is False


def test_gather_facts_malformed_values_never_raise(monkeypatch):
    """Malformed environment requirements produce False facts, not exceptions."""
    env_reqs = [
        {"port": "garbage-no-colon"},
        {"port": {"weird": "shape"}},
        {"binary": {"not": "a-string"}},
        {"unknown-probe": "value"},
        "not-a-dict-at-all",
        None,
    ]
    facts = probes.gather_facts(env_reqs)
    assert facts["port:garbage-no-colon"] is False
    assert facts["unknown-probe:value"] is False
    for v in facts.values():
        assert isinstance(v, bool)


def test_gather_facts_probe_exception_becomes_false(monkeypatch):
    """A probe that raises is treated as fact=False, never propagated."""
    def boom(val):
        raise RuntimeError("probe blew up")
    monkeypatch.setitem(probes.PROBES, "binary", boom)
    facts = probes.gather_facts([{"binary": "anything"}])
    assert facts["binary:anything"] is False


def test_probe_mcp_malformed_installed_plugins(mock_home):
    """Wrong-shaped installed_plugins.json (dict entries instead of lists) returns False."""
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps({
        "plugins": {"broken@mp": {"installPath": "/nope"}}
    }))
    assert probes.probe_mcp("anything") is False


def test_probe_plugin_malformed_installed_plugins(mock_home):
    """Wrong-shaped installed_plugins.json (list instead of dict) returns False."""
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps({
        "plugins": [{"name": "broken"}]
    }))
    assert probes.probe_plugin("broken") is False
