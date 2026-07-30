"""Small route-registration helpers kept free of application side effects."""


def register_debug_routes(target_app, debug: bool, router) -> None:
    """Register a development-only router when debug mode is fixed at startup."""
    if debug:
        target_app.include_router(router)
