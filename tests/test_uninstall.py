"""Tests for get_uninstall_plan — reverse dependency resolution."""

import json

import pytest

import resolver


@pytest.fixture
def installed_cardwatch_and_deps(mock_home, marketplace_json):
    """Install cardwatch + notify-linux (its notification provider)."""
    data = {
        "version": 2,
        "plugins": {
            "cardwatch@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/cardwatch", "version": "2.0.0"}
            ],
            "notify-linux@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/notify-linux", "version": "2.0.0"}
            ],
        },
    }
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps(data))
    return data


@pytest.fixture
def installed_two_consumers(mock_home, marketplace_json):
    """Install cardwatch + test-notifier (both need notification) + notify-linux."""
    # Add a second notification consumer to marketplace
    mp_path = mock_home / ".claude" / "plugins" / "marketplaces" / "softwaresoftware-plugins" / ".claude-plugin" / "marketplace.json"
    mp_data = json.loads(mp_path.read_text())
    mp_data["plugins"].append({
        "name": "test-notifier",
        "source": {"source": "github", "repo": "ThatcherT/test-notifier"},
        "description": "Another app that needs notification",
        "version": "1.0.0",
        "requires": ["notification"],
        "optional": [],
        "provides": [],
        "environment": {},
    })
    mp_path.write_text(json.dumps(mp_data))

    data = {
        "version": 2,
        "plugins": {
            "cardwatch@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/cardwatch", "version": "2.0.0"}
            ],
            "test-notifier@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/test-notifier", "version": "1.0.0"}
            ],
            "notify-linux@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/notify-linux", "version": "2.0.0"}
            ],
        },
    }
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps(data))
    return data


@pytest.fixture
def installed_transitive_chain(mock_home, marketplace_json):
    """Install test-app + test-browser + test-daemon (transitive chain)."""
    data = {
        "version": 2,
        "plugins": {
            "test-app@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/test-app", "version": "1.0.0"}
            ],
            "test-browser@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/test-browser", "version": "1.0.0"}
            ],
            "test-daemon@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/test-daemon", "version": "1.0.0"}
            ],
        },
    }
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps(data))
    return data


@pytest.fixture
def installed_bundle_and_stateful_provider(mock_home, marketplace_json):
    """Install test-bundle + test-vault (a retain_on_orphan stateful provider)."""
    data = {
        "version": 2,
        "plugins": {
            "test-bundle@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/test-bundle", "version": "1.0.0"}
            ],
            "test-vault@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/test-vault", "version": "1.0.0"}
            ],
        },
    }
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps(data))
    return data


def test_uninstall_basic(installed_cardwatch_and_deps):
    """Uninstalling cardwatch should also remove notify-linux (orphaned)."""
    plan = resolver.get_uninstall_plan("cardwatch")
    assert plan["plugin"] == "cardwatch"
    names = [r["plugin"] for r in plan["remove_order"]]
    assert "cardwatch" in names
    assert "notify-linux" in names
    assert plan["kept_deps"] == []


def test_uninstall_shared_dep_kept(installed_two_consumers):
    """Uninstalling cardwatch should keep notify-linux (test-notifier still needs it)."""
    plan = resolver.get_uninstall_plan("cardwatch")
    names = [r["plugin"] for r in plan["remove_order"]]
    assert "cardwatch" in names
    assert "notify-linux" not in names
    kept_names = [k["plugin"] for k in plan["kept_deps"]]
    assert "notify-linux" in kept_names


def test_uninstall_transitive_orphans(installed_transitive_chain):
    """Uninstalling test-app should remove test-browser and test-daemon (full chain orphaned)."""
    plan = resolver.get_uninstall_plan("test-app")
    names = [r["plugin"] for r in plan["remove_order"]]
    assert "test-app" in names
    assert "test-browser" in names
    assert "test-daemon" in names
    assert plan["kept_deps"] == []


def test_uninstall_keeps_stateful_provider(installed_bundle_and_stateful_provider):
    """Uninstalling a consumer must NOT auto-remove a retain_on_orphan provider,
    even though no other installed plugin requires it. It holds user data/state."""
    plan = resolver.get_uninstall_plan("test-bundle")
    remove_names = [r["plugin"] for r in plan["remove_order"]]
    kept_names = [k["plugin"] for k in plan["kept_deps"]]
    assert "test-bundle" in remove_names
    assert "test-vault" not in remove_names
    assert "test-vault" in kept_names
    # Reason should make the stateful/explicit-removal intent clear.
    vault_kept = next(k for k in plan["kept_deps"] if k["plugin"] == "test-vault")
    assert "explicitly" in vault_kept["reason"].lower()


def test_uninstall_unflagged_orphan_still_removed(installed_cardwatch_and_deps):
    """An orphaned dep WITHOUT retain_on_orphan must still be removed —
    the safeguard is opt-in and does not change default orphan behavior."""
    plan = resolver.get_uninstall_plan("cardwatch")
    remove_names = [r["plugin"] for r in plan["remove_order"]]
    assert "notify-linux" in remove_names
    assert plan["kept_deps"] == []


def test_uninstall_not_installed(mock_home, marketplace_json):
    """Trying to uninstall a plugin that's not installed should error."""
    plan = resolver.get_uninstall_plan("cardwatch")
    assert "error" in plan
    assert "not installed" in plan["error"]


def test_uninstall_not_in_marketplace(mock_home, marketplace_json):
    """Trying to uninstall a plugin not in marketplace should error."""
    plan = resolver.get_uninstall_plan("nonexistent")
    assert "error" in plan
    assert "not found" in plan["error"]


def test_uninstall_target_first(installed_cardwatch_and_deps):
    """Target plugin should be first in remove_order."""
    plan = resolver.get_uninstall_plan("cardwatch")
    assert plan["remove_order"][0]["plugin"] == "cardwatch"


def test_uninstall_no_deps(mock_home, marketplace_json):
    """Plugin with no dependencies — just removes itself."""
    data = {
        "version": 2,
        "plugins": {
            "liteframe@softwaresoftware-plugins": [
                {"scope": "user", "installPath": "/fake/liteframe", "version": "1.1.0"}
            ],
        },
    }
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps(data))

    plan = resolver.get_uninstall_plan("liteframe")
    assert len(plan["remove_order"]) == 1
    assert plan["remove_order"][0]["plugin"] == "liteframe"
    assert plan["kept_deps"] == []

# --- name@marketplace / multi-marketplace support ---


@pytest.fixture
def installed_passthrough(mock_home, marketplace_json, other_marketplace):
    """cool-tool from other-plugins installed via passthrough."""
    data = {
        "version": 2,
        "plugins": {
            "cool-tool@other-plugins": [
                {"scope": "user", "installPath": "/fake/cool-tool", "version": "1.0.0"}
            ],
        },
    }
    installed_path = mock_home / ".claude" / "plugins" / "installed_plugins.json"
    installed_path.write_text(json.dumps(data))
    return data


def test_uninstall_at_marketplace_syntax(installed_passthrough):
    """name@marketplace targets the specified marketplace, symmetric with get_install_plan."""
    plan = resolver.get_uninstall_plan("cool-tool@other-plugins")
    assert "error" not in plan
    assert plan["plugin"] == "cool-tool"
    assert plan["marketplace"] == "other-plugins"
    assert plan["remove_order"][0]["plugin"] == "cool-tool"


def test_uninstall_other_marketplace_auto_discovered(installed_passthrough):
    """Without @marketplace, the plugin is found across installed marketplaces."""
    plan = resolver.get_uninstall_plan("cool-tool")
    assert "error" not in plan
    assert plan["marketplace"] == "other-plugins"
    assert plan["remove_order"][0]["plugin"] == "cool-tool"


def test_uninstall_default_marketplace_still_works(installed_cardwatch_and_deps):
    """softwaresoftware plugins keep full orphan resolution via the default path."""
    plan = resolver.get_uninstall_plan("cardwatch@softwaresoftware-plugins")
    names = [r["plugin"] for r in plan["remove_order"]]
    assert "cardwatch" in names
    assert "notify-linux" in names
