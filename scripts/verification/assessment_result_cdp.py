"""Render a completed assessment result through the authenticated UI."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import urllib.request
from pathlib import Path

import websockets


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "visual-qa" / "assessment-result.png"


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


async def main():
    token = os.environ["VISUAL_QA_TOKEN"]
    user_id = os.environ["VISUAL_QA_USER_ID"]
    session_id = os.environ["ASSESSMENT_SESSION_ID"]
    targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
    page = next(item for item in targets if item["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], origin="http://localhost") as ws:
        await command(ws, "Page.enable")
        await command(ws, "Runtime.enable")
        await command(ws, "Emulation.setDeviceMetricsOverride", {
            "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False,
        })
        await command(ws, "Page.navigate", {"url": "http://127.0.0.1:5173/"})
        await asyncio.sleep(0.5)
        expression = (
            f"localStorage.setItem('auth_token',{json.dumps(token)});"
            f"localStorage.setItem('current_user',JSON.stringify({{user_id:{json.dumps(user_id)},username:'runtime-qa'}}))"
        )
        await command(ws, "Runtime.evaluate", {"expression": expression})
        await command(ws, "Page.navigate", {"url": f"http://127.0.0.1:5173/apply/assessment/sessions/{session_id}/result"})
        await asyncio.sleep(3)
        state = await command(ws, "Runtime.evaluate", {
            "expression": "JSON.stringify({text:document.body.innerText,path:location.pathname,width:document.documentElement.scrollWidth,viewport:innerWidth})",
            "returnByValue": True,
        })
        value = json.loads(state["result"]["value"])
        shot = await command(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(base64.b64decode(shot["data"]))
    assert "检测完成" in value["text"]
    assert "答对 4 / 5 题" in value["text"]
    assert "正在生成报告" not in value["text"]
    assert value["width"] <= value["viewport"] + 1
    print(json.dumps({"path": value["path"], "result": "4/5", "width": value["width"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
