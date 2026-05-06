import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from pydantic import BaseModel


class TokenPayload(BaseModel):
    user_id: str
    exp: float
    iat: float
    type: str = "access"
    jti: str = ""


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class User(BaseModel):
    user_id: str
    username: str
    hashed_password: str


_users_db: dict[str, User] = {}
_refresh_tokens: dict[str, str] = {}
_blacklisted_tokens: set[str] = set()


def _hash_password(password: str, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${hashed.hex()}"


def _verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt, _ = hashed_password.split("$", 1)
        new_hash = _hash_password(password, salt)
        return secrets.compare_digest(new_hash, hashed_password)
    except (ValueError, AttributeError):
        return False


def register_user(username: str, password: str) -> Optional[User]:
    if username in {u.username for u in _users_db.values()}:
        return None
    user_id = secrets.token_hex(8)
    hashed = _hash_password(password)
    user = User(user_id=user_id, username=username, hashed_password=hashed)
    _users_db[user_id] = user
    return user


def authenticate_user(username: str, password: str) -> Optional[User]:
    for user in _users_db.values():
        if user.username == username and _verify_password(password, user.hashed_password):
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


def create_refresh_token(user_id: str, secret_key: str, algorithm: str = "HS256",
                         expire_days: int = 30) -> str:
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(16)
    payload = {
        "user_id": user_id,
        "exp": now + timedelta(days=expire_days),
        "iat": now,
        "type": "refresh",
        "jti": jti,
    }
    token = jwt.encode(payload, secret_key, algorithm=algorithm)
    _refresh_tokens[jti] = user_id
    return token


def create_token_pair(user_id: str, secret_key: str, algorithm: str = "HS256",
                      access_expire_minutes: int = 1440,
                      refresh_expire_days: int = 30) -> TokenPair:
    access_token = create_access_token(user_id, secret_key, algorithm, access_expire_minutes)
    refresh_token = create_refresh_token(user_id, secret_key, algorithm, refresh_expire_days)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=access_expire_minutes * 60,
    )


def decode_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[TokenPayload]:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        jti = payload.get("jti", "")
        if jti in _blacklisted_tokens:
            return None
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


def refresh_access_token(refresh_token_str: str, secret_key: str,
                         algorithm: str = "HS256",
                         access_expire_minutes: int = 1440,
                         refresh_expire_days: int = 30) -> Optional[TokenPair]:
    payload = decode_token(refresh_token_str, secret_key, algorithm)
    if payload is None or payload.type != "refresh":
        return None

    jti = payload.jti
    if jti not in _refresh_tokens:
        return None

    user_id = payload.user_id
    _refresh_tokens.pop(jti, None)
    _blacklisted_tokens.add(jti)

    return create_token_pair(
        user_id, secret_key, algorithm,
        access_expire_minutes, refresh_expire_days,
    )


def revoke_token(token: str, secret_key: str, algorithm: str = "HS256") -> bool:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        jti = payload.get("jti", "")
        if jti:
            _blacklisted_tokens.add(jti)
        token_type = payload.get("type", "")
        if token_type == "refresh" and jti in _refresh_tokens:
            del _refresh_tokens[jti]
        return True
    except jwt.InvalidTokenError:
        return False


def get_user_by_id(user_id: str) -> Optional[User]:
    return _users_db.get(user_id)


def init_default_admin(secret_key: str):
    admin = register_user("admin", "admin123")
    if admin:
        print(f"[安全] 默认管理员已创建 - 用户名: admin, 密码: admin123 (请立即修改)")
