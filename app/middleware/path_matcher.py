from typing import List

from fastapi import Request

_STATIC_FILE_EXTENSIONS = (
    ".js", ".css", ".html", ".woff", ".woff2", ".ttf",
    ".ico", ".svg", ".png", ".jpg", ".jpeg",
)

_DEFAULT_STATIC_PATHS = ["/static", "/assets", "/@vite", "/frontend"]

# 口令爆破类端点：走独立、更严的预算，且键永远是 IP（登录时尚无 user_id 可用，
# 也不能让攻击者通过附带合法 token 换桶绕过）。
_AUTH_LOGIN_PATHS = ("/api/auth/login", "/api/auth/register")
_AUTH_PREFIX = "/api/auth/"

# 限流桶名，与 middleware_config 中的三档预算一一对应。
BUCKET_AUTH_LOGIN = "auth_login"
BUCKET_AUTH = "auth"
BUCKET_GENERAL = "general"


def _path_matches(path: str, configured: str) -> bool:
    """配置项匹配：精确相等，或作为目录/资源前缀。

    ``/api/health`` 需要覆盖 ``/api/health/ready``；但 ``/api/tools`` 不应命中
    ``/api/toolsets``，故前缀只在配置项以 ``/`` 结尾或补一个 ``/`` 后成立。
    """
    if not configured:
        return False
    if path == configured:
        return True
    if configured == "/":
        return False
    if configured.endswith("/"):
        return path.startswith(configured)
    return path.startswith(f"{configured}/")


def _matches_any(path: str, patterns) -> bool:
    return any(_path_matches(path, pattern) for pattern in patterns)


class PathMatcher:
    def __init__(
        self,
        static_paths: List[str] | None = None,
        skip_paths: List[str] | None = None,
        rate_limit_skip_paths: List[str] | None = None,
        rate_limit_always_paths: List[str] | None = None,
    ):
        self._static_paths = static_paths or _DEFAULT_STATIC_PATHS
        self._skip_paths = skip_paths or []
        self._rate_limit_skip_paths = rate_limit_skip_paths or []
        self._rate_limit_always_paths = rate_limit_always_paths or list(_AUTH_LOGIN_PATHS)

    def is_static_path(self, path: str) -> bool:
        return any(path.startswith(p) for p in self._static_paths)

    def is_static_file(self, path: str) -> bool:
        return path.endswith(_STATIC_FILE_EXTENSIONS)

    def is_skip_path(self, path: str) -> bool:
        if self.is_static_path(path):
            return True
        return any(
            path == configured
            or (configured != "/" and configured.endswith("/") and path.startswith(configured))
            for configured in self._skip_paths
        )

    def should_skip_auth(self, request: Request) -> bool:
        path = request.url.path
        if self.is_skip_path(path):
            return True
        if request.method == "OPTIONS":
            return True
        if path == "/":
            return True
        return False

    def is_rate_limit_always_path(self, path: str) -> bool:
        return _matches_any(path, self._rate_limit_always_paths)

    def rate_limit_bucket(self, path: str) -> str:
        """返回该路径所属的限流桶，供中间件取对应预算。"""
        if _matches_any(path, _AUTH_LOGIN_PATHS):
            return BUCKET_AUTH_LOGIN
        if _matches_any(path, (_AUTH_PREFIX,)):
            return BUCKET_AUTH
        return BUCKET_GENERAL

    def should_skip_rate_limit(self, request: Request) -> bool:
        """判断是否完全不计限流预算。

        语义修正：NO_AUTH（免认证）**不再**意味着免限流。原实现里 ``is_skip_path``
        同时被认证与限流复用，导致 ``/api/auth/login``、``/api/auth/register`` 落在
        限流盲区，可被无限暴力尝试。这里改为：先判强制限流路径，再判豁免清单。
        """
        path = request.url.path
        if self.is_rate_limit_always_path(path):
            return False
        if self.is_static_path(path):
            return True
        if request.method == "GET" and not path.startswith("/api/"):
            return True
        # 心跳/轮询/探针/管理内部工具等显式豁免清单
        return _matches_any(path, self._rate_limit_skip_paths)
