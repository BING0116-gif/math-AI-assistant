from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

from app.middleware.auth import (
    register_user,
    authenticate_user,
    create_token_pair,
    refresh_access_token,
    revoke_token,
)
from app.middleware.security import validate_input, SecurityValidationError
from app.config.settings import settings

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


@router.post("/login")
async def login(request: LoginRequest):
    try:
        validate_input(request.username, "username", max_length=32)
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = await authenticate_user(request.username, request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    tokens = await create_token_pair(
        user.id,
        settings.JWT_SECRET_KEY,
        settings.JWT_ALGORITHM,
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )

    return {
        "status": "success",
        "data": {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            **tokens.model_dump(),
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
