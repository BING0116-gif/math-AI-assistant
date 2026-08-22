"""
Offline startup verification - run as subprocess.

Usage:
    python tests/scripts/offline_startup_check.py [--no-key|--disabled]

    --no-key     AI_ENABLED=true, DASHSCOPE_API_KEY removed
    --disabled   AI_ENABLED=false, DASHSCOPE_API_KEY=test-key

Exits with code 0 on success, 1 on failure. Prints JSON results.

Phases:
  1. Application assembly (import app.application → _build_services)
  2. FastAPI lifespan (TestClient context → actual lifespan enter/exit)
  3. Health check within lifespan
"""

import asyncio
import json
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def run_assembly_check() -> dict:
    """Phase 1: verify application assembly (import + _build_services)."""
    results = {}

    preloaded = set(sys.modules.keys())

    try:
        import app.application  # noqa: F401
        results["assembly_success"] = True
    except Exception as e:
        results["assembly_success"] = False
        results["assembly_error"] = type(e).__name__ + ": " + str(e)
        return results

    # Check which AI-related modules were newly loaded
    new_modules = set(sys.modules.keys()) - preloaded
    ai_modules = {m for m in new_modules if m.startswith(("agent_core", "prompts.dynamic_params"))}
    results["ai_modules_loaded"] = sorted(ai_modules)
    results["math_agent_not_imported"] = "agent_core" not in sys.modules
    results["dynamic_llm_not_imported"] = "prompts.dynamic_params" not in sys.modules

    # Check LLMService singleton was NOT initialized (module may be imported as dependency)
    try:
        import app.services.llm_service
        llm_initialized = app.services.llm_service.LLMService._instance is not None
    except Exception:
        llm_initialized = False
    results["llm_service_not_initialized"] = not llm_initialized

    # Check AI capability
    from app.services.ai_capability import get_ai_capability
    cap = get_ai_capability()
    results["ai_available"] = cap.available
    results["ai_reason"] = cap.reason
    results["ai_enabled_config"] = cap.enabled_config
    results["ai_has_api_key"] = cap.has_api_key

    # Check that agent is None in main
    try:
        import main
        results["agent_is_none"] = main.agent is None
    except Exception as e:
        results["agent_is_none_error"] = str(e)

    return results


async def run_lifespan_check() -> dict:
    """Phase 2: enter FastAPI lifespan via TestClient and verify health."""
    from fastapi.testclient import TestClient
    from main import app

    results = {}
    lifespan_entered = False
    health_status = None
    health_data = None

    # Record modules loaded before lifespan
    pre_lifespan_modules = set(sys.modules.keys())

    try:
        with TestClient(app) as client:
            lifespan_entered = True

            # Verify health endpoint within lifespan
            response = client.get("/api/health")
            health_status = response.status_code
            if health_status == 200:
                health_data = response.json()
            else:
                health_data = response.text[:500]

        results["lifespan_entered"] = True
        results["health_status"] = health_status
        results["health_data_unavailable"] = health_data
    except Exception as e:
        results["lifespan_entered"] = False
        results["lifespan_error"] = type(e).__name__ + ": " + str(e)
        results["health_status"] = None

    # Check which AI modules were loaded during lifespan
    lifespan_new_modules = set(sys.modules.keys()) - pre_lifespan_modules
    results["lifespan_new_ai_modules"] = sorted(
        m for m in lifespan_new_modules if m.startswith(
            ("agent_core", "prompts.dynamic_params")
        )
    )

    # Check LLMService singleton was NOT initialized during lifespan
    try:
        import app.services.llm_service
        lifespan_llm_initialized = app.services.llm_service.LLMService._instance is not None
    except Exception:
        lifespan_llm_initialized = False
    results["lifespan_llm_service_not_initialized"] = not lifespan_llm_initialized

    return results


def run_check() -> dict:
    """Run both phases and return unified results."""
    result = {}

    # Phase 1: Application assembly
    assembly = run_assembly_check()
    result.update(assembly)

    if not assembly.get("assembly_success"):
        result["lifespan_entered"] = False
        result["lifespan_skipped"] = "assembly_failed"
        return result

    # Phase 2: FastAPI lifespan
    lifespan = asyncio.run(run_lifespan_check())
    result.update(lifespan)

    return result


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--no-key":
        os.environ["DASHSCOPE_API_KEY"] = ""
        os.environ["AI_ENABLED"] = "true"
    elif mode == "--disabled":
        os.environ["AI_ENABLED"] = "false"
        os.environ["DASHSCOPE_API_KEY"] = "test-key"
    else:
        print(json.dumps({"error": f"Unknown mode: {mode}"}))
        sys.exit(1)

    result = run_check()
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Exit code: 0 if both phases succeeded
    ok = result.get("assembly_success") and result.get("lifespan_entered") and result.get("health_status") == 200
    sys.exit(0 if ok else 1)