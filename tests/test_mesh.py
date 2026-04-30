"""Tests for the session-bridge mesh client.

The resolver consults the mesh to find hosts that advertise capabilities
no local plugin can satisfy. The mesh client is a thin urllib wrapper —
robust to the daemon being absent (returns []) so the resolver degrades
to local-only when there is no mesh.
"""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import mesh


def _fake_response(payload):
    """Build a context-manager mock for urllib.request.urlopen."""
    cm = MagicMock()
    cm.__enter__.return_value = MagicMock(read=lambda: json.dumps(payload).encode())
    cm.__exit__.return_value = False
    return cm


def test_list_hosts_returns_parsed_response():
    payload = [
        {"host": "local-yocal", "self": True, "capabilities": ["lan-access"]},
        {"host": "pixel-7-pro", "self": False, "capabilities": ["sms-send"], "ip": "100.74.17.91"},
    ]
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        hosts = mesh.list_hosts()
    assert len(hosts) == 2
    assert hosts[0]["host"] == "local-yocal"
    assert hosts[1]["capabilities"] == ["sms-send"]


def test_list_hosts_returns_empty_on_network_error():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        assert mesh.list_hosts() == []


def test_list_hosts_returns_empty_on_http_error():
    err = urllib.error.HTTPError("http://x", 500, "Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        assert mesh.list_hosts() == []


def test_list_hosts_returns_empty_on_invalid_json():
    cm = MagicMock()
    cm.__enter__.return_value = MagicMock(read=lambda: b"not json")
    cm.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=cm):
        assert mesh.list_hosts() == []


def test_find_host_for_capability_returns_first_match():
    payload = [
        {"host": "local-yocal", "self": True, "capabilities": []},
        {"host": "pixel-7-pro", "self": False, "capabilities": ["sms-send", "gps"]},
        {"host": "lab-mac", "self": False, "capabilities": ["xcode"]},
    ]
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        host = mesh.find_host_for_capability("sms-send")
    assert host == "pixel-7-pro"


def test_find_host_for_capability_returns_none_when_no_match():
    payload = [
        {"host": "local-yocal", "self": True, "capabilities": ["lan-access"]},
    ]
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        assert mesh.find_host_for_capability("sms-send") is None


def test_find_host_for_capability_returns_none_when_mesh_unreachable():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("nope")):
        assert mesh.find_host_for_capability("sms-send") is None


def test_find_host_prefers_self_when_self_advertises():
    """If the local daemon's self block claims the capability, no need to forward."""
    payload = [
        {"host": "local-yocal", "self": True, "capabilities": ["sms-send"]},
        {"host": "pixel-7-pro", "self": False, "capabilities": ["sms-send"]},
    ]
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        host = mesh.find_host_for_capability("sms-send")
    # Self-host wins when both advertise — same host = no cross-host hop needed.
    assert host == "local-yocal"
