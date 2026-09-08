"""Visible Phase 2 acceptance through a Chromium CDP endpoint."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "phase2-visual-qa"
TOKEN = os.environ["VISUAL_QA_TOKEN"]
USER_ID = os.environ["VISUAL_QA_USER_ID"]


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
    result = await command(ws, "Runtime.evaluate", {"expression": expression, "returnByValue": True})
    return result["result"].get("value")


async def render(ws, route, width, height, name):
    await command(ws, "Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width <= 390,
    })
    await command(ws, "Page.navigate", {"url": f"http://127.0.0.1:5173{route}"})
    await asyncio.sleep(2)
    state = json.loads(await evaluate(ws, "JSON.stringify({text:document.body.innerText,width:document.documentElement.scrollWidth,viewport:innerWidth,path:location.pathname,query:location.search})"))
    shot = await command(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    (OUT / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
    (OUT / f"{name}.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
    page = next(item for item in targets if item["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], origin="http://localhost") as ws:
        await command(ws, "Page.enable")
        await command(ws, "Runtime.enable")
        await command(ws, "Page.navigate", {"url": "http://127.0.0.1:5173/"})
        await asyncio.sleep(1)
        await evaluate(ws, f"localStorage.setItem('auth_token',{json.dumps(TOKEN)});localStorage.setItem('current_user',JSON.stringify({{id:{json.dumps(USER_ID)},user_id:{json.dumps(USER_ID)},username:'phase2a'}}));")
        desktop = await render(ws, "/error-book", 1440, 900, "error-book-desktop")
        assert desktop["width"] <= desktop["viewport"] + 1
        assert "极限验收" in desktop["text"] and "今日待解决" in desktop["text"]
        clicked = await evaluate(ws, "(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('开始今日复习'));if(!b)return false;b.click();return true})()")
        assert clicked
        await asyncio.sleep(2)
        practice = await render(ws, "/apply/practice?knowledge_point=P2-LIMIT", 1440, 900, "practice-prefilled-desktop")
        selected = await evaluate(ws, "(()=>{const labels=[...document.querySelectorAll('label')];const label=labels.find(x=>x.innerText.includes('极限验收'));return !!label && !!label.querySelector('input:checked')})()")
        assert practice["path"] == "/apply/practice" and practice["query"] == "?knowledge_point=P2-LIMIT"
        assert "极限验收" in practice["text"] and selected
        mobile = await render(ws, "/error-book", 390, 844, "error-book-mobile")
        assert mobile["width"] <= mobile["viewport"] + 1
        assert "极限验收" in mobile["text"] and "今日待解决" in mobile["text"]
    print(json.dumps({"status":"passed","desktop":{"viewport":desktop["viewport"],"width":desktop["width"]},"practice_selected":selected,"mobile":{"viewport":mobile["viewport"],"width":mobile["width"]}}))


if __name__ == "__main__":
    asyncio.run(main())
