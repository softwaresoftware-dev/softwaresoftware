"""Thin client for the session-bridge daemon's host registry.

Used by the resolver to discover which hosts in the local mesh advertise
which capabilities. Degrades gracefully when the daemon is absent
(returns []), so the resolver works the same on a single-host install
as it does on a multi-host fabric.
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("SESSION_BRIDGE_URL", "http://127.0.0.1:8910")


def list_hosts(url: str = DEFAULT_URL) -> list[dict]:
    """GET /hosts from the session-bridge daemon.

    Returns the parsed list of host records, or [] if the daemon is
    unreachable, returns non-2xx, or returns a body that isn't valid JSON.
    Never raises — callers can treat the empty list as "no mesh available."
    """
    try:
        with urllib.request.urlopen(f"{url}/hosts", timeout=2) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return []
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return data


def find_host_for_capability(capability: str, url: str = DEFAULT_URL) -> str | None:
    """Return the hostname of a mesh host advertising `capability`, or None.

    Self-host wins when both self and a peer advertise the same capability —
    a local satisfier avoids any cross-host hop. Beyond that, returns the
    first peer in the order /hosts returned them.
    """
    hosts = list_hosts(url)
    self_match = next((h for h in hosts if h.get("self") and capability in (h.get("capabilities") or [])), None)
    if self_match:
        return self_match["host"]
    for h in hosts:
        if capability in (h.get("capabilities") or []):
            return h["host"]
    return None
