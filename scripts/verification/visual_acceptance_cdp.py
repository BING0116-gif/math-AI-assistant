"""Render authenticated student views through an existing Chromium CDP port."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "visual-qa"
TOKEN = os.environ["VISUAL_QA_TOKEN"]
USER_ID = os.environ["VISUAL_QA_USER_ID"]
USERNAME = os.environ.get("VISUAL_QA_USERNAME", "visualqa")


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


async def render(ws, route: str, width: int, height: int, name: str):
    await command(ws, "Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width <= 390,
    })
    await command(ws, "Page.navigate", {"url": f"http://127.0.0.1:5173{route}"})
    await asyncio.sleep(2)
    state = await command(ws, "Runtime.evaluate", {
        "expression": "JSON.stringify({title:document.title,text:document.body.innerText.slice(0,4000),width:document.documentElement.scrollWidth,viewport:innerWidth,errors:performance.getEntriesByType('resource').filter(x=>x.name.includes('/api/')).map(x=>({name:x.name,duration:x.duration}))})",
        "returnByValue": True,
    })
    value = json.loads(state["result"]["value"])
    shot = await command(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    (OUT / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
    (OUT / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
    page = next(item for item in targets if item["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], origin="http://localhost") as ws:
        await command(ws, "Page.enable")
        await command(ws, "Runtime.enable")
        await command(ws, "Page.navigate", {"url": "http://127.0.0.1:5173/"})
        await asyncio.sleep(1)
        await command(ws, "Runtime.evaluate", {"expression": f"localStorage.setItem('auth_token',{json.dumps(TOKEN)}); localStorage.setItem('current_user', JSON.stringify({{id:{json.dumps(USER_ID)},user_id:{json.dumps(USER_ID)},username:{json.dumps(USERNAME)}}}));"})
        results = {
            "dashboard_desktop": await render(ws, "/dashboard", 1440, 900, "dashboard-desktop"),
            "profile_desktop": await render(ws, "/profile", 1440, 900, "profile-desktop"),
            "dashboard_mobile": await render(ws, "/dashboard", 390, 844, "dashboard-mobile"),
            "profile_mobile": await render(ws, "/profile", 390, 844, "profile-mobile"),
        }
        await command(ws, "Page.navigate", {"url": "http://127.0.0.1:5173/dashboard"})
        await asyncio.sleep(2)
        clicked = await command(ws, "Runtime.evaluate", {
            "expression": "(() => { const el=[...document.querySelectorAll('button,a')].find(x=>x.innerText.includes('开始基础诊断')); if(!el) return false; el.click(); return true; })()",
            "returnByValue": True,
        })
        assert clicked["result"]["value"], "diagnostic action not found"
        await asyncio.sleep(1)
        location = await command(ws, "Runtime.evaluate", {
            "expression": "location.pathname", "returnByValue": True,
        })
        assert location["result"]["value"] == "/apply/assessment", location
    for name, result in results.items():
        assert result["width"] <= result["viewport"] + 1, f"horizontal overflow: {name} {result}"
        assert "尚在了解你" in result["text"], f"cold-start message missing: {name}"
        assert "0%" not in result["text"], f"cold-start zero scores rendered: {name}"
        assert "undefined" not in result["text"].lower(), f"undefined rendered: {name}"
    print(json.dumps({name: {"title": row["title"], "viewport": row["viewport"], "width": row["width"]} for name, row in results.items()}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
