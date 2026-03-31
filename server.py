"""MCP server for nov-dependency-resolver — plugin dependency resolver and environment detective."""

from mcp.server.fastmcp import FastMCP

import resolver

mcp = FastMCP("nov-dependency-resolver")


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


if __name__ == "__main__":
    mcp.run()
