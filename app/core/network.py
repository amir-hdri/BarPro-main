from typing import Any

RETRYABLE_NETWORK_MARKERS = (
    "timeout",
    "timed out",
    "readtimeout",
    "connecttimeout",
    "net::",
    "err_name_not_resolved",
    "name_not_resolved",
    "dns",
    "servfail",
    "could not resolve host",
    "temporary failure in name resolution",
    "nodename nor servname provided",
    "connection reset",
    "connection aborted",
    "connection refused",
    "connection closed",
    "connection terminated",
    "socket hang up",
    "target closed",
    "browser has been closed",
    "execution context was destroyed",
    "page has been closed",
    "frame was detached",
    "navigation interrupted",
    "session closed",
    "target page, context or browser has been closed",
    "protocol error",
    "net::err_connection_reset",
    "net::err_connection_refused",
    "net::err_internet_disconnected",
    "net::err_network_changed",
    "net::err_timed_out",
    "net::err_proxy_connection_failed",
    "net::err_tunnel_connection_failed",
    "ns_error_net_reset",
    "ns_error_connection_refused",
    "econnreset",
    "econnrefused",
    "etimedout",
    "connection reset by peer",
    "proxy error",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
    "squid",
    # TLS/SSL handshake aborts. A mid-handshake EOF is what an unstable transit
    # path (or a peer that resets selected clients) looks like from curl and
    # Playwright, so it is retryable rather than a permanent automation fault.
    "unexpected_eof",
    "unexpected eof",
    "eof occurred",
    "handshake failure",
    "sslerror",
    "err_ssl",
    "tlsv1",
    "wrong version number",
    # Chrome net errors also surface without the "net::" prefix depending on
    # which layer stringifies them.
    "err_connection",
    "err_empty_response",
)


# Subset of the markers above that indicate the EGRESS PATH is broken, i.e. this
# worker's route to the target is unusable and its IP index should leave the
# routing pool.
#
# WHY a subset: RETRYABLE_NETWORK_MARKERS also covers browser-lifecycle faults
# ("browser has been closed", "frame was detached", "execution context was
# destroyed"). Those are worker-local crashes — blocking the IP index for them
# would evict a perfectly healthy egress path from rotation.
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
    "err_connection",
    "err_internet_disconnected",
    "err_network_changed",
    "err_timed_out",
    "err_empty_response",
    # TLS
    "unexpected_eof",
    "unexpected eof",
    "eof occurred",
    "handshake failure",
    "sslerror",
    "err_ssl",
    "tlsv1",
    "wrong version number",
    # Proxy / gateway
    "err_proxy_connection_failed",
    "err_tunnel_connection_failed",
    "proxy error",
    "squid",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
)


def is_egress_failure(error: Any) -> bool:
    """True when the error means this worker's route to the target is broken."""
    message = str(error or "").lower()
    return any(marker in message for marker in EGRESS_FAILURE_MARKERS)


def is_retryable_network_error(error: Any) -> bool:
    message = str(error or "").lower()
    return any(marker in message for marker in RETRYABLE_NETWORK_MARKERS)
