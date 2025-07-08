#!/usr/bin/env python3
"""
amscope_server.py ― FastAPI backend for AmScope / Toupcam cameras
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
• Enumerates every USB camera the SDK can see
• Exposes simple REST endpoints to configure gain, exposure, resolution, AE
• Streams *live* frames or still snapshots as PNG bytes
• Designed to talk to the new PyQt GUI over HTTP (no Qt in the backend)

⇢   GET  /cameras             → list available cameras
⇢   POST /connect             → open selected camera
⇢   POST /disconnect          → close camera
⇢   GET  /status              → current settings + frame size/FPS
⇢   POST /gain                → set electronic gain      {gain:int %}
⇢   POST /exposure            → set exposure time        {us:int}
⇢   POST /auto_exposure       → toggle AE                {enabled:bool}
⇢   POST /resolution          → set “high/mid/low”       {mode:str}
⇢   GET  /frame               → latest video frame (PNG)
⇢   GET  /snapshot            → still image      (PNG, blocking Snap)
⇢   GET  /ping                → health-check for GUI discovery
"""

from __future__ import annotations

import ctypes
import io
import threading
import time
from typing import Optional, List

import amcam                                # AmScope / Toupcam SDK
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image                       # pillow – add to requirements.lock

# ──────────────────────────── FastAPI app ──────────────────────────────
app = FastAPI(title="AmScope Camera API", version="0.1.0")

log_lock = threading.Lock()                 # protect print() from callback spam
camera: "CameraController | None" = None    # singleton (one cam per container)

# ──────────────────────────── models ───────────────────────────────────
class ConnectRequest(BaseModel):
    index: int = 0                          # 0-based index into /cameras list

class GainRequest(BaseModel):
    gain: int                               # 100–300 %

class ExposureRequest(BaseModel):
    us: int                                 # micro-seconds

class AutoExpRequest(BaseModel):
    enabled: bool

class ResolutionRequest(BaseModel):
    mode: str                               # "high"|"mid"|"low"

# ───────────────────── low-level camera wrapper ────────────────────────
class CameraController:
    """Owns the SDK object, a persistent frame buffer, and a tiny FPS counter."""

    def __init__(self, dev: amcam.Amcam):
        self.hcam = dev

        # Choose initial resolution (use SDK default: entry 2 = 640×480)
        self.hcam.put_eSize(2)
        self.w, self.h = self.hcam.get_Size()

        # Single pre-allocated buffer (RGB888 → stride rounded to 4 bytes)
        stride = ((self.w * 24 + 31) // 32) * 4
        self.buf = ctypes.create_string_buffer(stride * self.h)
        self.stride = stride

        # Thread-safe latest PNG
        self._frame_lock = threading.Lock()
        self._latest_png: Optional[bytes] = None

        # FPS measurement
        self._frame_count = 0
        self._last_tick = time.perf_counter()
        self.fps = 0.0

        # Start streaming
        self.hcam.StartPullModeWithCallback(self._sdk_cb, self)

    # ——— SDK callback runs on internal thread ————————————————
    @staticmethod
    def _sdk_cb(event: int, ctx: "CameraController"):
        if event != amcam.AMCAM_EVENT_IMAGE:
            return

        # Pull raw frame → buf
        try:
            ctx.hcam.PullImageV2(ctx.buf, 24, None)
        except amcam.HRESULTException:
            return                                              # drop

        # Convert to PNG in-memory
        img = Image.frombuffer(
            "RGB", (ctx.w, ctx.h), ctx.buf, "raw",
            "BGR" if ctx.hcam.get_Option(amcam.AMCAM_OPTION_BYTEORDER) else "RGB",
            0, 1
        )
        bio = io.BytesIO()
        img.save(bio, format="PNG")

        # Publish
        with ctx._frame_lock:
            ctx._latest_png = bio.getvalue()

        # FPS counter
        ctx._frame_count += 1
        now = time.perf_counter()
        if now - ctx._last_tick >= 1.0:
            ctx.fps = ctx._frame_count / (now - ctx._last_tick)
            ctx._frame_count = 0
            ctx._last_tick = now

    # ——— public helpers ——————————————————————————————
    def latest_png(self) -> bytes:
        with self._frame_lock:
            if self._latest_png is None:
                raise RuntimeError("No frame yet")
            return self._latest_png

    def snapshot_png(self) -> bytes:
        """Blocking still image capture (≈200 ms)."""
        ev = threading.Event()

        # local-scope buffer to avoid clobbering live view
        buf = ctypes.create_string_buffer(self.stride * self.h)

        def cb(event, ctx):
            if event == amcam.AMCAM_EVENT_STILLIMAGE:
                try:
                    ctx.hcam.PullStillImageV2(buf, 24, None)
                except amcam.HRESULTException:
                    pass
                finally:
                    ev.set()

        # temporary callback
        self.hcam.StartPullModeWithCallback(cb, self)
        self.hcam.Snap(0)
        ev.wait(timeout=2.0)

        # restore streaming callback
        self.hcam.Stop()
        self.hcam.StartPullModeWithCallback(self._sdk_cb, self)

        img = Image.frombuffer(
            "RGB", (self.w, self.h), buf, "raw",
            "BGR" if self.hcam.get_Option(amcam.AMCAM_OPTION_BYTEORDER) else "RGB",
            0, 1
        )
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    # ——— simple setters / getters —————————————————————————
    def set_gain(self, gain: int):
        self.hcam.put_ExpoAGain(gain)

    def set_exposure(self, us: int):
        lo, hi, _ = self.hcam.get_ExpTimeRange()
        self.hcam.put_ExpoTime(max(lo, min(us, hi)))

    def set_auto_exp(self, enabled: bool):
        self.hcam.put_AutoExpoEnable(enabled)

    def set_resolution(self, mode: str):
        idx = {"high": 0, "mid": 1, "low": 2}.get(mode.lower())
        if idx is None:
            raise ValueError("mode must be high|mid|low")
        self.hcam.put_eSize(idx)
        self.w, self.h = self.hcam.get_Size()

    def status(self) -> dict:
        return {
            "width": self.w,
            "height": self.h,
            "gain": self.hcam.get_ExpoAGain(),
            "exposure_us": self.hcam.get_ExpoTime()[0],
            "auto_exposure": bool(self.hcam.get_AutoExpoEnable()),
            "fps": round(self.fps, 1),
        }

    def close(self):
        try:
            self.hcam.Stop()
        except Exception:
            pass
        self.hcam.Close()

# ─────────────────────── helper functions ─────────────────────────────
def list_cameras() -> List[dict]:
    cams = amcam.Amcam.EnumV2()
    return [{"index": i, "name": c.displayname} for i, c in enumerate(cams)]

def ensure_cam() -> CameraController:
    if camera is None:
        raise HTTPException(status_code=503, detail="Camera not connected.")
    return camera

# ───────────────────── lifecycle hooks ────────────────────────────────
@app.on_event("startup")
def _startup():
    cams = amcam.Amcam.EnumV2()
    if cams:
        global camera
        camera = CameraController(amcam.Amcam.Open(cams[0].id))

@app.on_event("shutdown")
def _shutdown():
    if camera:
        camera.close()

# ──────────────────────── API endpoints ───────────────────────────────
@app.get("/cameras")
def cameras():
    return list_cameras()

@app.post("/connect")
def connect(req: ConnectRequest):
    cams = amcam.Amcam.EnumV2()
    if req.index >= len(cams):
        raise HTTPException(status_code=404, detail="Index out of range")
    global camera
    if camera:
        camera.close()
    camera = CameraController(amcam.Amcam.Open(cams[req.index].id))
    return {"status": "connected", "name": cams[req.index].displayname}

@app.post("/disconnect")
def disconnect():
    global camera
    if camera:
        camera.close()
        camera = None
    return {"status": "disconnected"}

@app.get("/status")
def status():
    return ensure_cam().status()

@app.post("/gain")
def set_gain(req: GainRequest):
    cam = ensure_cam()
    cam.set_gain(req.gain)
    return {"gain": req.gain}

@app.post("/exposure")
def set_exposure(req: ExposureRequest):
    cam = ensure_cam()
    cam.set_exposure(req.us)
    return {"exposure_us": req.us}

@app.post("/auto_exposure")
def set_auto_exp(req: AutoExpRequest):
    cam = ensure_cam()
    cam.set_auto_exp(req.enabled)
    return {"auto_exposure": req.enabled}

@app.post("/resolution")
def set_resolution(req: ResolutionRequest):
    cam = ensure_cam()
    try:
        cam.set_resolution(req.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"resolution": req.mode}

@app.get("/frame", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def frame():
    png = ensure_cam().latest_png()
    return Response(content=png, media_type="image/png")

@app.get("/snapshot", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def snapshot():
    png = ensure_cam().snapshot_png()
    return Response(content=png, media_type="image/png")

# GUI discovery / health-check
@app.get("/ping")
def ping():
    return {"backend": "AmScope"}
