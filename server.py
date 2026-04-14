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

    Works across all installed marketplaces. For softwaresoftware plugins,
    auto-selects the best provider for each missing capability based on
    environment probes. For plugins from other marketplaces, returns a
    passthrough install plan.

    Supports 'name@marketplace' syntax to target a specific marketplace.
    """
    return resolver.get_install_plan(plugin_name)


@mcp.tool()
def list_marketplace_plugins(marketplace: str = "") -> dict:
    """List all plugins available across all installed marketplaces.

    Returns plugin names, descriptions, versions, source marketplace, and
    whether each is installed. Pass a marketplace name to filter to one
    marketplace, or leave empty to list all.
    """
    return resolver.list_marketplace_plugins(marketplace or None)


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
