import json

import pytest

from app.middleware_setup import MAX_TEXT_BODY_SIZE, RequestBodySizeMiddleware


def _scope(headers=()):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": list(headers),
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }


async def _invoke(messages, *, headers=()):
    received_by_app = []
    sent = []
    queue = list(messages)

    async def receive():
        return queue.pop(0)

    async def send(message):
        sent.append(message)

    async def app(scope, app_receive, app_send):
        while True:
            message = await app_receive()
            received_by_app.append(message)
            if message["type"] == "http.disconnect" or not message.get("more_body", False):
                break
        await app_send({"type": "http.response.start", "status": 204, "headers": []})
        await app_send({"type": "http.response.body", "body": b""})

    await RequestBodySizeMiddleware(app)(_scope(headers), receive, send)
    return received_by_app, sent


@pytest.mark.asyncio
async def test_rejects_chunked_body_that_exceeds_actual_limit(monkeypatch):
    monkeypatch.setattr("app.middleware_setup.MAX_TEXT_BODY_SIZE", 5)
    received, sent = await _invoke([
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ])

    assert received == []
    assert sent[0]["status"] == 413
    assert "请求体过大" in json.loads(sent[1]["body"])["detail"]


@pytest.mark.asyncio
async def test_replays_legal_chunked_body_without_mutation(monkeypatch):
    monkeypatch.setattr("app.middleware_setup.MAX_TEXT_BODY_SIZE", 6)
    messages = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]
    received, sent = await _invoke(messages)

    assert received == messages
    assert sent[0]["status"] == 204


@pytest.mark.asyncio
async def test_rejects_oversized_declared_length_before_reading_body():
    received, sent = await _invoke(
        [{"type": "http.request", "body": b"", "more_body": False}],
        headers=[(b"content-length", str(MAX_TEXT_BODY_SIZE + 1).encode())],
    )

    assert received == []
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_rejects_invalid_content_length_cleanly():
    received, sent = await _invoke(
        [{"type": "http.request", "body": b"", "more_body": False}],
        headers=[(b"content-length", b"not-a-number")],
    )

    assert received == []
    assert sent[0]["status"] == 400
