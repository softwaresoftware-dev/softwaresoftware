"""Tests for resolver.py — dependency diff engine."""

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


