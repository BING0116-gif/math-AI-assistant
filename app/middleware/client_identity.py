"""限流与审计使用的客户端身份解析。

背景：生产拓扑下浏览器请求经 frontend nginx 反代到 web，socket 对端固定是
代理容器 IP。RateLimitMiddleware 早期直接取 ``request.client.host``，于是
**所有学生共用同一个限流桶**（单用户开几个标签页就能触发全站 429）。

信任边界：只有当 socket 对端命中 ``TRUSTED_PROXY_CIDRS`` 时才采信
``X-Forwarded-For``，否则一律用真实对端 IP —— 客户端自带的 XFF 不可信。

链值取法：nginx 用 ``$proxy_add_x_forwarded_for``（= 客户端已带头 + 真实对端）
追加，因此**从右往左**第一个不在可信网段内的地址才是真实客户端；若整条链都在
可信网段内（单跳反代的常见情形），取最右一项，即代理追加的真实对端地址。
"""
from __future__ import annotations

import ipaddress
from typing import Tuple

from starlette.requests import Request

DEFAULT_TRUSTED_PROXY_CIDRS = "172.16.0.0/12,127.0.0.1"

_UNKNOWN = "unknown"
_networks_cache: dict[str, Tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] = {}


def _parse_networks(raw: str) -> Tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if "/" not in item and ":" not in item:
                item = f"{item}/32"
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            # 配错单项不应让整条限流链路失效，跳过即可。
            continue
    return tuple(networks)


def trusted_networks(raw: str | None = None) -> Tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    value = DEFAULT_TRUSTED_PROXY_CIDRS if raw is None else raw
    cached = _networks_cache.get(value)
    if cached is None:
        cached = _parse_networks(value)
        _networks_cache[value] = cached
    return cached


def _is_in_networks(address: str, networks) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed in network for network in networks)


def _settings_cidrs() -> str:
    # 延迟导入：中间件在应用装配早期即被构造，避免 settings 循环导入。
    from app.config.settings import settings

    return getattr(settings, "TRUSTED_PROXY_CIDRS", DEFAULT_TRUSTED_PROXY_CIDRS) or DEFAULT_TRUSTED_PROXY_CIDRS


def _client_from_forwarded(forwarded: str, networks) -> str | None:
    chain = [part.strip() for part in forwarded.split(",")]
    chain = [part for part in chain if part and part.lower() != _UNKNOWN]
    if not chain:
        return None
    for candidate in reversed(chain):
        if not _is_in_networks(candidate, networks):
            return candidate
    return chain[-1]


def resolve_client_ip(request: Request) -> str:
    """返回可用于限流/审计的客户端 IP。"""
    peer = request.client.host if request.client else _UNKNOWN
    networks = trusted_networks(_settings_cidrs())
    if networks and peer != _UNKNOWN and _is_in_networks(peer, networks):
        forwarded = request.headers.get("x-forwarded-for", "")
        resolved = _client_from_forwarded(forwarded, networks)
        if resolved:
            return resolved
    return peer


def resolve_rate_limit_key(request: Request) -> str:
    """限流桶键：已认证用 user_id，未认证用解析后的真实 IP。

    AuthenticationMiddleware 是本中间件的外层（``add_middleware`` 后注册者更外），
    因此正常 ``/api/*`` 请求在进到这里时 ``request.state.user_id`` 已就绪。
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"u:{user_id}"
    return f"ip:{resolve_client_ip(request)}"
