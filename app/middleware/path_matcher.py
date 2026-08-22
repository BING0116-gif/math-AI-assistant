from typing import List

from fastapi import Request

_STATIC_FILE_EXTENSIONS = (
    ".js", ".css", ".html", ".woff", ".woff2", ".ttf",
    ".ico", ".svg", ".png", ".jpg", ".jpeg",
)

_DEFAULT_STATIC_PATHS = ["/static", "/assets", "/@vite", "/frontend"]


class PathMatcher:
    def __init__(
        self,
        static_paths: List[str] | None = None,
        skip_paths: List[str] | None = None,
        rate_limit_skip_paths: List[str] | None = None,
    ):
        self._static_paths = static_paths or _DEFAULT_STATIC_PATHS
        self._skip_paths = skip_paths or []
        self._rate_limit_skip_paths = rate_limit_skip_paths or []

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

    def should_skip_rate_limit(self, request: Request) -> bool:
        path = request.url.path
        if self.is_static_path(path):
            return True
        if request.method == "GET" and not path.startswith("/api/"):
            return True
        if self.is_skip_path(path):
            return True
        # Admin 内部工具会一次性拉取大量候选/分析数据，豁免其限流
        if any(
            path == configured
            or (configured != "/" and configured.endswith("/") and path.startswith(configured))
            for configured in self._rate_limit_skip_paths
        ):
            return True
        return False
