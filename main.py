"""Backward-compatible process entry point.

Use ``uvicorn app.application:app`` for the ASGI application.  Keeping this
shim means older tests and deployment scripts importing ``main`` continue to
work while application assembly lives under ``app/``.
"""

import uvicorn

from app.application import app, agent, error_book_manager, registry, scheduled_tasks

__all__ = ["app", "agent", "error_book_manager", "registry", "scheduled_tasks"]


if __name__ == "__main__":
    uvicorn.run("app.application:app", host="127.0.0.1", port=8000, reload=False)
