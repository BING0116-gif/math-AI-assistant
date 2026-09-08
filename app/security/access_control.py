from enum import Enum
from typing import Set, Optional
from functools import wraps
from fastapi import HTTPException, Request


class Permission(Enum):
    READ_OWN_DATA = "read_own_data"
    WRITE_OWN_DATA = "write_own_data"
    DELETE_OWN_DATA = "delete_own_data"
    READ_ALL_DATA = "read_all_data"
    MANAGE_USERS = "manage_users"
    EXPORT_DATA = "export_data"


class RolePermissionMapping:
    MAPPING = {
        "student": {
            Permission.READ_OWN_DATA,
            Permission.WRITE_OWN_DATA,
            Permission.DELETE_OWN_DATA,
        },
        "teacher": {
            Permission.READ_OWN_DATA,
            Permission.WRITE_OWN_DATA,
            Permission.READ_ALL_DATA,
            Permission.EXPORT_DATA,
        },
        "admin": {
            Permission.READ_OWN_DATA,
            Permission.WRITE_OWN_DATA,
            Permission.DELETE_OWN_DATA,
            Permission.READ_ALL_DATA,
            Permission.MANAGE_USERS,
            Permission.EXPORT_DATA,
        },
    }


def check_data_ownership(requesting_user_id: str, resource_owner_id: str) -> bool:
    return requesting_user_id == resource_owner_id


def is_admin(user_role: str) -> bool:
    return user_role == "admin"


def require_permission(permission: Permission):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                raise HTTPException(status_code=401, detail="无法识别请求")

            user = getattr(request.state, "current_user", None)
            if user is None:
                raise HTTPException(status_code=401, detail="未认证")

            user_role = getattr(user, "role", "student")
            user_permissions = RolePermissionMapping.MAPPING.get(user_role, set())

            if Permission.READ_ALL_DATA in user_permissions:
                return await func(*args, **kwargs)

            if permission not in user_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"权限不足: 需要 {permission.value}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def verify_resource_ownership(
    request: Request, resource_owner_id: str
) -> None:
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未认证")

    user_role = getattr(user, "role", "student")

    if is_admin(user_role):
        return

    user_id = getattr(user, "id", None) or getattr(user, "user_id", None)
    if not check_data_ownership(str(user_id), resource_owner_id):
        raise HTTPException(status_code=403, detail="无权访问该资源")


def require_admin_role(request: Request) -> None:
    """要求管理员角色，否则抛出 403。"""
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未认证")
    user_role = getattr(user, "role", "student")
    if not is_admin(user_role):
        raise HTTPException(status_code=403, detail="权限不足: 需要管理员角色")


def require_internal_auth(request: Request) -> None:
    """内部接口鉴权，验证内网密钥。

    开发模式下跳过校验，生产环境必须配置 API Key。
    """
    from app.config.settings import settings

    # 开发模式跳过校验
    if settings.DEBUG:
        return

    # 检查 X-Internal-Key 头
    internal_key = (
        request.headers.get("X-Internal-Key", "")
        or request.headers.get("X-API-Key", "")
    )
    expected_key = settings.QUESTION_SYSTEM_API_KEY
    if not expected_key:
        raise HTTPException(status_code=503, detail="Internal API key is not configured")
    if internal_key != expected_key:
        raise HTTPException(status_code=403, detail="内部接口鉴权失败")
