import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from pydantic import BaseModel
from sqlalchemy import select, update

from app.data.models import User as DBUser, RefreshToken as DBRefreshToken
from app.data.database import get_db_session


class TokenPayload(BaseModel):
    user_id: str
    exp: int
    iat: int
    type: str = "access"
    jti: str = ""


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def _hash_password(password: str, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
    return f"{salt}${hashed.hex()}"


def _verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt, _ = hashed_password.split("$", 1)
        new_hash = _hash_password(password, salt)
        return secrets.compare_digest(new_hash, hashed_password)
    except (ValueError, AttributeError):
        return False


async def register_user(username: str, password: str) -> Optional[DBUser]:
    async with get_db_session() as session:
        result = await session.execute(select(DBUser).where(DBUser.username == username))
        existing = result.scalar_one_or_none()
        if existing:
            return None
        hashed = _hash_password(password)
        user = DBUser(
            username=username,
            email=f"{username}@placeholder.local",
            password_hash=hashed,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def authenticate_user(username: str, password: str) -> Optional[DBUser]:
    async with get_db_session() as session:
        result = await session.execute(select(DBUser).where(DBUser.username == username))
        user = result.scalar_one_or_none()
        if user and user.is_active and _verify_password(password, user.password_hash):
            return user
        return None


def create_access_token(user_id: str, secret_key: str, algorithm: str = "HS256",
                        expire_minutes: int = 1440) -> str:
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(16)
    payload = {
        "user_id": user_id,
        "exp": now + timedelta(minutes=expire_minutes),
        "iat": now,
        "type": "access",
        "jti": jti,
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


async def create_refresh_token(user_id: str, secret_key: str, algorithm: str = "HS256",
                               expire_days: int = 30) -> str:
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(16)
    expires_at = now + timedelta(days=expire_days)
    payload = {
        "user_id": user_id,
        "exp": expires_at,
        "iat": now,
        "type": "refresh",
        "jti": jti,
    }
    token = jwt.encode(payload, secret_key, algorithm=algorithm)

    async with get_db_session() as session:
        rt = DBRefreshToken(
            jti=jti,
            user_id=user_id,
            token_type="refresh",
            expires_at=expires_at,
            is_revoked=False,
        )
        session.add(rt)

    return token


async def create_token_pair(user_id: str, secret_key: str, algorithm: str = "HS256",
                            access_expire_minutes: int = 1440,
                            refresh_expire_days: int = 30) -> TokenPair:
    access_token = create_access_token(user_id, secret_key, algorithm, access_expire_minutes)
    refresh_token = await create_refresh_token(user_id, secret_key, algorithm, refresh_expire_days)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=access_expire_minutes * 60,
    )


def decode_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[TokenPayload]:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_access_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[str]:
    payload = decode_token(token, secret_key, algorithm)
    if payload is None or payload.type != "access":
        return None
    return payload.user_id


async def refresh_access_token(refresh_token_str: str, secret_key: str,
                               algorithm: str = "HS256",
                               access_expire_minutes: int = 1440,
                               refresh_expire_days: int = 30) -> Optional[TokenPair]:
    payload = decode_token(refresh_token_str, secret_key, algorithm)
    if payload is None or payload.type != "refresh":
        return None

    jti = payload.jti
    user_id = payload.user_id

    async with get_db_session() as session:
        claim = await session.execute(
            update(DBRefreshToken)
            .where(
                DBRefreshToken.jti == jti,
                DBRefreshToken.is_revoked == False,
            )
            .values(is_revoked=True)
        )
        if claim.rowcount != 1:
            return None
        user_result = await session.execute(
            select(DBUser).where(
                DBUser.id == user_id,
                DBUser.is_active == True,
            )
        )
        if user_result.scalar_one_or_none() is None:
            return None

    return await create_token_pair(
        user_id, secret_key, algorithm,
        access_expire_minutes, refresh_expire_days,
    )


async def revoke_token(token: str, secret_key: str, algorithm: str = "HS256") -> bool:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        jti = payload.get("jti", "")
        if not jti:
            return True

        token_type = payload.get("type", "")
        if token_type == "refresh":
            async with get_db_session() as session:
                result = await session.execute(
                    select(DBRefreshToken).where(DBRefreshToken.jti == jti)
                )
                rt = result.scalar_one_or_none()
                if rt:
                    rt.is_revoked = True

        return True
    except jwt.InvalidTokenError:
        return False


async def get_user_by_id(user_id: str) -> Optional[DBUser]:
    async with get_db_session() as session:
        result = await session.execute(select(DBUser).where(DBUser.id == user_id))
        return result.scalar_one_or_none()


async def init_default_admin(secret_key: str):
    admin_user = os.environ.get("ADMIN_USERNAME", "").strip()
    admin_pass = os.environ.get("ADMIN_PASSWORD", "").strip()

    if not admin_user or not admin_pass:
        print("[安全] 未设置 ADMIN_USERNAME / ADMIN_PASSWORD 环境变量，跳过管理员初始化")
        print("[安全] 请通过环境变量设置管理员凭据后重启服务")
        return

    admin = await register_user(admin_user, admin_pass)
    async with get_db_session() as session:
        result = await session.execute(
            select(DBUser).where(DBUser.username == admin_user)
        )
        stored_admin = result.scalar_one()
        stored_admin.role = "admin"
        stored_admin.is_active = True
    if admin:
        print("[安全] 管理员账号已创建")
    else:
        print("[安全] 管理员账号已存在，已确认管理员角色")
