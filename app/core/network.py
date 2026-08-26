"""Network error classification shared by the RPA workers and the circuit breaker.

The marker tables below are deliberately built by composition rather than
maintained as independent literals. Two hand-maintained lists (this module's
retry table and ``circuit_breaker.IP_BLOCK_PATTERNS``) had already drifted far
enough apart that five of six real egress failures were retried forever without
ever removing the broken IP index from the routing pool, so the invariant
"an egress failure is always retryable" is now enforced structurally:

    RETRYABLE_NETWORK_MARKERS = EGRESS + BROWSER_LIFECYCLE + GENERIC

Anything added to ``EGRESS_FAILURE_MARKERS`` is therefore retryable for free,
and ``tests/test_error_taxonomy.py`` asserts the containment so a future edit
cannot silently reintroduce the drift.
"""

from typing import Any

# ---------------------------------------------------------------------------
# 1. Egress failures — THIS worker's route to the target is unusable.
#
# Matching one of these means the IP index should leave the routing pool: the
# transport itself is broken, so retrying on the same egress path just burns
# attempts. Keep this table limited to transport-layer evidence.
# ---------------------------------------------------------------------------
EGRESS_FAILURE_MARKERS = (
    # DNS
    "err_name_not_resolved",
    "name_not_resolved",
    "could not resolve host",
    "temporary failure in name resolution",
    "servfail",
    # TCP
    "connection reset",
    "connection refused",
    "connection closed",
    "connection aborted",
    "connection terminated",
    "connection reset by peer",
    "econnreset",
    "econnrefused",
    "etimedout",
    "connection timed out",
    # Chrome net errors. The bare forms are used on purpose: Playwright emits
    # "net::ERR_CONNECTION_CLOSED" but the same condition reaches us as a plain
    # "ERR_CONNECTION_CLOSED" once another layer stringifies it, and only the
    # bare form matches both.
    "err_connection",
    "err_internet_disconnected",
    "err_network_changed",
    "err_timed_out",
    "err_empty_response",
    "err_address_unreachable",
    "err_network_access_denied",
    # TLS. A mid-handshake EOF is what an unstable transit path — or a peer
    # that resets selected clients — looks like from curl, requests and
    # Playwright alike, so it is transport evidence rather than a permanent
    # automation fault. Both "TLS handshake: EOF" (Go/proxy style) and
    # "tls: handshake failure" (OpenSSL style) must match.
    "tls handshake",
    "handshake: eof",
    "handshake eof",
    "handshake failure",
    "unexpected_eof",
    "unexpected eof",
    "eof occurred",
    "sslerror",
    "ssl handshake",
    "err_ssl",
    "tlsv1",
    "wrong version number",
    # Proxy / gateway — Squid sits in the egress path on every worker, so its
    # failures are egress failures.
    "err_proxy_connection_failed",
    "err_tunnel_connection_failed",
    "proxy error",
    "squid",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
)


# ---------------------------------------------------------------------------
# 2. Browser / worker-local lifecycle faults — retryable, but NOT egress.
#
# These are crashes on this worker, not evidence about the network path.
# Blocking the IP index for them would evict a perfectly healthy egress route
# from rotation, which is why the two tables are kept separate at all.
# ---------------------------------------------------------------------------
BROWSER_LIFECYCLE_MARKERS = (
    "target closed",
    "browser has been closed",
    "execution context was destroyed",
    "page has been closed",
    "frame was detached",
    "navigation interrupted",
    "session closed",
    "target page, context or browser has been closed",
    "protocol error",
    "socket hang up",
    # Playwright emits these when the renderer dies (usually worker OOM).
    "page crashed",
    "target crashed",
)


# ---------------------------------------------------------------------------
# 3. Generic transient markers — too broad to justify evicting an IP index.
#
# "timeout" matches target-side responses such as "408 Request Timeout", which
# say nothing about whether this worker's route is healthy.
# ---------------------------------------------------------------------------
GENERIC_RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "readtimeout",
    "connecttimeout",
    "net::",
    "dns",
    "ns_error_net_reset",
    "ns_error_connection_refused",
)


# Enforced by construction: every egress failure is retryable.
RETRYABLE_NETWORK_MARKERS = EGRESS_FAILURE_MARKERS + BROWSER_LIFECYCLE_MARKERS + GENERIC_RETRYABLE_MARKERS


def is_egress_failure(error: Any) -> bool:
    """True when the error means this worker's route to the target is broken.

    Callers use this to decide whether to take the current ``WORKER_IP_INDEX``
    out of the routing pool, so it must stay narrower than
    :func:`is_retryable_network_error`.
    """
    message = str(error or "").lower()
    return any(marker in message for marker in EGRESS_FAILURE_MARKERS)


def is_retryable_network_error(error: Any) -> bool:
    """True when the error is transient and the operation is worth retrying."""
    message = str(error or "").lower()
    return any(marker in message for marker in RETRYABLE_NETWORK_MARKERS)
