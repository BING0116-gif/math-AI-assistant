from typing import Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.settings import settings

_CSP_DEBUG = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self' ws://localhost:* wss://localhost:* "
    "https://dashscope.aliyuncs.com http://localhost:* https://localhost:*; "
    "frame-ancestors 'self'"
)

_CSP_PRODUCTION = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self' wss://localhost:* https://dashscope.aliyuncs.com; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, debug: bool = False):
        self.app = app
        self._debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 在每次请求时读取 debug 配置，支持测试时动态切换
        is_debug = self._debug
        try:
            is_debug = settings.DEBUG
        except Exception:
            pass

        async def send_wrapper(response):
            if response["type"] == "http.response.start":
                headers = response.get("headers", [])
                headers.append((b"X-Content-Type-Options", b"nosniff"))
                headers.append((b"X-Frame-Options", b"DENY"))
                headers.append((b"X-XSS-Protection", b"1; mode=block"))
                headers.append((b"Referrer-Policy", b"strict-origin-when-cross-origin"))
                csp = _CSP_DEBUG if is_debug else _CSP_PRODUCTION
                headers.append((b"Content-Security-Policy", csp.encode()))
                headers.append((b"Permissions-Policy", b"camera=(), microphone=(), geolocation=()"))
                response["headers"] = headers
            await send(response)

        await self.app(scope, receive, send_wrapper)
