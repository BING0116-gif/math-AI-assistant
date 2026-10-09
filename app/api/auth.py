from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.middleware.auth import (
    register_user,
    authenticate_user_detailed,
    LoginOutcome,
    create_token_pair,
    refresh_access_token,
    revoke_token,
)
from app.middleware.client_identity import resolve_client_ip
from app.middleware.security import validate_input, SecurityValidationError
from app.config.settings import settings
from app.observability import ACCOUNT_LOCKOUTS, LOGIN_FAILURES
from app.security.access_control import normalize_role
from app.security.audit import get_audit_logger

router = APIRouter(prefix="/api/auth", tags=["认证"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$")
    password: str = Field(..., min_length=6, max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    message: str
    status: str = "success"


class LoginError(BaseModel):
    """登录失败的统一响应体。

    不再把错误装进 FastAPI 默认的 ``{"detail": "..."}``：前端需要靠 ``code`` 分支
    区分"密码错"和"已锁定"，而 ``detail`` 字符串无法承载这个语义。
    """

    code: str
    message: str
    retry_after_seconds: Optional[int] = None


def _audit_login(user_id: str, success: bool, ip_address: str, reason: str) -> None:
    """审计失败不得影响登录本身，因此只记日志不抛出。"""
    try:
        get_audit_logger().log_login(
            user_id=user_id, success=success, ip_address=ip_address, reason=reason
        )
    except Exception:  # noqa: BLE001 - 审计写入失败不能把登录变成 500
        pass


@router.post("/register", response_model=MessageResponse)
async def register(request: RegisterRequest):
    try:
        validate_input(request.username, "username", max_length=32)
        validate_input(request.password, "password", max_length=64)
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = await register_user(request.username, request.password)
    if user is None:
        raise HTTPException(status_code=409, detail="用户名已存在")

    return MessageResponse(message="注册成功")


@router.post("/login", responses={
    401: {"model": LoginError, "description": "用户名或密码错误"},
    423: {"model": LoginError, "description": "账户已临时锁定"},
})
async def login(payload: LoginRequest, request: Request):
    try:
        validate_input(payload.username, "username", max_length=32)
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    client_ip = resolve_client_ip(request)
    result = await authenticate_user_detailed(
        payload.username, payload.password, client_ip=client_ip
    )

    if result.success:
        user = result.user
        tokens = await create_token_pair(
            user.id,
            settings.JWT_SECRET_KEY,
            settings.JWT_ALGORITHM,
            settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
            settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )
        _audit_login(str(user.id), True, client_ip, "success")
        return {
            "status": "success",
            "data": {
                "user_id": user.id,
                "username": user.username,
                "role": normalize_role(user.role),
                **tokens.model_dump(),
            },
        }

    known_user_id = str(result.user.id) if result.user is not None else ""
    LOGIN_FAILURES.labels(result.reason or "invalid_credentials").inc()
    _audit_login(
        known_user_id or f"unknown:{payload.username}",
        False,
        client_ip,
        result.reason,
    )

    if result.outcome is LoginOutcome.LOCKED:
        if result.newly_locked:
            ACCOUNT_LOCKOUTS.inc()
        retry_after = max(1, int(result.retry_after_seconds))
        return JSONResponse(
            status_code=423,
            headers={"Retry-After": str(retry_after)},
            content=LoginError(
                code="ACCOUNT_LOCKED",
                message="账户已临时锁定，请稍后再试",
                retry_after_seconds=retry_after,
            ).model_dump(),
        )

    return JSONResponse(
        status_code=401,
        content=LoginError(
            code="INVALID_CREDENTIALS",
            message="用户名或密码错误",
            retry_after_seconds=None,
        ).model_dump(),
    )


@router.get("/me")
async def me(request: Request):
    """Return the authenticated user's server-authoritative identity."""
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未认证")
    return {
        "code": 0,
        "data": {
            "user_id": str(user.id),
            "username": user.username,
            "role": normalize_role(user.role),
        },
    }


@router.post("/refresh")
async def refresh(request: RefreshRequest):
    tokens = await refresh_access_token(
        request.refresh_token,
        settings.JWT_SECRET_KEY,
        settings.JWT_ALGORITHM,
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )

    if tokens is None:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")

    return {
        "status": "success",
        "data": tokens.model_dump(),
    }


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, body: Optional[RefreshRequest] = None):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        await revoke_token(token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
    if body is not None:
        await revoke_token(
            body.refresh_token,
            settings.JWT_SECRET_KEY,
            settings.JWT_ALGORITHM,
        )

    return MessageResponse(message="已成功退出登录")
