"""Configuration for the Apple App Store Scraper. Everything can be set with
an environment variable; the defaults work out of the box.

    PORT                    port the API listens on (default 8000)
    APPLE_APP_STORE_PROXY   proxy URL for every request, e.g.
                            http://user:pass@host:port (default: none — direct).
                            The App Store answers a home or office connection
                            fine at normal volume. Apple rate-limits busy IPs
                            ("API capacity exceeded"), so set a rotating proxy
                            only if you run thousands of calls in bursts.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# The App Store's own retry ladder: a rate-limited call is retried on a
# fresh connection (and, with a rotating proxy, a fresh IP) after a short
# pause, because waiting longer does not clear Apple's per-IP limit.
APPLE_APP_STORE_MAX_RETRIES = 5
APPLE_APP_STORE_RETRY_BACKOFF = 0.5    # seconds, multiplied by the attempt number

# Parallel upstream calls per request (chart hydration, bulk lookups).
APPLE_APP_STORE_FANOUT = 4

APPLE_APP_STORE_PROXY = os.environ.get("APPLE_APP_STORE_PROXY") or None


def apple_app_store_proxy():
    """The proxy for one HTTP session (None = direct)."""
    return os.environ.get("APPLE_APP_STORE_PROXY") or None
