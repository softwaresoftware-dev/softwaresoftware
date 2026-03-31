"""Dependency resolver for nov-dependency-resolver — the core diff engine.

Computes what a plugin needs, what's satisfied, what's missing,
and auto-selects providers based on environment probes.
"""

import probes
import registry


def check_dependencies(plugin_name: str, marketplace: str = "nov-plugins") -> dict:
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

    return {
        "plugin": plugin_name,
        "satisfied": satisfied,
        "missing": missing,
        "optional_missing": optional_missing,
    }


def resolve(capability: str, marketplace: str = "nov-plugins") -> list[dict]:
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
        })

    # Sort: matched first, then installed first
    ranked.sort(key=lambda p: (not p["match"], not p["installed"]))
    return ranked


def get_install_plan(plugin_name: str, marketplace: str = "nov-plugins") -> dict:
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
    deps = check_dependencies(plugin_name, marketplace)
    if "error" in deps:
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
                    install_order.append({
                        "plugin": best["name"],
                        "capability": cap,
                        "reason": f"Provides '{cap}' — best environment match",
                        "required": cap in required_caps,
                    })
            elif not any(p["installed"] for p in providers):
                if cap not in no_provider:
                    no_provider.append(cap)

    required_set = set(deps["missing"])
    _resolve_caps(deps["missing"] + deps["optional_missing"], required_set)

    return {
        "plugin": plugin_name,
        "install_order": install_order,
        "already_satisfied": already_satisfied,
        "no_provider_available": no_provider,
    }


def _has_installed_provider(capability: str, marketplace: str) -> bool:
    """Check if any installed plugin provides a capability."""
    providers = registry.get_providers(capability, marketplace)
    return any(registry.is_plugin_installed(p["name"]) for p in providers)
