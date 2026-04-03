"""Fire-and-forget anonymous telemetry for softwaresoftware.

Stdlib only. Sends events in daemon threads so resolver latency is unaffected.
Silent on all failures — telemetry must never break the resolver.
"""

import json
import os
import sys
import threading
import urllib.request
import uuid

ENDPOINT = "https://telemetry.softwaresoftware.dev/api/events"
SESSION_ID = str(uuid.uuid4())
TIMEOUT = 2

# Respect userConfig toggle — CLAUDE_PLUGIN_OPTION_TELEMETRY is injected at runtime
_raw = os.environ.get("CLAUDE_PLUGIN_OPTION_TELEMETRY", "true")
ENABLED = _raw.lower() not in ("false", "0", "no")


def _get_resolver_version():
    try:
        from importlib.metadata import version
        return version("softwaresoftware")
    except Exception:
        return "unknown"


def send_event(event_type, **kwargs):
    """Send a telemetry event in a background thread. No-op if disabled."""
    if not ENABLED:
        return
    try:
        import probes
        detected_os = probes.probe_os()
        detected_shell = probes.probe_shell()
    except Exception:
        detected_os = "unknown"
        detected_shell = "unknown"

    payload = {
        "event_type": event_type,
        "session_id": SESSION_ID,
        "resolver_version": _get_resolver_version(),
        "os": detected_os,
        "shell": detected_shell,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        **kwargs,
    }
    threading.Thread(target=_post, args=(payload,), daemon=True).start()


def _post(payload):
    try:
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=TIMEOUT)
    except Exception:
        pass
