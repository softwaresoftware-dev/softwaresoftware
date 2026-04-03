---
name: uninstall
description: Uninstall a plugin and its orphaned dependencies. Only removes dependencies that no other installed plugin needs.
---

# softwaresoftware uninstall

Uninstall a plugin and safely remove dependencies that are no longer needed by anything else.

## Arguments

The user provides a plugin name (e.g., `/softwaresoftware:uninstall liteframe`).

## Workflow

1. **Get the uninstall plan.** Call the `get_uninstall_plan` MCP tool with the plugin name.

2. **Handle errors and early exits.**
   - If the plan has an `error` field, tell the user and stop.

3. **Show the plan.** Present what will be removed as a markdown table:

   | # | Plugin | Reason | Action |
   |---|--------|--------|--------|
   | 1 | (target) | target plugin | remove |
   | 2 | (dep) | Orphaned — provided 'capability' only for target | remove |
   | — | (dep) | Still needed by other installed plugins | keep |

   - Plugins in `remove_order` show as "remove" with their removal order number
   - Plugins in `kept_deps` show as "keep" (no order number) with the reason they're retained
   - Include a one-line summary below the table (e.g., "2 to remove, 1 kept (shared dependency)")

4. **Ask for confirmation.** Wait for explicit user approval before removing anything.

5. **Create tasks and uninstall.** After confirmation, create a task for each plugin to remove. Work through `remove_order` in order:
   - Set the task to in_progress
   - Run `claude plugin remove <plugin_name>`
   - If successful, mark the task completed
   - If it fails, mark the task as errored and stop — don't continue with remaining removals

6. **Verify.** Run `claude plugin list` and confirm all removed plugins no longer appear. Report success or any discrepancies.

7. **Next steps.** Tell the user:
   - Type `/exit` to quit, then start a new `claude` session to fully unload the removed plugins.

## Rules

- Never uninstall without showing the plan and getting confirmation first
- Remove in the exact order returned by `remove_order` — the target plugin first, then orphaned dependencies
- If a plugin remove command fails, stop immediately
- Never remove a dependency that is still needed by another installed plugin — this is the core safety guarantee
