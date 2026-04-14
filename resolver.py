"""Dependency resolver for softwaresoftware — the core diff engine.

Computes what a plugin needs, what's satisfied, what's missing,
and auto-selects providers based on environment probes.
"""

import time

import probes
import registry
import telemetry

# Third-party MCPs that can satisfy capabilities. When loaded, the resolver
# treats the capability as satisfied. When not loaded, the resolver includes
# them as installable candidates with user instructions.
KNOWN_MCP_PROVIDERS = {
    "slack": {
        "capabilities": ["channel", "notification"],
        "install": "claude mcp add --transport http --scope user slack https://mcp.slack.com/mcp",
        "description": "Official Slack MCP — send messages to Slack channels and DMs",
    },
    "gmail": {
        "capabilities": ["notification"],
        "install": "claude mcp add gmail",
        "description": "Gmail MCP — send email notifications",
    },
}


def _mcp_satisfies(capability: str) -> str | None:
    """Check if a loaded third-party MCP satisfies a capability.

    Returns the MCP name if satisfied, None otherwise.
    """
    for mcp_name, info in KNOWN_MCP_PROVIDERS.items():
        if capability in info["capabilities"] and probes.probe_mcp(mcp_name):
            return mcp_name
    return None


def _mcp_candidates(capability: str) -> list[dict]:
    """Get known MCP providers that could satisfy a capability (loaded or not).

    Returns list of candidate dicts compatible with the install plan format.
    """
    candidates = []
    for mcp_name, info in KNOWN_MCP_PROVIDERS.items():
        if capability in info["capabilities"]:
            candidates.append({
                "name": mcp_name,
                "description": info["description"],
                "install_command": info["install"],
                "mcp_provider": True,
                "loaded": probes.probe_mcp(mcp_name),
            })
    return candidates


def list_marketplace_plugins(marketplace: str | None = None) -> dict:
    """List all plugins available across marketplaces with install status.

    Args:
        marketplace: Specific marketplace to list, or None for all marketplaces.

    Returns:
        {
            "marketplaces": list[str],
            "plugins": list[dict],  — name, description, version, installed, category, marketplace
        }
    """
    if marketplace:
        marketplaces = [marketplace]
    else:
        marketplaces = registry.get_all_marketplaces()

    plugins = []
    seen = set()  # avoid duplicates if a plugin appears in multiple marketplaces
    for mp in marketplaces:
        for p in registry.get_marketplace_plugins(mp):
            name = p["name"]
            if name in seen:
                continue
            seen.add(name)
            entry = {
                "name": name,
                "description": p.get("description", ""),
                "version": p.get("version", ""),
                "installed": registry.is_plugin_installed(name),
                "category": p.get("category", ""),
                "marketplace": mp,
            }
            # Only include capability fields for softwaresoftware plugins
            if mp == "softwaresoftware-plugins":
                entry["provides"] = p.get("provides", [])
                entry["requires"] = p.get("requires", [])
                if p.get("external"):
                    entry["external"] = True
                    entry["registry"] = p.get("registry", "claude-plugins-official")
            plugins.append(entry)
    return {"marketplaces": marketplaces, "plugins": plugins}


def check_dependencies(plugin_name: str, marketplace: str = "softwaresoftware-plugins") -> dict:
    """Check which dependencies a plugin has and their satisfaction status.

    Returns:
        {
            "plugin": str,
            "satisfied": list[str],     — capabilities that are met
            "missing": list[str],       — required capabilities without a provider
            "optional_missing": list[str] — optional capabilities without a provider
        }
    """
    plugin = registry.find_marketplace_plugin(plugin_name, marketplace)
    if not plugin:
        return {
            "plugin": plugin_name,
            "error": f"Plugin '{plugin_name}' not found in marketplace",
            "satisfied": [],
            "missing": [],
            "optional_missing": [],
        }

    requires = plugin.get("requires", [])
    optional = plugin.get("optional", [])
    built_in = plugin.get("built_in_capabilities", [])

    satisfied = list(built_in)
    missing = []
    optional_missing = []

    for cap in requires:
        if cap in built_in:
            continue
        elif _mcp_satisfies(cap):
            satisfied.append(cap)
        elif _has_installed_provider(cap, marketplace):
            satisfied.append(cap)
        else:
            missing.append(cap)

    for cap in optional:
        if cap in built_in:
            continue
        elif _mcp_satisfies(cap):
            satisfied.append(cap)
        elif _has_installed_provider(cap, marketplace):
            satisfied.append(cap)
        else:
            optional_missing.append(cap)

    result = {
        "plugin": plugin_name,
        "satisfied": satisfied,
        "missing": missing,
        "optional_missing": optional_missing,
    }
    telemetry.send_event(
        "resolve",
        plugin_name=plugin_name,
        capabilities_satisfied=satisfied,
        capabilities_missing=missing,
    )
    return result


def resolve(capability: str, marketplace: str = "softwaresoftware-plugins") -> list[dict]:
    """Find and rank providers for a capability based on environment match.

    Returns:
        List of providers sorted by match quality (best first). Each entry:
        {
            "name": str,
            "match": bool,          — all environment conditions met
            "match_details": dict,  — per-condition results
            "installed": bool
        }
    """
    providers = registry.get_providers(capability, marketplace)
    if not providers:
        return []

    # Gather environment requirements from all candidates
    env_reqs = [p.get("environment", {}) for p in providers if p.get("environment")]
    facts = probes.gather_facts(env_reqs)

    ranked = []
    for provider in providers:
        env = provider.get("environment", {})
        match_details = {}
        all_match = True

        for key, value in env.items():
            # List values match if any individual value matches
            if isinstance(value, list):
                any_matched = any(facts.get(f"{key}:{v}", False) for v in value)
                match_details[key] = any_matched
                if not any_matched:
                    all_match = False
            else:
                fact_key = f"{key}:{value}"
                matched = facts.get(fact_key, False)
                match_details[fact_key] = matched
                if not matched:
                    all_match = False

        # No environment requirements = universal match
        if not env:
            all_match = True

        ranked.append({
            "name": provider["name"],
            "description": provider.get("description", ""),
            "version": provider.get("version", ""),
            "match": all_match,
            "match_details": match_details,
            "installed": registry.is_plugin_installed(provider["name"]),
            "external": provider.get("external", False),
            "source": provider.get("source", {}),
        })

    # Sort: matched first, then local before external, then installed first
    ranked.sort(key=lambda p: (not p["match"], p.get("external", False), not p["installed"]))
    return ranked


def get_install_plan(plugin_name: str, marketplace: str | None = None) -> dict:
    """Generate an ordered install plan for a plugin and its dependencies.

    For softwaresoftware-plugins: auto-selects the best provider for each missing
    capability. Transitively resolves dependencies of selected providers.
    Install order is topologically sorted — dependencies before dependents.

    For other marketplaces: passthrough install with no capability resolution.

    Supports 'name@marketplace' syntax to target a specific marketplace.

    Returns:
        {
            "plugin": str,
            "install_order": list[dict],  — ordered list of what to install
            "already_satisfied": list[str],
            "no_provider_available": list[str],  — capabilities with no matching provider
            "marketplace": str,  — source marketplace
        }
    """
    t0 = time.monotonic()

    # Resolve which marketplace the plugin belongs to
    if marketplace:
        resolved_marketplace = marketplace
    else:
        _, resolved_marketplace = registry.find_plugin_any_marketplace(plugin_name)
        # Strip @marketplace from name if present
        if "@" in plugin_name:
            plugin_name = plugin_name.rsplit("@", 1)[0]

    if not resolved_marketplace:
        telemetry.send_event("error", plugin_name=plugin_name, error_message="Plugin not found in any marketplace", error_context="get_install_plan")
        return {"plugin": plugin_name, "error": f"Plugin '{plugin_name}' not found in any installed marketplace", "install_order": []}

    # Non-softwaresoftware marketplaces: passthrough install, no capability resolution
    if resolved_marketplace != "softwaresoftware-plugins":
        is_installed = registry.is_plugin_installed(plugin_name)
        install_order = []
        if not is_installed:
            install_order.append({
                "plugin": plugin_name,
                "capability": None,
                "reason": f"Direct install from {resolved_marketplace}",
                "required": True,
                "passthrough": True,
                "marketplace": resolved_marketplace,
            })
        duration_ms = int((time.monotonic() - t0) * 1000)
        telemetry.send_event(
            "install",
            plugin_name=plugin_name,
            providers_selected=[plugin_name] if install_order else [],
            capabilities_satisfied=[],
            capabilities_missing=[],
            duration_ms=duration_ms,
        )
        return {
            "plugin": plugin_name,
            "target_installed": is_installed,
            "install_order": install_order,
            "already_satisfied": [],
            "no_provider_available": [],
            "marketplace": resolved_marketplace,
        }

    # softwaresoftware-plugins: full capability resolution
    deps = check_dependencies(plugin_name, resolved_marketplace)
    if "error" in deps:
        telemetry.send_event("error", plugin_name=plugin_name, error_message=deps["error"], error_context="get_install_plan")
        return {"plugin": plugin_name, "error": deps["error"], "install_order": []}

    install_order = []
    no_provider = []
    already_satisfied = list(deps["satisfied"])
    # Track plugins already planned for install to avoid duplicates
    planned = set()
    # Track resolution stack for cycle detection
    resolving = set()

    def _resolve_caps(caps, required_caps):
        """Resolve a list of capabilities, recursively resolving provider deps."""
        for cap in caps:
            if cap in already_satisfied:
                continue
            if cap in resolving:
                continue  # cycle detected, skip

            # Check if a third-party MCP already satisfies this
            mcp_name = _mcp_satisfies(cap)
            if mcp_name:
                already_satisfied.append(cap)
                continue

            providers = resolve(cap, resolved_marketplace)
            matched = [p for p in providers if p["match"] and not p["installed"]]

            if matched:
                best = matched[0]
                if best["name"] in planned:
                    continue

                # Recursively resolve this provider's dependencies first
                provider_plugin = registry.find_marketplace_plugin(best["name"], resolved_marketplace)
                if provider_plugin:
                    provider_requires = provider_plugin.get("requires", [])
                    provider_optional = provider_plugin.get("optional", [])
                    if provider_requires or provider_optional:
                        resolving.add(cap)
                        _resolve_caps(provider_requires, set(provider_requires))
                        _resolve_caps(provider_optional, set())
                        resolving.discard(cap)

                if best["name"] not in planned:
                    planned.add(best["name"])
                    entry = {
                        "plugin": best["name"],
                        "capability": cap,
                        "reason": f"Provides '{cap}' — best environment match",
                        "required": cap in required_caps,
                    }
                    if best.get("external"):
                        entry["external"] = True
                        entry["registry"] = best.get("registry", "claude-plugins-official")
                    install_order.append(entry)
            elif not any(p["installed"] for p in providers):
                # Check if a known third-party MCP could satisfy this
                mcp_opts = _mcp_candidates(cap)
                if mcp_opts:
                    best_mcp = mcp_opts[0]
                    if best_mcp["name"] not in planned:
                        planned.add(best_mcp["name"])
                        install_order.append({
                            "plugin": best_mcp["name"],
                            "capability": cap,
                            "reason": f"Provides '{cap}' — third-party MCP",
                            "required": cap in required_caps,
                            "mcp_provider": True,
                            "install_command": best_mcp["install_command"],
                            "description": best_mcp["description"],
                        })
                elif cap not in no_provider:
                    no_provider.append(cap)

    required_set = set(deps["missing"])
    _resolve_caps(deps["missing"] + deps["optional_missing"], required_set)

    # Include external registry metadata if the target or any dep is external
    external_registries = {}
    all_registries = registry.get_external_registries(resolved_marketplace)

    # Check the target plugin itself
    target_plugin = registry.find_marketplace_plugin(plugin_name, resolved_marketplace)
    target_is_external = target_plugin.get("external", False) if target_plugin else False
    if target_is_external:
        reg_name = target_plugin.get("registry", "")
        if reg_name and reg_name not in external_registries:
            reg_info = all_registries.get(reg_name)
            if reg_info:
                external_registries[reg_name] = reg_info

    # Check deps in install_order
    for entry in install_order:
        if entry.get("external"):
            reg_name = entry.get("registry", "")
            if reg_name and reg_name not in external_registries:
                reg_info = all_registries.get(reg_name)
                if reg_info:
                    external_registries[reg_name] = reg_info

    target_installed = registry.is_plugin_installed(plugin_name)
    result = {
        "plugin": plugin_name,
        "target_installed": target_installed,
        "target_external": target_is_external,
        "target_registry": target_plugin.get("registry", "") if target_is_external else None,
        "install_order": install_order,
        "already_satisfied": already_satisfied,
        "no_provider_available": no_provider,
        "marketplace": resolved_marketplace,
    }
    # When already installed with nothing to do, include post-install info
    # so the skill can suggest setup if it hasn't been run yet
    if target_installed and not install_order:
        skills = registry.get_plugin_skills(plugin_name)
        result["post_install"] = {
            "skills": skills,
            "has_setup": "setup" in skills,
        }
    if external_registries:
        result["external_registries"] = external_registries
    duration_ms = int((time.monotonic() - t0) * 1000)
    telemetry.send_event(
        "install",
        plugin_name=plugin_name,
        providers_selected=[i["plugin"] for i in install_order],
        capabilities_satisfied=already_satisfied,
        capabilities_missing=no_provider,
        duration_ms=duration_ms,
    )
    return result


def get_uninstall_plan(plugin_name: str, marketplace: str = "softwaresoftware-plugins") -> dict:
    """Generate an uninstall plan for a plugin and its orphaned dependencies.

    Identifies which dependencies were installed to support this plugin and can
    be safely removed — i.e., no other installed plugin requires the capability
    they provide.

    Returns:
        {
            "plugin": str,
            "remove_order": list[dict],  — ordered list of what to remove (dependents first)
            "kept_deps": list[dict],     — deps kept because other plugins need them
        }
    """
    plugin = registry.find_marketplace_plugin(plugin_name, marketplace)
    if not plugin:
        return {
            "plugin": plugin_name,
            "error": f"Plugin '{plugin_name}' not found in marketplace",
            "remove_order": [],
        }

    if not registry.is_plugin_installed(plugin_name):
        return {
            "plugin": plugin_name,
            "error": f"Plugin '{plugin_name}' is not installed",
            "remove_order": [],
        }

    installed = registry.get_installed_plugins()
    all_plugins = registry.get_marketplace_plugins(marketplace)

    # Build set of installed plugin names (excluding the target)
    installed_names = {k.split("@")[0] for k in installed}
    other_installed = installed_names - {plugin_name}

    # Find all capabilities the target plugin requires/optionally uses
    target_caps = plugin.get("requires", []) + plugin.get("optional", [])

    remove_order = [{"plugin": plugin_name, "reason": "target plugin"}]
    kept_deps = []
    checked = {plugin_name}

    def _find_orphaned_deps(caps, excluding):
        """Find installed providers for caps that no other plugin needs."""
        for cap in caps:
            # Find the installed provider for this capability
            providers = registry.get_providers(cap, marketplace)
            installed_provider = None
            for p in providers:
                if p["name"] in installed_names and p["name"] not in excluding:
                    installed_provider = p
                    break

            if not installed_provider:
                continue

            pname = installed_provider["name"]
            if pname in checked:
                continue
            checked.add(pname)

            # Check if any OTHER installed plugin (not being removed) needs this cap
            plugins_being_removed = {r["plugin"] for r in remove_order}
            remaining = other_installed - plugins_being_removed

            needed_by_others = False
            for other_name in remaining:
                other_plugin = registry.find_marketplace_plugin(other_name, marketplace)
                if not other_plugin:
                    continue
                other_caps = (
                    other_plugin.get("requires", [])
                    + other_plugin.get("optional", [])
                )
                if cap in other_caps:
                    needed_by_others = True
                    break

            if needed_by_others:
                kept_deps.append({
                    "plugin": pname,
                    "capability": cap,
                    "reason": f"Still needed by other installed plugins",
                })
            else:
                remove_order.append({
                    "plugin": pname,
                    "capability": cap,
                    "reason": f"Orphaned — provided '{cap}' only for {plugin_name}",
                })
                # Recursively check this provider's own deps
                provider_entry = registry.find_marketplace_plugin(pname, marketplace)
                if provider_entry:
                    sub_caps = (
                        provider_entry.get("requires", [])
                        + provider_entry.get("optional", [])
                    )
                    if sub_caps:
                        _find_orphaned_deps(sub_caps, checked)

    _find_orphaned_deps(target_caps, checked)

    telemetry.send_event(
        "uninstall",
        plugin_name=plugin_name,
        plugins_removed=[r["plugin"] for r in remove_order],
        plugins_kept=[k["plugin"] for k in kept_deps],
    )
    return {
        "plugin": plugin_name,
        "remove_order": remove_order,
        "kept_deps": kept_deps,
    }


def _has_installed_provider(capability: str, marketplace: str) -> bool:
    """Check if any installed plugin provides a capability."""
    providers = registry.get_providers(capability, marketplace)
    return any(registry.is_plugin_installed(p["name"]) for p in providers)
