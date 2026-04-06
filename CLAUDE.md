# CLAUDE.md — softwaresoftware

Plugin installer for Claude Code. Detects environment, resolves capabilities to providers, auto-selects based on environment probes, generates install plans.

## Quick Reference

| Command | What it does |
|---------|-------------|
| `/softwaresoftware:install <plugin>` | Install a plugin with all dependencies resolved automatically |
| `/softwaresoftware:setup` | Diagnose environment and resolve plugin dependencies |

## Stack

- Python 3.11+, FastMCP, stdlib only (no external deps beyond mcp)
- 8 generic environment probes (OS, shell, binary, port, env, mcp, plugin, file)
- Reads: installed_plugins.json, settings.json, marketplace.json

## Architecture

- `probes.py` — 8 generic environment detection primitives
- `registry.py` — reads marketplace, installed plugins
- `resolver.py` — dependency diff engine, provider ranking, install plan generation
- `server.py` — FastMCP server exposing 2 MCP tools

## MCP Tools

- `check_dependencies(plugin_name)` — what's satisfied/missing
- `get_install_plan(plugin_name)` — ordered install list with auto-selected providers

## Development

```bash
pip install "mcp[cli]"
python server.py                # run MCP server
make test                       # run tests
```

Install as plugin:
```bash
claude --plugin-dir /home/thatcher/projects/softwaresoftware/projects/plugins/marketplace/softwaresoftware
```

## Capability System

Plugins declare dependencies on capabilities — semantic contracts that providers satisfy. Full reference: **[docs/capability-contracts.md](docs/capability-contracts.md)** — covers marketplace fields, environment probes, resolution algorithm, and how to write providers/consumers.

**How it works:** A plugin's marketplace.json entry has `requires: ["notification"]`. `check_dependencies` reads this, finds providers that have `provides: ["notification"]`, runs environment probes against each provider's `environment` conditions, and auto-selects the best match.

**Consumer skills use intent, not tool names.** Instead of hardcoding `send_notification(...)`, consumer skills say "Use the notification capability to alert the user with message X and urgency Y." Claude figures out which installed tool satisfies the capability and calls it.

**Dependency preamble — dual discovery.** When a consumer skill checks for missing capabilities, it should present two paths: (1) marketplace providers via `get_install_plan`, and (2) any MCP tools already in Claude's context that could satisfy the capability (e.g., a Gmail MCP satisfying notification). The user chooses, then the skill smoke tests the solution before proceeding.

**Probes are generic** — never plugin-specific. They check: os, shell, binary in PATH, TCP port, env var, MCP server, installed plugin, file exists. New providers = marketplace metadata only.
