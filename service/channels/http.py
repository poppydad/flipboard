"""
Shared outbound HTTP helper for channels that call an external API.

Explicitly pins certifi's CA bundle rather than relying on the host
Python's default SSL trust store — some environments (notably
python.org-installed Python on macOS) don't have that wired to the
system keychain the way `curl` is, and fail with
CERTIFICATE_VERIFY_FAILED even though the same URL works fine outside
Python. Pinning certifi works the same way everywhere, including
whatever Python ends up on the Pi.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def get_json(url: str, **params: object) -> dict | list | None:
    """GETs a URL (optionally with query params) and returns parsed JSON,
    or None on any network/parse failure — channels are expected to treat
    that as "nothing to post this cycle," not crash the scheduler."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10, context=_SSL_CONTEXT) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
