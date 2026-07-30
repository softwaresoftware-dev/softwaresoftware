"""Tests for resolver.py — dependency diff engine."""

import json

import resolver


def test_check_dependencies_satisfied(mock_home, marketplace_json, installed_plugins):
    """Cardwatch with notify-linux installed — notification should be satisfied."""
    result = resolver.check_dependencies("cardwatch")
    assert "notification" in result["satisfied"]
    assert result["missing"] == []
    assert "scheduling" in result["optional_missing"]


def test_resolve_notification(mock_home, marketplace_json, monkeypatch):
    """Should rank notify-linux higher on linux."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "notify-send")

    providers = resolver.resolve("notification")
    assert len(providers) == 2
    # notify-linux should match on linux
    linux = next(p for p in providers if p["name"] == "notify-linux")
    macos = next(p for p in providers if p["name"] == "notify-macos")
    assert linux["match"] is True
    assert macos["match"] is False
    # Matched should sort first
    assert providers[0]["name"] == "notify-linux"


def test_resolve_list_environment(mock_home, marketplace_json, monkeypatch):
    """Provider with os: ["linux", "darwin", "windows"] should match on any of those."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "darwin")

    providers = resolver.resolve("daemon")
    assert len(providers) == 1
    assert providers[0]["name"] == "daemon-manager"
    assert providers[0]["match"] is True


def test_resolve_list_environment_no_match(mock_home, marketplace_json, monkeypatch):
    """Provider with os list should NOT match on unsupported OS."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "freebsd")

    providers = resolver.resolve("daemon")
    assert len(providers) == 1
    assert providers[0]["match"] is False


def test_get_install_plan(mock_home, marketplace_json, monkeypatch):
    """Should auto-select notify-linux on linux."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "notify-send")

    plan = resolver.get_install_plan("cardwatch")
    assert plan["plugin"] == "cardwatch"
    assert len(plan["install_order"]) >= 1
    first = plan["install_order"][0]
    assert first["plugin"] == "notify-linux"
    assert first["capability"] == "notification"
    assert first["required"] is True


def test_get_install_plan_already_satisfied(mock_home, marketplace_json, installed_plugins):
    """With notify-linux installed, notification should be in already_satisfied."""
    plan = resolver.get_install_plan("cardwatch")
    assert "notification" in plan["already_satisfied"]
    # No install needed for notification
    notification_installs = [i for i in plan["install_order"] if i["capability"] == "notification"]
    assert len(notification_installs) == 0


def test_get_install_plan_target_installed(mock_home, marketplace_json, installed_plugins):
    """Plan should report target_installed=True when the plugin is already installed."""
    plan = resolver.get_install_plan("notify-linux")
    assert plan["target_installed"] is True


def test_get_install_plan_target_installed_has_post_install(mock_home, marketplace_json, installed_plugins):
    """When target is installed with no deps to add, post_install should include skill info."""
    # Create a setup skill for notify-linux
    install_path = mock_home / ".claude" / "plugins" / "cache" / "softwaresoftware-plugins" / "notify-linux" / "2.0.0"
    setup_dir = install_path / "skills" / "setup"
    setup_dir.mkdir(parents=True)
    (setup_dir / "SKILL.md").write_text("# setup")

    plan = resolver.get_install_plan("notify-linux")
    assert plan["target_installed"] is True
    assert plan["install_order"] == []
    assert "post_install" in plan
    assert plan["post_install"]["has_setup"] is True
    assert "setup" in plan["post_install"]["skills"]


def test_get_install_plan_target_installed_no_setup(mock_home, marketplace_json, installed_plugins):
    """When target is installed but has no setup skill, post_install.has_setup should be False."""
    plan = resolver.get_install_plan("notify-linux")
    assert plan["target_installed"] is True
    assert "post_install" in plan
    assert plan["post_install"]["has_setup"] is False


def test_get_install_plan_target_not_installed(mock_home, marketplace_json):
    """Plan should report target_installed=False when the plugin is not installed."""
    plan = resolver.get_install_plan("cardwatch")
    assert plan["target_installed"] is False


def test_get_install_plan_transitive(mock_home, marketplace_json, monkeypatch):
    """Transitive deps: test-app -> browser-automation (test-browser) -> daemon (test-daemon).

    Install order must have test-daemon before test-browser.
    """
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")

    plan = resolver.get_install_plan("test-app")
    assert plan["plugin"] == "test-app"
    names = [entry["plugin"] for entry in plan["install_order"]]
    assert "test-daemon" in names
    assert "test-browser" in names
    assert names.index("test-daemon") < names.index("test-browser")


def test_resolve_external_ranked_after_local(mock_home, marketplace_json_with_external, monkeypatch):
    """External providers should rank after local ones when both match."""
    import probes
    # darwin so local-browser matches, npx so ext-playwright also matches
    monkeypatch.setattr(probes, "probe_os", lambda: "darwin")
    monkeypatch.setattr(probes, "probe_binary", lambda name: True)

    providers = resolver.resolve("browser-automation")
    local = [p for p in providers if not p.get("external")]
    external = [p for p in providers if p.get("external")]
    assert len(local) >= 1
    assert len(external) >= 1
    # Both match, but local should come before external
    first_external_idx = next(i for i, p in enumerate(providers) if p.get("external"))
    first_local_idx = next(i for i, p in enumerate(providers) if not p.get("external"))
    assert first_local_idx < first_external_idx


def test_install_plan_external_has_registry(mock_home, marketplace_json_with_external, monkeypatch):
    """Install plan entries for external providers should include registry info."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "npx")

    plan = resolver.get_install_plan("test-needs-browser")
    assert len(plan["install_order"]) >= 1
    ext_entry = next(
        (e for e in plan["install_order"] if e.get("external")),
        None,
    )
    assert ext_entry is not None
    assert ext_entry["registry"] == "claude-plugins-official"
    assert ext_entry["capability"] == "browser-automation"
    # Plan should include external_registries with repo info
    assert "external_registries" in plan
    assert "claude-plugins-official" in plan["external_registries"]
    assert plan["external_registries"]["claude-plugins-official"]["repo"] == "anthropics/claude-plugins-official"


def test_transitive_optional_skips_already_installed_provider(mock_home, monkeypatch):
    """When a provider's transitive optional dep is already satisfied by an installed plugin,
    don't recommend a new external install. Regression: was suggesting deploy-on-aws
    even though nginx-cloudflare-deploy was already installed."""
    import probes
    mp_path = mock_home / ".claude" / "plugins" / "marketplaces" / "softwaresoftware-plugins" / ".claude-plugin" / "marketplace.json"
    mp_path.parent.mkdir(parents=True, exist_ok=True)
    mp_path.write_text(json.dumps({
        "name": "softwaresoftware-plugins",
        "plugins": [
            {"name": "app", "requires": ["routing"], "optional": [], "provides": [], "environment": {}},
            {"name": "router-with-optional-deploy", "requires": [], "optional": ["deploy"],
             "provides": ["routing"], "environment": {}},
            {"name": "local-deploy", "requires": [], "optional": [],
             "provides": ["deploy"], "environment": {"binary": "nginx"}},
            {"name": "external-deploy",
             "source": {"source": "url", "url": "https://github.com/x/y.git"},
             "registry": "other",
             "requires": [], "optional": [],
             "provides": ["deploy"], "environment": {"binary": "awscli"},
             "external": True},
        ],
        "external_registries": {"other": {"repo": "x/y"}},
    }))
    # local-deploy is already installed
    installed_path = mock_home / ".claude" / "plugins" / "cache" / "softwaresoftware-plugins" / "local-deploy" / "1.0.0"
    installed_path.mkdir(parents=True)
    (installed_path / ".claude-plugin").mkdir()
    (installed_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "local-deploy", "version": "1.0.0"}))
    inst_idx = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    inst_idx.write_text(json.dumps({
        "version": 2,
        "plugins": {
            "local-deploy@softwaresoftware-plugins": [
                {"scope": "user", "installPath": str(installed_path), "version": "1.0.0"}
            ]
        },
    }))
    # Both local-deploy (nginx) and external-deploy (awscli) match env
    monkeypatch.setattr(probes, "probe_binary", lambda name: name in ("nginx", "awscli"))

    plan = resolver.get_install_plan("app")
    plugins_to_install = [e["plugin"] for e in plan["install_order"]]
    assert "external-deploy" not in plugins_to_install, (
        "Should not recommend installing external-deploy when local-deploy is already installed"
    )
    assert "deploy" in plan["already_satisfied"]


def test_install_plan_surfaces_alternatives(mock_home, marketplace_json_with_external, monkeypatch):
    """When multiple providers match the environment, install_order entry lists the others as alternatives with ready=True."""
    import probes
    # Both local-browser (os: darwin) and ext-playwright (binary: npx) match
    monkeypatch.setattr(probes, "probe_os", lambda: "darwin")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "npx")

    plan = resolver.get_install_plan("test-needs-browser")
    browser_entry = next(
        e for e in plan["install_order"] if e["capability"] == "browser-automation"
    )
    # Local wins (sort: local before external), and external is surfaced as alternative
    assert browser_entry["plugin"] == "local-browser"
    assert "alternatives" in browser_entry
    alt_names = [a["plugin"] for a in browser_entry["alternatives"]]
    assert "ext-playwright" in alt_names
    ext_alt = next(a for a in browser_entry["alternatives"] if a["plugin"] == "ext-playwright")
    assert ext_alt["external"] is True
    assert ext_alt["registry"] == "claude-plugins-official"
    assert ext_alt["ready"] is True


def test_install_plan_surfaces_unmet_alternatives(mock_home, marketplace_json_with_external, monkeypatch):
    """Providers whose env probes don't pass are still surfaced as ready=False alternatives with unmet probes."""
    import probes
    # Only local-browser matches (darwin); ext-playwright needs npx which is missing
    monkeypatch.setattr(probes, "probe_os", lambda: "darwin")
    monkeypatch.setattr(probes, "probe_binary", lambda name: False)

    plan = resolver.get_install_plan("test-needs-browser")
    browser_entry = next(
        e for e in plan["install_order"] if e["capability"] == "browser-automation"
    )
    assert browser_entry["plugin"] == "local-browser"
    assert "alternatives" in browser_entry
    ext_alt = next(a for a in browser_entry["alternatives"] if a["plugin"] == "ext-playwright")
    assert ext_alt["ready"] is False
    assert "binary:npx" in ext_alt["unmet_probes"]
    assert ext_alt["external"] is True
    assert ext_alt["registry"] == "claude-plugins-official"


def test_install_plan_no_alternatives_when_single_provider(mock_home, monkeypatch):
    """When only one provider exists for a capability, no alternatives field is emitted."""
    import probes
    import json as _json
    mp_path = mock_home / ".claude" / "plugins" / "marketplaces" / "softwaresoftware-plugins" / ".claude-plugin" / "marketplace.json"
    mp_path.parent.mkdir(parents=True, exist_ok=True)
    mp_path.write_text(_json.dumps({
        "name": "softwaresoftware-plugins",
        "plugins": [
            {"name": "consumer", "requires": ["solo"], "optional": [], "provides": [], "environment": {}},
            {"name": "only-provider", "requires": [], "optional": [], "provides": ["solo"], "environment": {}},
        ],
    }))
    plan = resolver.get_install_plan("consumer")
    entry = next(e for e in plan["install_order"] if e["capability"] == "solo")
    assert entry["plugin"] == "only-provider"
    assert "alternatives" not in entry


def test_install_plan_alternative_external_routes_to_correct_registry(mock_home, monkeypatch):
    """Alternative external providers must carry their own registry, not default to claude-plugins-official."""
    import probes
    mp_path = mock_home / ".claude" / "plugins" / "marketplaces" / "softwaresoftware-plugins" / ".claude-plugin" / "marketplace.json"
    mp_path.parent.mkdir(parents=True, exist_ok=True)
    mp_path.write_text(json.dumps({
        "name": "softwaresoftware-plugins",
        "plugins": [
            {
                "name": "consumer",
                "source": {"source": "github", "repo": "x/consumer"},
                "requires": ["kb"],
                "optional": [],
                "provides": [],
                "environment": {},
            },
            {
                "name": "local-kb",
                "source": {"source": "github", "repo": "x/local-kb"},
                "requires": [], "optional": [],
                "provides": ["kb"],
                "environment": {"binary": "git"},
            },
            {
                "name": "third-party-kb",
                "source": {"source": "url", "url": "https://github.com/other/other-marketplace.git"},
                "registry": "other-marketplace",
                "requires": [], "optional": [],
                "provides": ["kb"],
                "environment": {"binary": "git"},
                "external": True,
            },
        ],
        "external_registries": {
            "other-marketplace": {"repo": "other/other-marketplace", "description": "Other"}
        },
    }))
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "git")

    plan = resolver.get_install_plan("consumer")
    kb_entry = next(e for e in plan["install_order"] if e["capability"] == "kb")
    assert kb_entry["plugin"] == "local-kb"
    alt = next(a for a in kb_entry["alternatives"] if a["plugin"] == "third-party-kb")
    assert alt["registry"] == "other-marketplace"


def test_get_install_plan_transitive_no_duplicates(mock_home, marketplace_json, monkeypatch):
    """Transitive resolution should not produce duplicate entries."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")

    plan = resolver.get_install_plan("test-app")
    names = [entry["plugin"] for entry in plan["install_order"]]
    assert len(names) == len(set(names))


def test_mcp_satisfies_capability(mock_home, marketplace_json, monkeypatch):
    """When a known third-party MCP is loaded, its capabilities are satisfied."""
    import probes
    # Simulate Slack MCP being loaded
    monkeypatch.setattr(probes, "probe_mcp", lambda name: name == "slack")

    result = resolver.check_dependencies("cardwatch")
    # Slack provides notification, so it should be satisfied
    assert "notification" in result["satisfied"]
    assert result["missing"] == []


def test_mcp_satisfies_skips_install(mock_home, marketplace_json, monkeypatch):
    """Install plan should not install a provider when a loaded MCP satisfies the capability."""
    import probes
    monkeypatch.setattr(probes, "probe_mcp", lambda name: name == "slack")

    plan = resolver.get_install_plan("cardwatch")
    assert "notification" in plan["already_satisfied"]
    notification_installs = [i for i in plan["install_order"] if i["capability"] == "notification"]
    assert len(notification_installs) == 0


def test_mcp_satisfies_not_loaded(mock_home, marketplace_json, monkeypatch):
    """When no known MCP is loaded, capabilities fall back to marketplace providers."""
    import probes
    monkeypatch.setattr(probes, "probe_mcp", lambda name: False)
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "notify-send")

    plan = resolver.get_install_plan("cardwatch")
    # Should fall back to installing notify-linux
    assert any(i["plugin"] == "notify-linux" for i in plan["install_order"])


def test_mcp_provider_in_install_plan(mock_home, marketplace_json, monkeypatch):
    """When no marketplace provider matches but a known MCP can satisfy, include it."""
    import probes
    monkeypatch.setattr(probes, "probe_mcp", lambda name: False)
    # No OS match for any marketplace notification provider
    monkeypatch.setattr(probes, "probe_os", lambda: "freebsd")
    monkeypatch.setattr(probes, "probe_binary", lambda name: False)

    plan = resolver.get_install_plan("cardwatch")
    mcp_entries = [i for i in plan["install_order"] if i.get("mcp_provider")]
    assert len(mcp_entries) >= 1
    slack_entry = next((e for e in mcp_entries if e["plugin"] == "slack"), None)
    if slack_entry:
        assert slack_entry["mcp_provider"] is True
        assert "install_command" in slack_entry
        assert slack_entry["capability"] == "notification"


# --- Multi-marketplace tests ---


def test_list_all_marketplaces(mock_home, marketplace_json, other_marketplace):
    """list_marketplace_plugins with no args returns plugins from all marketplaces."""
    result = resolver.list_marketplace_plugins()
    assert "softwaresoftware-plugins" in result["marketplaces"]
    assert "other-plugins" in result["marketplaces"]
    names = [p["name"] for p in result["plugins"]]
    # Should include plugins from both marketplaces
    assert "cardwatch" in names
    assert "cool-tool" in names


def test_list_single_marketplace(mock_home, marketplace_json, other_marketplace):
    """list_marketplace_plugins with a specific marketplace only returns those plugins."""
    result = resolver.list_marketplace_plugins("other-plugins")
    assert result["marketplaces"] == ["other-plugins"]
    names = [p["name"] for p in result["plugins"]]
    assert "cool-tool" in names
    assert "cardwatch" not in names


def test_list_plugins_have_marketplace_field(mock_home, marketplace_json, other_marketplace):
    """Each plugin entry should include its source marketplace."""
    result = resolver.list_marketplace_plugins()
    for p in result["plugins"]:
        assert "marketplace" in p
    cardwatch = next(p for p in result["plugins"] if p["name"] == "cardwatch")
    assert cardwatch["marketplace"] == "softwaresoftware-plugins"
    cool_tool = next(p for p in result["plugins"] if p["name"] == "cool-tool")
    assert cool_tool["marketplace"] == "other-plugins"


def test_list_no_duplicates(mock_home, marketplace_json, other_marketplace):
    """Plugins should not appear twice even if name collides across marketplaces."""
    result = resolver.list_marketplace_plugins()
    names = [p["name"] for p in result["plugins"]]
    assert len(names) == len(set(names))


def test_install_plan_passthrough(mock_home, marketplace_json, other_marketplace):
    """Plugins from non-softwaresoftware marketplaces get a passthrough install plan."""
    plan = resolver.get_install_plan("cool-tool")
    assert plan["marketplace"] == "other-plugins"
    assert len(plan["install_order"]) == 1
    entry = plan["install_order"][0]
    assert entry["passthrough"] is True
    assert entry["marketplace"] == "other-plugins"
    assert plan["no_provider_available"] == []


def test_install_plan_passthrough_already_installed(mock_home, marketplace_json, other_marketplace, monkeypatch):
    """Passthrough plan for an already-installed plugin has empty install_order."""
    import registry
    monkeypatch.setattr(registry, "is_plugin_installed", lambda name: name == "cool-tool")
    plan = resolver.get_install_plan("cool-tool")
    assert plan["target_installed"] is True
    assert plan["install_order"] == []


def test_install_plan_at_marketplace_syntax(mock_home, marketplace_json, other_marketplace):
    """name@marketplace syntax targets the specified marketplace."""
    plan = resolver.get_install_plan("cool-tool@other-plugins")
    assert plan["plugin"] == "cool-tool"
    assert plan["marketplace"] == "other-plugins"
    assert plan["install_order"][0]["passthrough"] is True


def test_install_plan_softwaresoftware_gets_resolution(mock_home, marketplace_json, other_marketplace, monkeypatch):
    """Plugins from softwaresoftware-plugins still get full capability resolution."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "notify-send")

    plan = resolver.get_install_plan("cardwatch")
    assert plan["marketplace"] == "softwaresoftware-plugins"
    # Should have capability resolution, not passthrough
    assert any(e.get("capability") == "notification" for e in plan["install_order"])
    assert not any(e.get("passthrough") for e in plan["install_order"])


def test_install_plan_not_found_anywhere(mock_home, marketplace_json, other_marketplace):
    """Plugin not in any marketplace returns an error."""
    plan = resolver.get_install_plan("nonexistent-plugin")
    assert "error" in plan
    assert "not found" in plan["error"]


def test_softwaresoftware_searched_first(mock_home, marketplace_json, other_marketplace):
    """When a plugin exists in softwaresoftware-plugins, it should be found there first."""
    import registry
    plugin, mp = registry.find_plugin_any_marketplace("cardwatch")
    assert mp == "softwaresoftware-plugins"
    assert plugin["name"] == "cardwatch"


def test_find_in_other_marketplace(mock_home, marketplace_json, other_marketplace):
    """Plugins only in other marketplaces are found there."""
    import registry
    plugin, mp = registry.find_plugin_any_marketplace("cool-tool")
    assert mp == "other-plugins"
    assert plugin["name"] == "cool-tool"


def test_find_not_found(mock_home, marketplace_json, other_marketplace):
    """Plugin not in any marketplace returns (None, None)."""
    import registry
    plugin, mp = registry.find_plugin_any_marketplace("nonexistent")
    assert plugin is None
    assert mp is None


# --- Post-install skill detection tests ---


def test_external_target_has_registry_metadata(mock_home, marketplace_json_with_external, monkeypatch):
    """When the target plugin is external, plan includes target_external and external_registries."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "npx")

    plan = resolver.get_install_plan("ext-playwright")
    assert plan["target_external"] is True
    assert plan["target_registry"] == "claude-plugins-official"
    assert "external_registries" in plan
    assert "claude-plugins-official" in plan["external_registries"]
    assert plan["external_registries"]["claude-plugins-official"]["repo"] == "anthropics/claude-plugins-official"


def test_non_external_target_has_no_external_flag(mock_home, marketplace_json, monkeypatch):
    """Non-external target plugins should have target_external=False."""
    import probes
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "notify-send")

    plan = resolver.get_install_plan("cardwatch")
    assert plan["target_external"] is False
    assert plan["target_registry"] is None


def test_get_plugin_skills(mock_home, marketplace_json, installed_plugins):
    """Detect skills from an installed plugin's skills directory."""
    import registry
    # Create a fake skills directory for notify-linux
    install_path = mock_home / ".claude" / "plugins" / "cache" / "softwaresoftware-plugins" / "notify-linux" / "2.0.0"
    for skill_name in ["setup", "test"]:
        skill_dir = install_path / "skills" / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill_name}")

    skills = registry.get_plugin_skills("notify-linux")
    assert skills == ["setup", "test"]


def test_get_plugin_skills_has_setup(mock_home, marketplace_json, installed_plugins):
    """has_setup detection for a plugin with a setup skill."""
    import registry
    install_path = mock_home / ".claude" / "plugins" / "cache" / "softwaresoftware-plugins" / "notify-linux" / "2.0.0"
    setup_dir = install_path / "skills" / "setup"
    setup_dir.mkdir(parents=True)
    (setup_dir / "SKILL.md").write_text("# setup")

    skills = registry.get_plugin_skills("notify-linux")
    assert "setup" in skills


def test_get_plugin_skills_no_setup(mock_home, marketplace_json, installed_plugins):
    """Plugin without a setup skill."""
    import registry
    install_path = mock_home / ".claude" / "plugins" / "cache" / "softwaresoftware-plugins" / "notify-linux" / "2.0.0"
    skill_dir = install_path / "skills" / "send"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# send")

    skills = registry.get_plugin_skills("notify-linux")
    assert "setup" not in skills
    assert "send" in skills


def test_get_plugin_skills_not_installed(mock_home, marketplace_json):
    """Skills for a non-installed plugin returns empty list."""
    import registry
    assert registry.get_plugin_skills("not-installed") == []



def test_no_provider_records_unmet_binary_probe(mock_home, monkeypatch):
    """When a capability's only provider fails a binary probe, no_provider_available
    records the provider and the unmet probe so the install skill can offer to
    install the missing binary instead of dead-ending."""
    import probes
    mp_path = mock_home / ".claude" / "plugins" / "marketplaces" / "softwaresoftware-plugins" / ".claude-plugin" / "marketplace.json"
    mp_path.parent.mkdir(parents=True, exist_ok=True)
    mp_path.write_text(json.dumps({
        "name": "softwaresoftware-plugins",
        "plugins": [
            {"name": "app", "requires": ["agent-spawning"], "optional": [],
             "provides": [], "environment": {}},
            {"name": "spawner", "requires": [], "optional": [],
             "provides": ["agent-spawning"],
             "environment": {"os": ["linux", "darwin"], "binary": "tmux"}},
        ],
    }))
    # OS matches, but tmux is not installed.
    monkeypatch.setattr(probes, "probe_os", lambda: "linux")
    monkeypatch.setattr(probes, "probe_binary", lambda name: False)

    plan = resolver.get_install_plan("app")
    assert len(plan["no_provider_available"]) == 1
    entry = plan["no_provider_available"][0]
    assert entry["capability"] == "agent-spawning"
    assert entry["required"] is True
    assert len(entry["providers"]) == 1
    prov = entry["providers"][0]
    assert prov["plugin"] == "spawner"
    assert "binary:tmux" in prov["unmet_probes"]
    # The OS probe passed, so it must NOT appear as unmet.
    assert "os" not in prov["unmet_probes"]


# --- binary list = AND semantics ---


def _write_marketplace(mock_home, plugins, external_registries=None):
    mp_path = mock_home / ".claude" / "plugins" / "marketplaces" / "softwaresoftware-plugins" / ".claude-plugin" / "marketplace.json"
    mp_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": "softwaresoftware-plugins", "plugins": plugins}
    if external_registries:
        data["external_registries"] = external_registries
    mp_path.write_text(json.dumps(data))


def test_resolve_binary_list_requires_all(mock_home, monkeypatch):
    """binary: ["tmux", "uv"] means BOTH binaries required — one missing = no match."""
    import probes
    _write_marketplace(mock_home, [
        {"name": "spawner", "requires": [], "optional": [],
         "provides": ["agent-spawning"],
         "environment": {"binary": ["tmux", "uv"]}},
    ])
    # Only uv present — must NOT match
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "uv")
    providers = resolver.resolve("agent-spawning")
    assert providers[0]["match"] is False
    # The missing binary is individually identified for remediation
    assert providers[0]["match_details"]["binary:tmux"] is False
    assert providers[0]["match_details"]["binary:uv"] is True


def test_resolve_binary_list_all_present_matches(mock_home, monkeypatch):
    import probes
    _write_marketplace(mock_home, [
        {"name": "spawner", "requires": [], "optional": [],
         "provides": ["agent-spawning"],
         "environment": {"binary": ["tmux", "uv"]}},
    ])
    monkeypatch.setattr(probes, "probe_binary", lambda name: name in ("tmux", "uv"))
    providers = resolver.resolve("agent-spawning")
    assert providers[0]["match"] is True


def test_resolve_os_list_stays_any(mock_home, monkeypatch):
    """os lists keep OR semantics — only binary lists are AND."""
    import probes
    _write_marketplace(mock_home, [
        {"name": "daemon-mgr", "requires": [], "optional": [],
         "provides": ["daemon"],
         "environment": {"os": ["linux", "darwin", "windows"]}},
    ])
    monkeypatch.setattr(probes, "probe_os", lambda: "darwin")
    providers = resolver.resolve("daemon")
    assert providers[0]["match"] is True


def test_install_plan_binary_list_missing_one_reports_unmet(mock_home, monkeypatch):
    """A provider missing one of its required binaries lands in no_provider_available
    with the specific missing binary probe."""
    import probes
    _write_marketplace(mock_home, [
        {"name": "app", "requires": ["agent-spawning"], "optional": [],
         "provides": [], "environment": {}},
        {"name": "spawner", "requires": [], "optional": [],
         "provides": ["agent-spawning"],
         "environment": {"binary": ["tmux", "uv"]}},
    ])
    monkeypatch.setattr(probes, "probe_binary", lambda name: name == "uv")
    plan = resolver.get_install_plan("app")
    assert [e["plugin"] for e in plan["install_order"]] == []
    entry = next(e for e in plan["no_provider_available"] if e["capability"] == "agent-spawning")
    prov = entry["providers"][0]
    assert "binary:tmux" in prov["unmet_probes"]
    assert "binary:uv" not in prov["unmet_probes"]


# --- malformed marketplace entries must never crash get_install_plan ---


def test_install_plan_survives_malformed_entries(mock_home, monkeypatch):
    """One malformed marketplace entry (bad env shapes, non-dict entries) must
    not break install planning for anyone."""
    _write_marketplace(mock_home, [
        {"name": "app", "requires": ["cap"], "optional": [],
         "provides": [], "environment": {}},
        # provider with garbage probe values
        {"name": "bad-provider", "requires": [], "optional": [],
         "provides": ["cap"],
         "environment": {"port": "no-colon-here", "binary": {"weird": True},
                         "totally-unknown-probe": 42}},
        # environment is not even a dict
        {"name": "worse-provider", "requires": [], "optional": [],
         "provides": ["cap"], "environment": "linux"},
        # entry is not a dict at all
        "just-a-string",
        None,
    ])
    plan = resolver.get_install_plan("app")
    assert "install_order" in plan
    # worse-provider (malformed env treated as universal) or a no_provider report —
    # either way the plan is produced without raising.
    assert isinstance(plan["no_provider_available"], list)


def test_registry_malformed_installed_entries(mock_home, marketplace_json):
    """get_plugin_manifest / get_plugin_install_path tolerate wrong-shaped entries."""
    import registry
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps({
        "version": 2,
        "plugins": {
            "notify-linux@softwaresoftware-plugins": {"installPath": "/not-a-list"},
            "cardwatch@softwaresoftware-plugins": ["just-a-string"],
        },
    }))
    assert registry.get_plugin_manifest("notify-linux@softwaresoftware-plugins") is None
    assert registry.get_plugin_manifest("cardwatch@softwaresoftware-plugins") is None
    assert registry.get_plugin_install_path("notify-linux") is None
    # is_plugin_installed still works off the keys
    assert registry.is_plugin_installed("notify-linux") is True


# --- installed-but-unmatched provider must not silently vanish ---


def test_installed_provider_env_mismatch_reported(mock_home, monkeypatch):
    """A transitive capability whose only provider is installed but no longer
    matches the environment must be reported, not silently dropped."""
    import probes
    _write_marketplace(mock_home, [
        {"name": "app", "requires": ["routing"], "optional": [],
         "provides": [], "environment": {}},
        {"name": "router", "requires": ["deploy"], "optional": [],
         "provides": ["routing"], "environment": {}},
        {"name": "deploy-provider", "requires": [], "optional": [],
         "provides": ["deploy"], "environment": {"binary": "nginx"}},
    ])
    # deploy-provider is installed, but nginx has since been removed
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps({
        "version": 2,
        "plugins": {
            "deploy-provider@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/deploy-provider", "version": "1.0.0"}
            ],
        },
    }))
    monkeypatch.setattr(probes, "probe_binary", lambda name: False)

    plan = resolver.get_install_plan("app")
    # router still gets planned for routing
    assert any(e["plugin"] == "router" for e in plan["install_order"])
    # deploy must NOT silently vanish — it's reported with a reason
    entry = next(
        (e for e in plan["no_provider_available"] if e["capability"] == "deploy"),
        None,
    )
    assert entry is not None, "capability with installed-but-unmatched provider was silently dropped"
    assert entry["required"] is True
    assert "environment no longer matches" in entry["reason"]
    prov = next(p for p in entry["providers"] if p["plugin"] == "deploy-provider")
    assert prov["installed"] is True
    assert "binary:nginx" in prov["unmet_probes"]
    assert "environment no longer matches" in prov["reason"]
