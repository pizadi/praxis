"""Trusted-proxy client IP resolution for audit/login records."""

from fastapi import Request


def client_ip(request: Request) -> str:
    """Resolve the client address without trusting a spoofable XFF prefix.

    The bundled nginx overwrites ``X-Real-IP`` with its directly observed peer
    and appends that peer to ``X-Forwarded-For``. Prefer the overwritten header;
    when it is absent, the rightmost XFF entry is the hop appended by nginx.
    Direct requests with neither header fall back to the socket peer.
    """

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()[:64]

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        rightmost = forwarded_for.split(",")[-1].strip()
        if rightmost:
            return rightmost[:64]

    return (request.client.host if request.client else "")[:64]
