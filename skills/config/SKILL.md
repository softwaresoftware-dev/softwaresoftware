---
name: config
description: View and manage softwaresoftware settings. Shows current configuration and guides users through changing settings like telemetry.
argument-hint: "[setting-name]"
---

# softwaresoftware config

View and manage softwaresoftware plugin settings.

## Arguments

Optional setting name (e.g., `/softwaresoftware:config telemetry`). If omitted, show all settings.

## Settings

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| telemetry | `CLAUDE_PLUGIN_OPTION_TELEMETRY` | true | Send anonymous install/resolve events |

## Workflow

1. **Show current settings.** Check each `CLAUDE_PLUGIN_OPTION_*` environment variable and display a table:

   | Setting | Current Value | Default |
   |---------|--------------|---------|
   | telemetry | enabled / disabled / not set (using default: enabled) | enabled |

2. **If a setting name was provided**, explain what it does and its current value.

3. **To change a setting**, tell the user:
   - Run `claude plugin disable softwaresoftware` then `claude plugin enable softwaresoftware`
   - Claude Code will re-prompt for all userConfig values during enable
   - Then `/exit` and restart to apply

## Rules

- There is no `claude plugin config` CLI command — the only way to reconfigure is disable + re-enable
- Always show the current state before suggesting changes
- Be clear about what telemetry collects: anonymous install/resolve events, OS, shell, resolver version. No IP, no user ID, no file paths.
