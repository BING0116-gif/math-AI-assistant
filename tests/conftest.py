import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Gracefully handle missing pytest-asyncio
try:
    import pytest_asyncio
    HAS_PYTEST_ASYNCIO = True
except ImportError:
    HAS_PYTEST_ASYNCIO = False
    pytest_asyncio = None

# Register asyncio marker
pytest_plugins = []
if HAS_PYTEST_ASYNCIO:
    pytest_plugins.append("pytest_asyncio")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )