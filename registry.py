"""Registry reader for softwaresoftware — reads marketplace, installed plugins, and capability contracts.

All reads are at call time, never cached.
"""

import json
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PLUGINS_DIR = CLAUDE_DIR / "plugins"
INSTALLED_PATH = PLUGINS_DIR / "installed_plugins.json"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
MARKETPLACES_DIR = PLUGINS_DIR / "marketplaces"


def _read_json(path: Path) -> dict | list | None:
    """Read a JSON file, return None if missing or invalid."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_installed_plugins() -> dict:
    """Read installed_plugins.json.

    Returns:
        Dict mapping plugin keys (e.g. "liteframe@softwaresoftware-plugins") to their install info.
    """
    data = _read_json(INSTALLED_PATH)
    if not data or not isinstance(data, dict):
        return {}
    return data.get("plugins", {})


def get_enabled_plugins() -> dict:
    """Read enabledPlugins from settings.json.

    Returns:
        Dict mapping plugin keys to enabled status.
    """
    data = _read_json(SETTINGS_PATH)
    if not data or not isinstance(data, dict):
        return {}
    return data.get("enabledPlugins", {})


def get_marketplace_plugins(marketplace: str = "softwaresoftware-plugins") -> list[dict]:
    """Read plugins from a marketplace's marketplace.json.

    Returns:
        List of plugin entries from the marketplace.
    """
    mp_path = MARKETPLACES_DIR / marketplace / ".claude-plugin" / "marketplace.json"
    data = _read_json(mp_path)
    if not data or not isinstance(data, dict):
        return []
    return data.get("plugins", [])


def get_plugin_manifest(plugin_key: str) -> dict | None:
    """Read the plugin.json manifest for an installed plugin.

    Args:
        plugin_key: Key from installed_plugins.json (e.g. "liteframe@softwaresoftware-plugins")

    Returns:
        Parsed plugin.json dict, or None if not found.
    """
    installed = get_installed_plugins()
    entries = installed.get(plugin_key, [])
    if not entries:
        return None
    install_path = Path(entries[0].get("installPath", ""))
    manifest_path = install_path / ".claude-plugin" / "plugin.json"
    return _read_json(manifest_path)


def get_external_registries(marketplace: str = "softwaresoftware-plugins") -> dict:
    """Read the external_registries map from a marketplace.

    Returns:
        Dict mapping registry name to its config (e.g. {"repo": "anthropics/claude-plugins-official"}).
    """
    mp_path = MARKETPLACES_DIR / marketplace / ".claude-plugin" / "marketplace.json"
    data = _read_json(mp_path)
    if not data or not isinstance(data, dict):
        return {}
    return data.get("external_registries", {})


def find_marketplace_plugin(name: str, marketplace: str = "softwaresoftware-plugins") -> dict | None:
    """Find a plugin entry in the marketplace by name.

    Returns:
        Plugin dict from marketplace.json, or None.
    """
    for plugin in get_marketplace_plugins(marketplace):
        if plugin.get("name") == name:
            return plugin
    return None


def get_providers(capability: str, marketplace: str = "softwaresoftware-plugins") -> list[dict]:
    """Find all plugins in the marketplace that provide a capability.

    Returns:
        List of marketplace plugin entries that have the capability in their 'provides' field.
    """
    providers = []
    for plugin in get_marketplace_plugins(marketplace):
        if capability in plugin.get("provides", []):
            providers.append(plugin)
    return providers


def is_plugin_installed(name: str) -> bool:
    """Check if a plugin is installed by name (ignoring marketplace suffix)."""
    for key in get_installed_plugins():
        if key.split("@")[0] == name:
            return True
    return False
