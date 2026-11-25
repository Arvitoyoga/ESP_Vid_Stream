"""
Server relay ESP32-CAM  (jalan di VM Oracle)

  ESP32 --WebSocket /ingest--> server --MJPEG /stream--> browser
  Browser --POST /api/set--> server --WebSocket--> ESP32  (resolusi, LED, FPS)

Butuh Python 3.10+.
"""
import asyncio
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

load_dotenv()

INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")
VIEWER_USER = os.getenv("VIEWER_USER", "")
VIEWER_PASS = os.getenv("VIEWER_PASS", "")
PORT = int(os.getenv("PORT", "8080"))
BASE = Path(__file__).parent

if not INGEST_TOKEN:
    raise SystemExit("INGEST_TOKEN belum diisi. Salin .env.example menjadi .env lalu isi.")

app = FastAPI()
security = HTTPBasic(auto_error=False)

RES_ALLOWED = {5, 6, 8, 9, 10}  # QVGA, CIF, VGA, SVGA, XGA


def viewer_auth(creds: Optional[HTTPBasicCredentials] = Depends(security)):
    """Login dasar untuk viewer. Dinonaktifkan kalau VIEWER_PASS kosong."""
    if not VIEWER_PASS:
        return
    ok = (
        creds is not None
        and secrets.compare_digest(creds.username.encode(), VIEWER_USER.encode())
        and secrets.compare_digest(creds.password.encode(), VIEWER_PASS.encode())
    )
    if not ok:
        raise HTTPException(401, headers={"WWW-Authenticate": 'Basic realm="ESP32-CAM"'})


class Hub:
    def __init__(self):
        self.frame: Optional[bytes] = None
        self.seq = 0
        self.cond = asyncio.Condition()
        self.esp: Optional[WebSocket] = None
        self.state = {"res": 5, "led": 0, "fps": 0}
        self.measured_fps = 0.0
        self.frame_t = 0.0
        self._count = 0
        self._t0 = time.monotonic()

    def tick(self):
        now = time.monotonic()
        self.frame_t = now
        self._count += 1
        if now - self._t0 >= 1.0:
            self.measured_fps = self._count / (now - self._t0)
            self._count = 0
            self._t0 = now


hub = Hub()


# ---------- ESP32 mengirim frame ----------
@app.websocket("/ingest")
async def ingest(ws: WebSocket):
    token = ws.query_params.get("token", "")
    if not secrets.compare_digest(token.encode(), INGEST_TOKEN.encode()):
        await ws.close(code=1008)
        return

    await ws.accept()
    old = hub.esp
    hub.esp = ws
    if old is not None:
        try:
            await old.close()
        except Exception:
            pass

    # Sinkronkan pengaturan terakhir ke ESP32 (resolusi, LED, FPS)
    for k, v in hub.state.items():
        await ws.send_text(f"{k}:{v}")

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if data:
                hub.tick()
                async with hub.cond:
                    hub.frame = data
                    hub.seq += 1
                    hub.cond.notify_all()
    except Exception:
        pass
    finally:
        if hub.esp is ws:
            hub.esp = None


# ---------- Viewer ----------
@app.get("/", dependencies=[Depends(viewer_auth)])
async def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/stream", dependencies=[Depends(viewer_auth)])
async def stream():
    async def gen():
        last = -1
        while True:
            async with hub.cond:
                try:
                    await asyncio.wait_for(
                        hub.cond.wait_for(lambda: hub.frame is not None and hub.seq != last),
                        timeout=10,
                    )
                except asyncio.TimeoutError:
                    continue
                frame, last = hub.frame, hub.seq
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(frame)).encode()
                + b"\r\n\r\n"
                + frame
                + b"\r\n"
            )

    return StreamingResponse(
        gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/state", dependencies=[Depends(viewer_auth)])
async def api_state():
    online = hub.esp is not None
    streaming = online and (time.monotonic() - hub.frame_t) < 3
    return {
        "online": online,
        "streaming": streaming,
        "fps": round(hub.measured_fps, 1) if streaming else 0,
        "state": hub.state,
    }


@app.post("/api/set", dependencies=[Depends(viewer_auth)])
async def api_set(k: str, v: int):
    if k not in hub.state:
        raise HTTPException(400, "kunci tidak dikenal")
    if k == "res" and v not in RES_ALLOWED:
        raise HTTPException(400, "resolusi tidak valid")
    if k == "led" and v not in (0, 1):
        raise HTTPException(400, "led harus 0 atau 1")
    if k == "fps" and not (0 <= v <= 60):
        raise HTTPException(400, "fps harus 0-60")

    hub.state[k] = v
    if hub.esp is not None:
        try:
            await hub.esp.send_text(f"{k}:{v}")
        except Exception:
            pass
    return {"ok": True, "state": hub.state}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
