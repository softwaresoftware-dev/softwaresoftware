"""Dependency resolver for softwaresoftware — the core diff engine.

Computes what a plugin needs, what's satisfied, what's missing,
and auto-selects providers based on environment probes.
"""

import time

import probes
import registry
import telemetry


def list_marketplace_plugins(marketplace: str = "softwaresoftware-plugins") -> dict:
    """List all plugins available in the marketplace with install status.

    Returns:
        {
            "marketplace": str,
            "plugins": list[dict],  — name, description, version, installed, category
        }
    """
    all_plugins = registry.get_marketplace_plugins(marketplace)
    plugins = []
    for p in all_plugins:
        entry = {
            "name": p["name"],
            "description": p.get("description", ""),
            "version": p.get("version", ""),
            "installed": registry.is_plugin_installed(p["name"]),
            "category": p.get("category", ""),
            "provides": p.get("provides", []),
            "requires": p.get("requires", []),
        }
        if p.get("external"):
            entry["external"] = True
            entry["registry"] = p.get("source", {}).get("registry", "claude-plugins-official")
        plugins.append(entry)
    return {"marketplace": marketplace, "plugins": plugins}


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
        elif _has_installed_provider(cap, marketplace):
            satisfied.append(cap)
        else:
            missing.append(cap)

    for cap in optional:
        if cap in built_in:
            continue
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


def get_install_plan(plugin_name: str, marketplace: str = "softwaresoftware-plugins") -> dict:
    """Generate an ordered install plan for a plugin and its dependencies.

    Auto-selects the best provider for each missing capability.
    Transitively resolves dependencies of selected providers.
    Install order is topologically sorted — dependencies before dependents.

    Returns:
        {
            "plugin": str,
            "install_order": list[dict],  — ordered list of what to install
            "already_satisfied": list[str],
            "no_provider_available": list[str],  — capabilities with no matching provider
        }
    """
    t0 = time.monotonic()
    deps = check_dependencies(plugin_name, marketplace)
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

            providers = resolve(cap, marketplace)
            matched = [p for p in providers if p["match"] and not p["installed"]]

            if matched:
                best = matched[0]
                if best["name"] in planned:
                    continue

                # Recursively resolve this provider's dependencies first
                provider_plugin = registry.find_marketplace_plugin(best["name"], marketplace)
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
                        entry["registry"] = best.get("source", {}).get("registry", "claude-plugins-official")
                    install_order.append(entry)
            elif not any(p["installed"] for p in providers):
                if cap not in no_provider:
                    no_provider.append(cap)

    required_set = set(deps["missing"])
    _resolve_caps(deps["missing"] + deps["optional_missing"], required_set)

    result = {
        "plugin": plugin_name,
        "target_installed": registry.is_plugin_installed(plugin_name),
        "install_order": install_order,
        "already_satisfied": already_satisfied,
        "no_provider_available": no_provider,
    }
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
