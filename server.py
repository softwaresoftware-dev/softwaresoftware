"""MCP server for softwaresoftware — plugin dependency resolver and environment detective."""

from mcp.server.fastmcp import FastMCP

import resolver

mcp = FastMCP("softwaresoftware")


@mcp.tool()
def check_dependencies(plugin_name: str) -> dict:
    """Check which capabilities a plugin requires and whether they're satisfied.

    Returns satisfied, missing (required), and optional_missing capabilities.
    """
    return resolver.check_dependencies(plugin_name)


@mcp.tool()
def get_install_plan(plugin_name: str) -> dict:
    """Generate an ordered install plan for a plugin and its missing dependencies.

    Auto-selects the best provider for each missing capability based on
    environment probes. Returns install order, already satisfied capabilities,
    and any capabilities with no available provider.
    """
    return resolver.get_install_plan(plugin_name)


@mcp.tool()
def list_marketplace_plugins() -> dict:
    """List all plugins available in the marketplace.

    Returns plugin names, descriptions, versions, and whether each is installed.
    Useful for discovering available plugins or suggesting options when a user
    doesn't specify a plugin name.
    """
    return resolver.list_marketplace_plugins()


@mcp.tool()
def get_uninstall_plan(plugin_name: str) -> dict:
    """Generate an uninstall plan for a plugin and its orphaned dependencies.

    Identifies dependencies that can be safely removed because no other
    installed plugin needs the capabilities they provide. Dependencies
    shared with other plugins are kept.
    """
    return resolver.get_uninstall_plan(plugin_name)


if __name__ == "__main__":
    mcp.run()
