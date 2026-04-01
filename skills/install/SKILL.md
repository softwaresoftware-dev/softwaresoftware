---
name: install
description: Install a plugin with all its dependencies resolved automatically. Detects your environment, picks the right providers, and installs everything in the correct order.
---

# nov-dependency-resolver install

Install a plugin and all its dependencies in one step.

## Arguments

The user provides a plugin name (e.g., `/nov-dependency-resolver:install zapframe`).

## Workflow

1. **Get the install plan.** Call the `get_install_plan` MCP tool with the plugin name.

2. **Handle errors and early exits.**
   - If the plan has an `error` field, tell the user and stop.
   - If `no_provider_available` is non-empty, list the unsatisfied capabilities and explain what's missing. Stop — don't partial-install.
   - If `target_installed` is true AND `install_order` is empty: tell the user the plugin is already installed with all dependencies satisfied. Stop.
   - If `target_installed` is true but `install_order` has entries: tell the user the plugin is installed but has missing dependencies, then continue to step 3 to install them.

3. **Show the plan.** Present what will be installed as a markdown table:

   | # | Plugin | Capability | Status | Required |
   |---|--------|------------|--------|----------|
   | — | (name) | (what it provides) | already satisfied / to install | yes / optional |
   | last | target plugin | — | to install | — |

   - Already-satisfied capabilities show as "already satisfied" in the Status column
   - Plugins to install show as "to install" with their install order number
   - The target plugin is the last row, unless `target_installed` is true
   - Include a one-line summary below the table (e.g., "2 to install, 1 already satisfied")

4. **Ask for confirmation.** Wait for explicit user approval before installing anything.

5. **Create tasks and install.** After confirmation, create a task for each plugin to install (dependencies + target). Each task should be named like "Install dockside (docker-dev-environment)". Then work through them in order:
   - Set the task to in_progress
   - Run `claude plugin install <plugin_name>`
   - If successful, mark the task completed
   - If it fails, mark the task as errored and stop — don't continue with remaining installs

6. **Verify.** Run `claude plugin list` and confirm all expected plugins appear. Report success or any discrepancies.

7. **Next steps.** Tell the user:
   - Type `/reload-plugins` to load the new plugins into the current session (no restart needed)
   - List the skills the target plugin provides (look up its marketplace entry description to give context)
   - If the plugin has `userConfig` fields, mention they can run `claude plugin configure <plugin_name>` to set them up

## Rules

- Never install without showing the plan and getting confirmation first
- Install in the exact order returned by `install_order` — dependencies before dependents
- If a plugin install command fails, stop immediately — don't leave a half-installed dependency chain
