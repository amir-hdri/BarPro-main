#!/usr/bin/env python3
"""SSH ProxyCommand: authenticated HTTP CONNECT through the sandbox proxy.

The sandbox exposes an authenticating HTTP proxy (407 without credentials) and
denies raw sockets, so ssh needs a CONNECT tunnel. macOS `nc` can do CONNECT but
cannot present proxy credentials, hence this shim.

Usage:
    ssh -o ProxyCommand='python3 /path/to/sandbox_connect.py %h %p' root@HOST

Credentials are read from HTTPS_PROXY so no secret is hardcoded here.
"""

import base64
import os
import select
import socket
import sys
import urllib.parse


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: sandbox_connect.py <host> <port>", file=sys.stderr)
        return 2
    target_host, target_port = sys.argv[1], sys.argv[2]

    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY")
    if not proxy_url:
        print("HTTPS_PROXY/ALL_PROXY not set", file=sys.stderr)
        return 2
    p = urllib.parse.urlparse(proxy_url)

    sock = socket.create_connection((p.hostname, p.port), timeout=20)

    req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n"
    if p.username:
        raw = f"{urllib.parse.unquote(p.username)}:{urllib.parse.unquote(p.password or '')}"
        token = base64.b64encode(raw.encode()).decode()
        req += f"Proxy-Authorization: Basic {token}\r\n"
    req += "\r\n"
    sock.sendall(req.encode())

    # Read just the CONNECT response headers, byte at a time, so no tunnel
    # payload is swallowed into our buffer.
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(1)
        if not chunk:
            print(f"proxy closed during CONNECT; got: {resp!r}", file=sys.stderr)
            return 1
        resp += chunk

    status_line = resp.split(b"\r\n", 1)[0].decode(errors="replace")
    if " 200" not in status_line:
        print(f"CONNECT failed: {status_line}", file=sys.stderr)
        return 1
    print(f"tunnel established: {status_line}", file=sys.stderr)

    # Shuttle stdin/stdout <-> socket until either side hangs up.
    sock.setblocking(False)
    stdin_fd, stdout_fd = sys.stdin.fileno(), sys.stdout.fileno()
    os.set_blocking(stdin_fd, False)
    try:
        while True:
            readable, _, _ = select.select([sock, stdin_fd], [], [], 60)
            for src in readable:
                if src is sock:
                    data = sock.recv(65536)
                    if not data:
                        return 0
                    os.write(stdout_fd, data)
                else:
                    data = os.read(stdin_fd, 65536)
                    if not data:
                        return 0
                    sock.sendall(data)
    except (BrokenPipeError, ConnectionResetError):
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
