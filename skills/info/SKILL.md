---
name: info
description: Show detailed information about a plugin — description, version, dependencies, environment compatibility, and install status.
argument-hint: "[plugin-name]"
---

# softwaresoftware info

Show everything about a plugin before you install it (or after).

## Arguments

The user provides a plugin name (e.g., `/softwaresoftware:info liteframe`).

## Workflow

1. **Check for a plugin name.** If no argument was provided:
   - Call the `list_marketplace_plugins` MCP tool
   - Show available plugins as a compact list and ask which one they want info on

2. **Look up the plugin.** Call `list_marketplace_plugins` and find the matching entry. If not found, show available plugins and stop.

3. **Check dependencies.** Call `check_dependencies` with the plugin name.

4. **Present the info.** Display in this format:

   ### plugin-name
   > description from marketplace

   | Field | Value |
   |-------|-------|
   | Version | x.y.z |
   | Category | provider / framework / app / etc |
   | Installed | yes / no |
   | Provides | capability-a, capability-b (or "—") |

   **Dependencies:**

   | Capability | Status | Provider |
   |------------|--------|----------|
   | notification | satisfied (notify-linux installed) | notify-linux |
   | scheduling | missing — no provider installed | — |
   | browser-automation | optional, not installed | claude-browser-bridge |

   - For each required capability, show whether it's satisfied and which installed plugin provides it
   - For missing required capabilities, note they'd be auto-resolved on install
   - For optional missing capabilities, label them as optional
   - If the plugin has no dependencies, say "No dependencies"
   - If the plugin has `built_in_capabilities`, list them as "built-in" in the status column

5. **Suggest next action.** Based on the state:
   - Not installed → "Install with `/softwaresoftware:install plugin-name`"
   - Installed with all deps satisfied → "All good — fully installed"
   - Installed with missing deps → "Missing dependencies. Run `/softwaresoftware:install plugin-name` to resolve"

## Rules

- This is read-only — never install or modify anything
- If the plugin name is close but not exact (e.g., "lite" for "liteframe"), suggest the closest match
