# Capability Contracts

Capabilities are abstract contracts between plugins. A **consumer** declares what it needs; a **provider** satisfies that need. The softwaresoftware resolver connects them at install time based on the user's environment.

There is no capability registry or schema file. A capability exists because at least one plugin `provides` it or `requires` it in `marketplace.json`.

## Marketplace entry fields

Every plugin in `marketplace.json` can use these capability-related fields:

```jsonc
{
  "name": "my-plugin",
  "category": "provider",         // "provider" for plugins that satisfy capabilities
  "requires": ["notification"],   // capabilities that MUST be satisfied before install
  "optional": ["scheduling"],     // capabilities that enhance the plugin but aren't required
  "provides": ["notification"],   // capabilities this plugin satisfies (providers only)
  "built_in_capabilities": [],    // capabilities satisfied internally, no external provider needed
  "environment": {                // conditions for auto-selection (providers only)
    "os": "linux",
    "binary": "notify-send"
  }
}
```

### Field reference

| Field | Type | Used by | Purpose |
|-------|------|---------|---------|
| `requires` | `string[]` | consumers | Capabilities that must be installed. The resolver blocks install if no provider matches. |
| `optional` | `string[]` | consumers | Capabilities used if available, skipped if not. No install failure. |
| `provides` | `string[]` | providers | Capabilities this plugin satisfies. Multiple providers can provide the same capability. |
| `built_in_capabilities` | `string[]` | consumers | Capabilities the plugin handles internally. The resolver skips dependency resolution for these. |
| `environment` | `object` | providers | Probe conditions that determine if this provider works in the user's environment. All conditions must match for auto-selection. |
| `category` | `string` | all | One of: `development`, `research`, `utilities`, `provider`, `framework`, `toolkit`. Providers should use `"provider"`. |

## Environment probes

The `environment` object maps probe keys to expected values. The resolver runs only the probes needed by candidate providers. All conditions in a provider's `environment` must pass for it to be selected.

| Probe | Value type | What it checks | Example |
|-------|-----------|----------------|---------|
| `os` | `string` | `platform.system().lower()` — `linux`, `darwin`, or `windows` | `"os": "linux"` |
| `shell` | `string` | Current shell — `bash`, `zsh`, `powershell`, `cmd` | `"shell": "bash"` |
| `binary` | `string` | Binary exists in `PATH` via `shutil.which()` | `"binary": "docker"` |
| `port` | `string` | TCP port is reachable — format `host:port` | `"port": "localhost:5432"` |
| `env` | `string` | Environment variable is set and non-empty | `"env": "SLACK_WEBHOOK_URL"` |
| `mcp` | `string` | MCP server is configured (in installed plugins or settings.json) | `"mcp": "gmail"` |
| `plugin` | `string` | Plugin is installed (in installed_plugins.json) | `"plugin": "liteframe"` |
| `file` | `string` | File or directory exists (supports `~` expansion) | `"file": "~/.config/app"` |

### List values

A probe value can be a list, meaning "any of these matches":

```json
"environment": {
  "os": ["linux", "darwin"]
}
```

This provider matches Linux OR macOS.

### No environment = universal

A provider with an empty `environment` object (or no `environment` field) matches every environment. Use this for providers that are pure Python/JS with no platform-specific dependencies.

## How resolution works

When a consumer plugin is installed via `/softwaresoftware:install`:

1. **Read requires/optional** — the resolver reads the consumer's `requires` and `optional` arrays.
2. **Skip built-ins** — any capability listed in `built_in_capabilities` is marked satisfied immediately.
3. **Check installed** — for each remaining capability, check if an installed plugin already provides it.
4. **Find candidates** — for unmet capabilities, find all marketplace plugins that `provides` it.
5. **Probe environment** — run the environment probes for each candidate. Only candidates where all conditions pass are considered.
6. **Rank and select** — candidates are sorted: environment match first, local (same marketplace) before external, already-installed before not. The top candidate is selected.
7. **Recurse** — the selected provider may itself have `requires`/`optional`, so the resolver recurses.
8. **Topological order** — the final install plan lists dependencies before dependents.

### What happens when resolution fails

- **No candidates at all** — the capability appears in `no_provider_available` in the install plan. If it was `requires`, the install skill warns the user. If `optional`, it's noted but install proceeds.
- **Candidates exist but none match environment** — same as no candidates. The user sees which providers exist and why they didn't match (via `match_details`).
- **Cycle detected** — the resolver tracks a `resolving` stack and skips capabilities already being resolved.

## Writing a provider

A provider is a plugin that satisfies one or more capabilities for consumers.

### Minimal example

Plugin that provides `notification` on Linux:

**marketplace.json entry:**

```json
{
  "name": "notify-linux",
  "category": "provider",
  "requires": [],
  "optional": [],
  "provides": ["notification"],
  "environment": {
    "os": "linux",
    "binary": "notify-send"
  }
}
```

The plugin itself exposes MCP tools or skills that implement the notification behavior. There's no formal interface — consumers reference capabilities by intent in their skill files, and Claude routes to whatever tools are available.

### Multi-capability provider

A plugin can provide multiple capabilities:

```json
{
  "provides": ["notification", "send-sms"],
  "environment": {
    "plugin": "termux-remote"
  }
}
```

### Provider selection priority

When multiple providers match for a capability, the resolver picks based on (in order):

1. Environment match (`true` before `false`)
2. Local marketplace before external registry
3. Already installed before not installed

There is no explicit priority field. If you need to influence selection, make the `environment` conditions more specific.

## Writing a consumer

A consumer declares what capabilities it needs. The resolver handles the rest.

### Marketplace entry

```json
{
  "name": "cardwatch",
  "category": "utilities",
  "requires": ["notification"],
  "optional": ["scheduling"],
  "provides": [],
  "environment": {}
}
```

### Referencing capabilities in skills

Consumer skills must never hardcode provider tool names. Use intent-based language:

```markdown
<!-- Good: decoupled -->
Send a notification to the user with message "Stock found!".
Use an available skill or tool.

<!-- Good: with guard for optional capability -->
Schedule this check to run every 30 minutes.
Use an available skill or tool.
If no scheduling tool is available, skip this step.

<!-- Bad: coupled to a specific provider -->
Call `mcp__notify-linux__send_notification`.
```

This works because:
- Claude sees all loaded skills and MCP tools in context
- `requires` dependencies are guaranteed to be installed
- `optional` dependencies might not be — always add a skip guard

## Creating a new capability

A capability is just a string. There's no definition file to create. To introduce one:

1. **Name it** — lowercase kebab-case describing the *what*, not the *how*. `notification` not `notify-send-wrapper`.
2. **Build the first provider** — a capability with no provider is useless. Set `category: "provider"`, add the capability to `provides`, add `environment` conditions.
3. **Add a consumer** — at least one plugin should `requires` or `optional` the capability.
4. **Register in marketplace.json** — add the provider entry and update any consumer entries.

### Naming conventions

| Pattern | Example | Note |
|---------|---------|------|
| Single noun | `notification`, `deploy` | Preferred for broad capabilities |
| Noun phrase | `browser-automation`, `terminal-ops` | When a single noun is ambiguous |
| Domain-scoped | `social-posting-reddit` | When the capability is domain-specific |

Avoid verb forms (`notify`, `automate-browser`) and implementation details (`tmux-sessions`, `systemd-scheduling`).

## Existing capabilities

| Capability | Providers | Environment probes |
|-----------|-----------|-------------------|
| `notification` | notify-linux, notify-windows, notify-termux, notify-slack, notify-email | os, mcp |
| `browser-automation` | claude-browser-bridge | -- |
| `terminal-ops` | tmux-session | binary: tmux |
| `daemon` | daemon-manager | os |
| `deploy` | nginx-cloudflare-deploy | binary: nginx, cloudflared |
| `docker-dev-environment` | dockside | binary: docker |
| `scheduling` | scheduling-agent | os, binary: systemctl |
| `agent-spawning` | taskpilot | os, binary: tmux |
| `channel` | termux-conversation | mcp |
| `human-approval` | approval-channel | optional: channel |
| `memory` | agent-memory | -- |
| `design-system` | softwaresoftware-design-system | -- |
| `social-posting-reddit` | reddit-poster | -- |
| `payment-information` | payment-vault | -- |
| `address` | address-vault | -- |
| `contacts` | contacts-vault | -- |
| `vehicle-info` | vehicle-vault | -- |
| `identity-documents` | identity-vault | -- |
