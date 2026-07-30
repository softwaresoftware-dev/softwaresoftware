"""Generic environment probes for softwaresoftware dependency resolution.

Eight primitives that detect facts about the user's environment.
Never plugin-specific — new providers add marketplace metadata, not new probes.
"""

import json
import os
import platform
import shutil
import socket
from pathlib import Path


def probe_os() -> str:
    """Detect operating system: linux, darwin, or windows."""
    return platform.system().lower()


def probe_shell() -> str:
    """Detect current shell: bash, zsh, powershell, or cmd."""
    if os.environ.get("PSModulePath"):
        return "powershell"
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "bash" in shell:
        return "bash"
    if os.name == "nt":
        return "cmd"
    return os.path.basename(shell) if shell else "unknown"


# Fallback binary names — when the primary name isn't found, try these.
# Windows ships the real interpreter as python.exe; "python3" may not exist
# or may resolve to the WindowsApps Store stub.
BINARY_FALLBACKS = {
    "python3": ["python"],
}


def _which(name: str) -> str | None:
    """shutil.which, but treats Windows Store stubs as not-found.

    The WindowsApps python.exe/python3.exe are zero-byte stubs that open the
    Microsoft Store instead of running Python — finding one is a false positive.
    """
    path = shutil.which(name)
    if path and "WindowsApps" in path:
        return None
    return path


def probe_binary(name: str) -> bool:
    """Check if a binary is available in PATH.

    Falls back to known alternate names (e.g. python3 -> python on Windows)
    and ignores WindowsApps Store stubs.
    """
    if _which(name) is not None:
        return True
    for alt in BINARY_FALLBACKS.get(name, []):
        if _which(alt) is not None:
            return True
    return False


def probe_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def _probe_port_value(value) -> bool:
    """Parse a 'host:port' probe value and check reachability.

    Tolerant of malformed values (missing colon, non-numeric port,
    non-string input) — returns False instead of raising.
    """
    try:
        host, _, port = str(value).rpartition(":")
        if not host:
            return False
        return probe_port(host, int(port))
    except (ValueError, TypeError):
        return False


def probe_env(name: str) -> bool:
    """Check if an environment variable is set (non-empty)."""
    return bool(os.environ.get(name))


def probe_mcp(name: str) -> bool:
    """Check if an MCP server is configured in any user-scope location."""
    # Check installed plugins for mcpServers
    installed_path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    if installed_path.exists():
        try:
            data = json.loads(installed_path.read_text())
            plugins = data.get("plugins", {})
            for entries in plugins.values():
                for entry in entries:
                    install_path = Path(entry.get("installPath", ""))
                    plugin_json = install_path / ".claude-plugin" / "plugin.json"
                    if plugin_json.exists():
                        manifest = json.loads(plugin_json.read_text())
                        if name in manifest.get("mcpServers", {}):
                            return True
        except Exception:
            # Malformed installed_plugins.json or plugin.json — treat as not found
            pass

    # Check all user-scope settings files for manual MCP configs
    # Claude Code reads mcpServers from multiple locations:
    #   ~/.claude.json              — primary user config
    #   ~/.claude/settings.json     — user settings
    #   ~/.claude/settings.local.json — local overrides (not committed)
    home = Path.home()
    settings_paths = [
        home / ".claude.json",
        home / ".claude" / "settings.json",
        home / ".claude" / "settings.local.json",
    ]
    for settings_path in settings_paths:
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text())
                if name in settings.get("mcpServers", {}):
                    return True
            except Exception:
                pass

    return False


def probe_plugin(name: str) -> bool:
    """Check if a plugin is installed (present in installed_plugins.json)."""
    installed_path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    if not installed_path.exists():
        return False
    try:
        data = json.loads(installed_path.read_text())
        plugins = data.get("plugins", {})
        for key in plugins:
            # Keys are like "pluginname@marketplace"
            plugin_name = key.split("@")[0]
            if plugin_name == name:
                return True
    except Exception:
        # Malformed installed_plugins.json — treat as not installed
        pass
    return False


def probe_file(path: str) -> bool:
    """Check if a file or directory exists."""
    return Path(os.path.expanduser(path)).exists()


# Probe dispatch table — maps environment requirement keys to probe functions
PROBES = {
    "os": lambda val: probe_os() == val,
    "shell": lambda val: probe_shell() == val,
    "binary": lambda val: probe_binary(val),
    "port": lambda val: _probe_port_value(val),
    "env": lambda val: probe_env(val),
    "mcp": lambda val: probe_mcp(val),
    "plugin": lambda val: probe_plugin(val),
    "file": lambda val: probe_file(val),
}


def gather_facts(environment_reqs: list[dict]) -> dict:
    """Run only the probes that candidates need.

    Args:
        environment_reqs: List of environment dicts from candidate plugins.
            Each dict maps probe keys to expected values.
            e.g. [{"os": "linux", "binary": "notify-send"}, {"os": "darwin"}]

    Returns:
        Dict of {probe_key:value: bool} for all checked conditions.
        e.g. {"os:linux": True, "binary:notify-send": True, "os:darwin": False}
    """
    facts = {}
    for env_req in environment_reqs:
        if not isinstance(env_req, dict):
            # Malformed marketplace entry — skip, never crash the plan
            continue
        for key, value in env_req.items():
            # List values expand into individual checks (e.g. os: ["linux", "darwin"])
            values = value if isinstance(value, list) else [value]
            for v in values:
                fact_key = f"{key}:{v}"
                if fact_key not in facts:
                    probe_fn = PROBES.get(key)
                    if probe_fn:
                        try:
                            facts[fact_key] = bool(probe_fn(v))
                        except Exception:
                            # A probe crashing on a malformed value must never
                            # break an install plan — treat as not matching.
                            facts[fact_key] = False
                    else:
                        facts[fact_key] = False
    return facts
