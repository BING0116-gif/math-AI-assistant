"""Backward-compatible process entry point.

Use ``uvicorn app.application:app`` for the ASGI application.  Keeping this
shim means older tests and deployment scripts importing ``main`` continue to
work while application assembly lives under ``app/``.
"""

import os

import uvicorn

from app.application import app, agent, error_book_manager, registry, scheduled_tasks

__all__ = ["app", "agent", "error_book_manager", "registry", "scheduled_tasks"]


if __name__ == "__main__":
    # 8000 is commonly reserved by Windows/Hyper-V. Keep the local entry point
    # configurable and use a safer default; Docker still serves on port 8000.
    port = int(os.getenv("BACKEND_PORT", "8100"))
    uvicorn.run("app.application:app", host="127.0.0.1", port=port, reload=False)
