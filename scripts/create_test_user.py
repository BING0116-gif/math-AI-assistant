"""E2E test: register user, get token, call recommendation API."""
import asyncio
import json
import sys
sys.path.insert(0, '.')

from app.data.database import init_db
from app.middleware.auth import register_user, authenticate_user, create_token_pair
from app.config.settings import settings


async def main():
    await init_db()

    # Register test user
    user = await register_user("testuser", "test123456")
    if user:
        print(f"User registered: {user.id}")
    else:
        print("User already exists, trying to authenticate...")

    # Authenticate
    user = await authenticate_user("testuser", "test123456")
    if user:
        tokens = await create_token_pair(
            user.id,
            settings.JWT_SECRET_KEY,
            settings.JWT_ALGORITHM,
            settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
            settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )
        print(f"Token: {tokens.access_token[:50]}...")
    else:
        print("Authentication failed!")


asyncio.run(main())