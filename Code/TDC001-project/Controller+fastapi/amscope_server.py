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

        # pick default preview resolution (entry 2 = 640×480)
        self.hcam.put_eSize(2)
        self.w, self.h = self.hcam.get_Size()

        # ---- new line --------------------------------------------------
        self._raw_lock = threading.Lock()         # protect _latest_raw
        # ----------------------------------------------------------------

        stride = ((self.w * 24 + 31) // 32) * 4
        self.buf = ctypes.create_string_buffer(stride * self.h)
        self.stride = stride

        self._latest_raw: bytes | None = None     # most-recent RGB frame
        self._frame_count = 0
        self._last_tick = time.perf_counter()
        self.fps = 0.0

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
        with ctx._raw_lock:
            ctx._latest_raw = bytes(ctx.buf)    # copy 1:1, no PNG

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

    # ——— simple setters / getters —————————————————————————
    def set_gain(self, gain: int):
        self.hcam.put_ExpoAGain(gain)

    def set_exposure(self, us: int):
        lo, hi, _ = self.hcam.get_ExpTimeRange()
        self.hcam.put_ExpoTime(max(lo, min(us, hi)))

    def set_auto_exp(self, enabled: bool):
        self.hcam.put_AutoExpoEnable(enabled)

    def set_resolution(self, mode: str):
        # ----------------- map mode → index -----------------
        res_cnt = self.hcam.ResolutionNumber()              # how many entries?
        sizes = [self.hcam.get_Resolution(i) for i in range(res_cnt)]  # [(w,h), …]

        if mode.lower() == "high":
            idx = max(range(res_cnt), key=lambda i: sizes[i][0]*sizes[i][1])
        elif mode.lower() == "low":
            idx = min(range(res_cnt), key=lambda i: sizes[i][0]*sizes[i][1])
        elif mode.lower() == "mid" and res_cnt > 2:
            idx = sorted(range(res_cnt), key=lambda i: sizes[i][0]*sizes[i][1])[res_cnt//2]
        else:
            raise ValueError(f"{mode!r} not available; camera has {res_cnt} mode(s)")

        # ----------------- state change sequence ------------ 
        self.hcam.Stop()
        time.sleep(0.2)                                     # give firmware time

        self.hcam.put_eSize(idx)
        self.w, self.h = self.hcam.get_Size()

        self.stride = ((self.w * 24 + 31) // 32) * 4
        self.buf = ctypes.create_string_buffer(self.stride * self.h)

        self.hcam.StartPullModeWithCallback(self._sdk_cb, self)

    def status(self) -> dict:
        return {
            "width": self.w,
            "height": self.h,
            "gain": self.hcam.get_ExpoAGain(),
            "exposure_us": self.hcam.get_ExpoTime(),
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
    cam.set_auto_exp(False)
    cam.set_gain(req.gain)
    return {"gain": req.gain}

@app.post("/exposure")
def set_exposure(req: ExposureRequest):
    cam = ensure_cam()
    lo, hi, _ = cam.hcam.get_ExpTimeRange()
    if not lo <= req.us <= hi:
        raise HTTPException(
            status_code=400,
            detail=f"Valid exposure range is {lo}–{hi} µs")
    cam.set_auto_exp(False)
    cam.set_exposure(req.us)
    return {"exposure_us": req.us, "auto_exposure": False}

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
    cam = ensure_cam()
    with cam._raw_lock:
        raw = cam._latest_raw
    if raw is None:
        raise HTTPException(503, "No frame yet")
    img = Image.frombuffer(
        "RGB", (cam.w, cam.h), raw, "raw",
        "BGR" if cam.hcam.get_Option(amcam.AMCAM_OPTION_BYTEORDER) else "RGB",
        0, 1
    )
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return Response(content=bio.getvalue(),
                    media_type="image/png",
                    headers={"Cache-Control": "no-store"})

# GUI discovery / health-check
@app.get("/ping")
def ping():
    return {"backend": "AmScope"}
