"""Shared fixtures for nov-dependency-resolver tests."""

import json

import pytest


@pytest.fixture
def mock_home(tmp_path, monkeypatch):
    """Set up a fake ~/.claude directory structure for testing."""
    claude_dir = tmp_path / ".claude"
    plugins_dir = claude_dir / "plugins"
    marketplaces_dir = plugins_dir / "marketplaces" / "nov-plugins"
    claude_plugin_dir = marketplaces_dir / ".claude-plugin"
    cache_dir = plugins_dir / "cache" / "nov-plugins"

    for d in [claude_plugin_dir, cache_dir]:
        d.mkdir(parents=True)

    # Patch Path.home() to return tmp_path
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Also patch the module-level constants in registry
    import registry
    monkeypatch.setattr(registry, "CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(registry, "PLUGINS_DIR", plugins_dir)
    monkeypatch.setattr(registry, "INSTALLED_PATH", plugins_dir / "installed_plugins.json")
    monkeypatch.setattr(registry, "SETTINGS_PATH", claude_dir / "settings.json")
    monkeypatch.setattr(registry, "MARKETPLACES_DIR", plugins_dir / "marketplaces")

    return tmp_path


@pytest.fixture
def marketplace_json(mock_home):
    """Write a marketplace.json with test plugins."""
    mp_path = mock_home / ".claude" / "plugins" / "marketplaces" / "nov-plugins" / ".claude-plugin" / "marketplace.json"
    data = {
        "name": "nov-plugins",
        "plugins": [
            {
                "name": "cardwatch",
                "source": {"source": "github", "repo": "ThatcherT/cardwatch"},
                "description": "Pokemon card stock monitor",
                "version": "2.0.0",
                "requires": ["notification"],
                "optional": ["scheduling"],
                "provides": [],
                "environment": {},
            },
            {
                "name": "notify-linux",
                "source": {"source": "github", "repo": "ThatcherT/notify-linux"},
                "description": "Linux desktop notifications",
                "version": "2.0.0",
                "requires": [],
                "optional": [],
                "provides": ["notification"],
                "environment": {"os": "linux", "binary": "notify-send"},
            },
            {
                "name": "notify-macos",
                "source": {"source": "github", "repo": "ThatcherT/notify-macos"},
                "description": "macOS notifications",
                "version": "1.0.0",
                "requires": [],
                "optional": [],
                "provides": ["notification"],
                "environment": {"os": "darwin"},
            },
            {
                "name": "daemon-manager",
                "source": {"source": "github", "repo": "ThatcherT/daemon-manager"},
                "description": "Persistent background process manager",
                "version": "1.0.0",
                "requires": [],
                "optional": [],
                "provides": ["daemon"],
                "environment": {"os": ["linux", "darwin", "windows"]},
            },
            {
                "name": "test-app",
                "source": {"source": "github", "repo": "ThatcherT/test-app"},
                "description": "Test app requiring browser-automation",
                "version": "1.0.0",
                "requires": ["browser-automation"],
                "optional": [],
                "provides": [],
                "environment": {},
            },
            {
                "name": "test-browser",
                "source": {"source": "github", "repo": "ThatcherT/test-browser"},
                "description": "Browser automation provider requiring daemon-proc",
                "version": "1.0.0",
                "requires": ["daemon-proc"],
                "optional": [],
                "provides": ["browser-automation"],
                "environment": {},
            },
            {
                "name": "test-daemon",
                "source": {"source": "github", "repo": "ThatcherT/test-daemon"},
                "description": "Daemon process provider for all platforms",
                "version": "1.0.0",
                "requires": [],
                "optional": [],
                "provides": ["daemon-proc"],
                "environment": {"os": ["linux", "darwin", "windows"]},
            },
            {
                "name": "liteframe",
                "source": {"source": "github", "repo": "ThatcherT/liteframe"},
                "description": "Static page publisher",
                "version": "1.1.0",
                "requires": [],
                "optional": [],
                "provides": [],
                "built_in_capabilities": ["static-site-build"],
                "environment": {},
            },
        ],
    }
    mp_path.write_text(json.dumps(data))
    return data


@pytest.fixture
def installed_plugins(mock_home):
    """Write an installed_plugins.json with notify-linux installed."""
    install_path = mock_home / ".claude" / "plugins" / "cache" / "nov-plugins" / "notify-linux" / "2.0.0"
    install_path.mkdir(parents=True)
    plugin_dir = install_path / ".claude-plugin"
    plugin_dir.mkdir()
    plugin_dir.joinpath("plugin.json").write_text(json.dumps({
        "name": "notify-linux",
        "mcpServers": {"notify-linux": {"command": "python", "args": ["server.py"]}},
    }))

    data = {
        "version": 2,
        "plugins": {
            "notify-linux@nov-plugins": [
                {
                    "scope": "user",
                    "installPath": str(install_path),
                    "version": "2.0.0",
                }
            ]
        },
    }
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps(data))
    return data
