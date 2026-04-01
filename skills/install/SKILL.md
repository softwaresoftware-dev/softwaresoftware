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

2. **Handle errors.** If the plan has an `error` field, tell the user and stop. If `no_provider_available` is non-empty, list the unsatisfied capabilities and explain what's missing. Stop — don't partial-install.

3. **Show the plan.** Present what will be installed:
   - Already satisfied capabilities (no action needed)
   - Each plugin to install, in order, with: name, what capability it provides, and why it was selected
   - The target plugin itself (installed last)
   - Format as a clear list the user can review at a glance

4. **Ask for confirmation.** Wait for explicit user approval before installing anything.

5. **Install dependencies in order.** For each entry in `install_order`, run:
   ```
   claude plugin install <plugin_name>
   ```
   If any install fails, stop and report the error. Don't continue with remaining installs.

6. **Install the target plugin.** Run:
   ```
   claude plugin install <plugin_name>
   ```

7. **Verify.** Run `claude plugin list` and confirm all expected plugins appear. Report success or any discrepancies.

8. **Next steps.** Tell the user:
   - They need to **restart Claude Code** for the new plugins' skills and MCP tools to load
   - List the skills the target plugin provides (look up its marketplace entry description to give context)
   - If the plugin has `userConfig` fields, mention they can run `claude plugin configure <plugin_name>` to set them up

## Rules

- Never install without showing the plan and getting confirmation first
- Install in the exact order returned by `install_order` — dependencies before dependents
- If the target plugin is already installed, say so and skip to checking its dependencies
- If all dependencies are already satisfied, just install the target plugin directly
- If a plugin install command fails, stop immediately — don't leave a half-installed dependency chain
