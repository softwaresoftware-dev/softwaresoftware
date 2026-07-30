---
name: install
description: Install a plugin with all its dependencies resolved automatically. Detects your environment, picks the right providers, and installs everything in the correct order. Works across all installed Claude Code marketplaces.
argument-hint: "[plugin-name or plugin-name@marketplace]"
---

# softwaresoftware install

Install a plugin and all its dependencies in one step. Works across all installed Claude Code marketplaces — softwaresoftware plugins get full capability resolution, other marketplace plugins get a direct install.

## Arguments

The user provides a plugin name (e.g., `/softwaresoftware:install zapframe`) or a name with marketplace (e.g., `/softwaresoftware:install stagehand@claude-plugins-official`).

## Workflow

0. **Load the softwaresoftware MCP tool schemas.** If `list_marketplace_plugins`, `get_install_plan`, `get_plugin_post_install`, or `get_uninstall_plan` are listed as deferred tools in your environment, load their schemas via ToolSearch before calling them. Example query: `select:mcp__softwaresoftware__list_marketplace_plugins,mcp__softwaresoftware__get_install_plan,mcp__softwaresoftware__get_plugin_post_install,mcp__softwaresoftware__get_uninstall_plan` (the exact tool name prefix varies — use whatever prefix the deferred-tool list shows). If ToolSearch reports the tools are unavailable, the installer's MCP server isn't loaded — tell the user to run `/reload-plugins` and retry, then stop.

1. **Check for a plugin name.** If no argument was provided, or the argument doesn't match any plugin in any marketplace:
   - Call the `list_marketplace_plugins` MCP tool (no arguments — lists all marketplaces)
   - Show available plugins as a markdown table:

     | Plugin | Description | Version | Marketplace | Status |
     |--------|-------------|---------|-------------|--------|
     | (name) | (description) | (version) | (marketplace) | installed / available |

   - Ask the user which plugin they'd like to install, then continue to step 2 with their choice.

2. **Get the install plan.** Call the `get_install_plan` MCP tool with the plugin name (including `@marketplace` suffix if the user specified one).

3. **Handle errors and early exits.**
   - If the plan has an `error` field and it says the plugin wasn't found, go back to step 1 and show available plugins.
   - If the plan has any other `error`, tell the user and stop.
   - If `no_provider_available` is non-empty, **do not just dead-end** — diagnose and offer remediation. Each entry is `{"capability", "required", "providers": [{"plugin", "description", "unmet_probes"}]}`. For each entry:
     - **Empty `providers`** → no provider plugin exists for this capability at all. Explain that and stop.
     - **A provider with an `unmet_probes` entry shaped `binary:<name>`** → that provider is one missing binary away from working. This is fixable. Tell the user concretely, e.g.: *"`mindframe` needs `agent-spawning`, provided by `taskpilot`, which requires `tmux` — not installed on this machine."* Then **offer to install it**: *"Want me to install `tmux`?"* Pick the command from the OS — `sudo apt install -y tmux` (Debian/Ubuntu), `sudo dnf install -y tmux` (Fedora/RHEL), `brew install tmux` (macOS), `sudo pacman -S tmux` (Arch), `winget install <package>` (Windows). If the user agrees, install the binary, then **re-run `get_install_plan`** and continue from step 3 with the fresh plan.
     - **An `unmet_probes` entry shaped `os` or `os:<name>`** → the provider's OS doesn't match this machine. Not fixable by installing anything. Explain honestly which OS it needs and stop.
     - **An `unmet_probes` entry shaped `env:<VAR>`** → the provider needs an environment variable / credential (e.g. an API token). Name the variable, tell the user to set it, and stop — don't try to guess the value.
   - Only stop without remediation when nothing in `no_provider_available` is fixable. Never partial-install.
   - If `target_installed` is true AND `install_order` is empty: tell the user the plugin is already installed with all dependencies satisfied. **Then check `post_install`**: if `has_setup` is true, suggest the user run `/<plugin>:setup` — e.g., "You may want to run `/daemon-manager:setup` to configure auto-start on boot." Then stop.
   - If `target_installed` is true but `install_order` has entries: tell the user the plugin is installed but has missing dependencies, then continue to step 4 to install them.
   - If `target_external` is true: the target plugin comes from an external registry. The plan will include `external_registries` with the registry info and `target_registry` with the registry name. The skill must ensure this registry is configured (step 6) before installing the target with `claude plugin install <name>@<registry>`.

4. **Show the plan.** Present what will be installed as a markdown table:

   For **softwaresoftware plugins** (full resolution):

   | # | Plugin | Capability | Source | Status | Required |
   |---|--------|------------|--------|--------|----------|
   | — | (name) | (what it provides) | softwaresoftware-plugins / claude-plugins-official | already satisfied / to install | yes / optional |
   | last | target plugin | — | softwaresoftware-plugins | to install | — |

   For **other marketplace plugins** (passthrough):

   | # | Plugin | Source | Status |
   |---|--------|--------|--------|
   | 1 | (name) | (marketplace name) | to install |

   - Already-satisfied capabilities show as "already satisfied" in the Status column
   - Plugins to install show as "to install" with their install order number
   - External plugins (with `"external": true`) show their registry name in the Source column
   - MCP providers (with `"mcp_provider": true`) show "third-party MCP" in the Source column and include the install command
   - Passthrough plugins (with `"passthrough": true`) show their marketplace name in the Source column
   - The target plugin is the last row, unless `target_installed` is true
   - Include a one-line summary below the table (e.g., "2 to install (1 external), 1 already satisfied")

   **After the table, surface alternative providers.** For any `install_order` entry that has an `alternatives` array, render a short "Alternative providers" section so the user knows they can opt into a different implementation. Each alternative has a `ready` flag:

   - `ready: true` → the alternate matches the user's environment and can be installed right now.
   - `ready: false` → the alternate exists in the marketplace but its env probes don't pass yet (e.g. a missing binary). Surface it anyway with the unmet probes from `unmet_probes`, so the user knows what setup it needs.

   Format:

   ```
   ### Alternative providers

   For **knowledge-base** (selected: `knowledge-base`):

   Ready to use:
   - `some-other-kb` — local provider. Opt in: `/softwaresoftware:install some-other-kb` first.

   Available with setup:
   - `hive-mind` (external — `arctype-plugins`): Obsidian-based shared knowledge vault for teams with qmd-powered search. Needs: `binary:qmd`. Opt in: install qmd, then `/softwaresoftware:install hive-mind`.
   ```

   Rules:
   - Split alternatives into "Ready to use" (`ready: true`) and "Available with setup" (`ready: false`). Omit either subsection if its bucket is empty.
   - Show each alternate's name, external-registry tag if applicable, and one-line description (truncate at ~120 chars).
   - For `ready: false`, list the `unmet_probes` verbatim and give a concrete setup hint when one is obvious (e.g. install the missing binary).
   - Tell the user to install the alternate **first** (`/softwaresoftware:install <alt-name>`) and then re-run the original install — once the alternate is installed, the resolver marks the capability satisfied and uses it instead of the local default.
   - Skip the whole section entirely if no entry in `install_order` has alternatives.

5. **Ask for confirmation.** Wait for explicit user approval before installing anything. If alternatives were shown, the user may choose to abort and install one of them first instead.

6. **Ensure external registries are configured.** If the install plan includes `external_registries`, check that each is available:
   - Run `claude plugin marketplace list` and parse the output
   - For each registry in the plan's `external_registries` map, check if it appears in the marketplace list
   - If a registry is missing, add it using the `repo` field from the plan: `claude plugin marketplace add <repo>` (e.g., `claude plugin marketplace add anthropics/claude-plugins-official`)
   - If adding the marketplace fails, tell the user and stop

7. **Create tasks and install.** After confirmation, create a task for each plugin to install (dependencies + target). Each task should be named like "Install dockside (docker-dev-environment)". Then work through them in order:
   - Set the task to in_progress
   - **MCP providers** (install plan entry has `"mcp_provider": true`): Show the user the install command from the `install_command` field and tell them to run it in their terminal. Example: "Run this in your terminal: `claude mcp add --transport http --scope user slack https://mcp.slack.com/mcp`". Then mark the task completed — the MCP will be available after the session restarts.
   - **External plugins** (install plan entry has `"external": true`): Run `claude plugin install <plugin_name>@<registry>` where `<registry>` is the entry's `registry` field (e.g., `claude-plugins-official`)
   - **Passthrough plugins** (install plan entry has `"passthrough": true`): Run `claude plugin install <plugin_name>@<marketplace>` where `<marketplace>` is the entry's `marketplace` field
   - **Local plugins**: Run `claude plugin install <plugin_name>` as before
   - If successful, mark the task completed
   - If it fails, mark the task as errored and stop — don't continue with remaining installs
   - **External target** (plan has `"target_external": true`): After installing all deps, install the target with `claude plugin install <plugin_name>@<target_registry>` where `<target_registry>` is the plan's `target_registry` field

8. **Verify.** Run `claude plugin list` and confirm all expected plugins appear. Report success or any discrepancies.

9. **Offer to add the installer instruction to CLAUDE.md.** After a successful install, check the user's root CLAUDE.md at `~/.claude/CLAUDE.md`:
   - Read the file if it exists
   - If the file already contains a softwaresoftware:install instruction, skip this step
   - If it does NOT, **ask the user for confirmation first** — never write to their CLAUDE.md silently. For example: "Want me to add a note to your `~/.claude/CLAUDE.md` so future sessions use `/softwaresoftware:install` for plugin installs?"
   - Only if the user agrees, append this block (creating the file if it doesn't exist):

     ```
     ## Plugin Installation

     Always use `/softwaresoftware:install <plugin-name>` to install Claude Code plugins. It works across all marketplaces, handles dependencies automatically, and detects your environment. Never use `claude plugin install` directly inside a session.
     ```

   - If the user declines, skip this step and don't ask again for subsequent installs in this session

10. **Detect skills and suggest next steps.** Call the `get_plugin_post_install` MCP tool with the target plugin name. Then tell the user:
    - Type `/reload-plugins` to load the installed plugins in this session.
    - List the skills detected (e.g., "Available skills: `/zapframe:create`, `/zapframe:dev`")
    - **If the plugin has a `:setup` skill** (`has_setup` is true): tell the user to run `/<plugin>:setup` after reloading plugins — e.g., "Run `/nginx-cloudflare-deploy:setup` to configure it."
    - If the plugin has `userConfig` fields and they need to reconfigure later: edit `~/.claude/settings.json` under `pluginConfigs.<plugin-name>.options.<field>` and then run `/reload-plugins`. (Claude Code does not re-prompt on `claude plugin disable`/`enable`, and there is no `claude plugin config` command.)

## Rules

- Never install without showing the plan and getting confirmation first
- Install in the exact order returned by `install_order` — dependencies before dependents
- If a plugin install command fails, stop immediately — don't leave a half-installed dependency chain
