import asyncio

import pytest

from app.services.stream_handler import with_sse_heartbeat


@pytest.mark.asyncio
async def test_sse_heartbeat_is_emitted_while_source_waits():
    async def source():
        await asyncio.sleep(0.01)
        yield "data: {\"type\": \"done\"}\n\n"

    items = [item async for item in with_sse_heartbeat(source(), interval_seconds=0.001)]

    assert ": ping\n\n" in items
    assert items[-1].startswith("data:")


@pytest.mark.asyncio
async def test_sse_heartbeat_preserves_source_order():
    async def source():
        yield "event: first\n\n"
        await asyncio.sleep(0)
        yield "event: second\n\n"

    items = [item async for item in with_sse_heartbeat(source(), interval_seconds=0.1)]

    assert items == ["event: first\n\n", "event: second\n\n"]
