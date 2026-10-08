import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
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


class LoginOutcome(str, Enum):
    """登录结果枚举。对外只区分"口令错"与"已锁定"两类，不区分用户是否存在/是否停用。"""

    SUCCESS = "success"
    INVALID_CREDENTIALS = "invalid_credentials"
    LOCKED = "locked"


@dataclass
class AuthResult:
    outcome: LoginOutcome
    user: Optional[DBUser] = None
    retry_after_seconds: int = 0
    #: 本次失败是否刚好触发锁定（用于计数指标，避免每次重试都重复 +1）
    newly_locked: bool = False
    #: 仅用于审计与指标内部区分原因，不得出现在响应体里
    reason: str = ""

    @property
    def success(self) -> bool:
        return self.outcome is LoginOutcome.SUCCESS


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite 读回的 ``DateTime(timezone=True)`` 列是 naive 时间，统一按 UTC 解释，
    避免与 aware ``now`` 比较时抛 TypeError（那会把登录接口变成 500）。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _login_guard_limits() -> tuple[int, int]:
    from app.config.settings import settings

    max_attempts = int(getattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 5) or 5)
    lock_minutes = int(getattr(settings, "LOGIN_LOCK_MINUTES", 15) or 15)
    return max(1, max_attempts), max(1, lock_minutes)


async def authenticate_user_detailed(
    username: str,
    password: str,
    client_ip: str = "",
) -> AuthResult:
    """校验口令并维护 ``failed_login_count`` / ``locked_until``。

    锁定只按 user_id 维度累计；IP 维度的爆破频次由限流中间件的 auth_login 桶负责，
    两者分离，避免共享出口 IP（宿舍/机房）的多个学生被连带误锁。
    """
    max_attempts, lock_minutes = _login_guard_limits()
    now = _utcnow()

    async with get_db_session() as session:
        result = await session.execute(select(DBUser).where(DBUser.username == username))
        user = result.scalar_one_or_none()

        if user is None:
            return AuthResult(
                outcome=LoginOutcome.INVALID_CREDENTIALS, reason="unknown_user"
            )
        if not user.is_active:
            # 与口令错同一对外结果，不在响应里区开，但指标/审计可区分
            return AuthResult(
                outcome=LoginOutcome.INVALID_CREDENTIALS, reason="inactive_user"
            )

        locked_until = _as_aware(user.locked_until)
        if locked_until is not None and locked_until > now:
            return AuthResult(
                outcome=LoginOutcome.LOCKED,
                retry_after_seconds=max(1, int((locked_until - now).total_seconds())),
                reason="locked",
            )

        if _verify_password(password, user.password_hash):
            await session.execute(
                update(DBUser)
                .where(DBUser.id == user.id)
                .values(
                    failed_login_count=0,
                    locked_until=None,
                    last_login_at=now,
                    last_login_ip=client_ip or None,
                )
            )
            await session.flush()
            return AuthResult(outcome=LoginOutcome.SUCCESS, user=user, reason="success")

        attempts = (user.failed_login_count or 0) + 1
        values: dict = {"failed_login_count": attempts}
        newly_locked = False
        if attempts >= max_attempts:
            # 进入锁定后计数归零：否则解锁后的第一次失败会立即再次触发锁定，
            # 用户永远得不到完整的 max_attempts 次重试机会。
            values.update(
                {
                    "failed_login_count": 0,
                    "locked_until": now + timedelta(minutes=lock_minutes),
                }
            )
            newly_locked = True
        await session.execute(
            update(DBUser).where(DBUser.id == user.id).values(**values)
        )
        await session.flush()

        if newly_locked:
            return AuthResult(
                outcome=LoginOutcome.LOCKED,
                retry_after_seconds=lock_minutes * 60,
                newly_locked=True,
                reason="locked",
            )
        return AuthResult(
            outcome=LoginOutcome.INVALID_CREDENTIALS, reason="wrong_password"
        )


async def authenticate_user(username: str, password: str) -> Optional[DBUser]:
    """兼容入口：只返回用户对象或 None（脚本与既有调用方保持原语义）。"""
    result = await authenticate_user_detailed(username, password)
    return result.user if result.success else None


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
    # 凭据来自 pydantic-settings（读取 .env），不是 os.environ——
    # pydantic-settings 不会把 .env 的值写回 os.environ。
    from app.config.settings import settings

    admin_user = (settings.ADMIN_USERNAME or "").strip()
    admin_pass = (settings.ADMIN_PASSWORD or "").strip()

    if not admin_user or not admin_pass:
        print("[安全] 未设置 ADMIN_USERNAME / ADMIN_PASSWORD（.env 中），跳过管理员初始化")
        print("[安全] 请在 .env 中添加 ADMIN_USERNAME / ADMIN_PASSWORD 后重启服务")
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
