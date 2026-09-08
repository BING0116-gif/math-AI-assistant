"""Verify an expired browser session cannot leave student routes loading forever."""
from __future__ import annotations

import asyncio
import json
import urllib.request

import websockets


async def command(ws, method, params=None, counter=[0]):
    counter[0] += 1
    ident = counter[0]
    await ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
    while True:
        payload = json.loads(await ws.recv())
        if payload.get("id") == ident:
            if "error" in payload:
                raise RuntimeError(payload["error"])
            return payload.get("result", {})


async def evaluate(ws, expression):
    result = await command(ws, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
    })
    return result["result"].get("value")


async def main():
    targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
    page = next(item for item in targets if item["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], origin="http://localhost") as ws:
        await command(ws, "Page.enable")
        await command(ws, "Runtime.enable")
        results = {}
        for route in ("/dashboard", "/profile", "/knowledge", "/error-book", "/apply"):
            await command(ws, "Page.navigate", {"url": "http://127.0.0.1:5173/"})
            await asyncio.sleep(0.5)
            await evaluate(ws, "localStorage.setItem('auth_token','expired'); localStorage.setItem('refresh_token','expired'); localStorage.setItem('current_user',JSON.stringify({user_id:'expired-user',username:'expired'}))")
            await command(ws, "Page.navigate", {"url": f"http://127.0.0.1:5173{route}"})
            await asyncio.sleep(3)
            results[route] = json.loads(await evaluate(ws, "JSON.stringify({path:location.pathname,text:document.body.innerText,token:localStorage.getItem('auth_token')})"))

    for route, state in results.items():
        assert state["token"] is None, f"expired session was not cleared: {route}"
        assert "加载中..." not in state["text"], f"permanent page loader: {route}"
        assert "正在绘制课程知识图谱" not in state["text"], f"permanent catalog loader: {route}"
        assert "正在加载最近记录" not in state["text"], f"permanent apply loader: {route}"
    print(json.dumps({route: {"path": state["path"], "session_cleared": state["token"] is None} for route, state in results.items()}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
