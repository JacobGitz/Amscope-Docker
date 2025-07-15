#!/usr/bin/env python3
"""
amscope_server.py ― FastAPI backend for AmScope / Toupcam cameras
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Enumerates USB cameras detected by the vendor SDK
* Exposes a REST API (see endpoint list below) to control gain, exposure,
  resolution, auto-exposure, etc.
* Streams live frames as PNG bytes so a GUI (e.g. PyQt) can display video.

Endpoints
---------
GET   /cameras            → list available cameras
POST  /connect            → open selected camera         {index:int}
POST  /disconnect         → close camera
GET   /status             → current settings, fps, size
POST  /gain               → set gain (%)                 {gain:int}
POST  /exposure           → set manual exposure (µs)     {us:int}
POST  /auto_exposure      → toggle auto-exposure         {enabled:bool}
POST  /resolution         → hi/mid/low sensor size       {mode:str}
GET   /frame              → latest video frame (PNG)
GET   /ping               → simple health-check
"""

from __future__ import annotations

# ── stdlib ────────────────────────────────────────────────────────────
import ctypes
import io
import threading
import time
from typing import List

# ── third-party ───────────────────────────────────────────────────────
import amcam                              # Vendor SDK Python wrapper
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image                     # Pillow (add to requirements)

# ───────────────────────────── FastAPI app ────────────────────────────
app = FastAPI(title="AmScope Camera API", version="0.1.0")

# Global singleton (one camera per backend container)
camera: "CameraController | None" = None

# Small helper so callback prints don’t interleave
_log_lock = threading.Lock()

# ──────────────────────────── Pydantic models ─────────────────────────
class ConnectRequest(BaseModel):
    index: int = 0                        # Which camera to open

class GainRequest(BaseModel):
    gain: int                             # 100–300 %

class ExposureRequest(BaseModel):
    us: int                               # micro-seconds

class AutoExpRequest(BaseModel):
    enabled: bool

class ResolutionRequest(BaseModel):
    mode: str                             # "high" | "mid" | "low"

# ───────────────────────── Camera controller ──────────────────────────
class CameraController:
    """
    Thin wrapper around amcam.Amcam providing:
    • persistent frame buffer
    • background callback to pull frames
    • convenience setters/getters
    """

    # ------------------------------------------------------------------
    def __init__(self, dev: amcam.Amcam) -> None:
        self.hcam = dev

        # Default preview resolution (index 2 is usually 640×480)
        self.hcam.put_eSize(2)
        self.w, self.h = self.hcam.get_Size()

        # Thread-safe storage for the latest raw RGB frame
        self._raw_lock = threading.Lock()
        self._latest_raw: bytes | None = None

        # Stats for FPS calculation
        self._frame_count = 0
        self._last_tick = time.perf_counter()
        self.fps = 0.0

        # Allocate one RGB888 buffer big enough for the chosen size
        stride = ((self.w * 24 + 31) // 32) * 4         # 4-byte aligned
        self.buf = ctypes.create_string_buffer(stride * self.h)
        self.stride = stride

        # Kick off continuous streaming; self._sdk_cb will fire per frame
        self.hcam.StartPullModeWithCallback(self._sdk_cb, self)

    # ------------------------------------------------------------------
    # SDK callback - runs on SDK thread, *not* the FastAPI thread pool
    # ------------------------------------------------------------------
    @staticmethod
    def _sdk_cb(event: int, ctx: "CameraController"):
        if event != amcam.AMCAM_EVENT_IMAGE:
            return  # Ignore non-image events for now

        # Pull raw RGB24 into ctx.buf
        try:
            ctx.hcam.PullImageV2(ctx.buf, 24, None)
        except amcam.HRESULTException:
            # USB glitch → just drop the frame
            return

        # Copy the buffer to bytes so FastAPI threads can use it safely
        with ctx._raw_lock:
            ctx._latest_raw = bytes(ctx.buf)

        # --- Simple FPS meter (1-second sliding window) ---------------
        ctx._frame_count += 1
        now = time.perf_counter()
        if now - ctx._last_tick >= 1.0:
            ctx.fps = ctx._frame_count / (now - ctx._last_tick)
            ctx._frame_count = 0
            ctx._last_tick = now

    # ------------------------------------------------------------------
    # Convenience setters/getters used by endpoints
    # ------------------------------------------------------------------
    def set_gain(self, gain: int) -> None:
        self.hcam.put_ExpoAGain(gain)

    def set_exposure(self, us: int) -> None:
        lo, hi, _ = self.hcam.get_ExpTimeRange()
        self.hcam.put_ExpoTime(max(lo, min(us, hi)))

    def set_auto_exp(self, enabled: bool) -> None:
        self.hcam.put_AutoExpoEnable(enabled)

    def set_resolution(self, mode: str) -> None:
        """
        Change sensor binning/ROI for \"high\", \"mid\", or \"low\".
        Implements:  Stop → eSize → re-alloc buffer → Start
        """
        # --- translate mode → index -----------------------------------
        res_cnt = self.hcam.ResolutionNumber()
        sizes = [self.hcam.get_Resolution(i) for i in range(res_cnt)]

        if mode.lower() == "high":
            idx = max(range(res_cnt), key=lambda i: sizes[i][0] * sizes[i][1])
        elif mode.lower() == "low":
            idx = min(range(res_cnt), key=lambda i: sizes[i][0] * sizes[i][1])
        elif mode.lower() == "mid" and res_cnt > 2:
            idx = sorted(
                range(res_cnt), key=lambda i: sizes[i][0] * sizes[i][1]
            )[res_cnt // 2]
        else:
            raise ValueError(f"{mode!r} not available; camera has {res_cnt} mode(s)")

        # --- state change sequence ------------------------------------
        self.hcam.Stop()
        time.sleep(0.2)                       # allow firmware to settle

        self.hcam.put_eSize(idx)
        self.w, self.h = self.hcam.get_Size()

        # Re-allocate buffer for new frame size
        self.stride = ((self.w * 24 + 31) // 32) * 4
        self.buf = ctypes.create_string_buffer(self.stride * self.h)

        # Restart streaming with the same callback
        self.hcam.StartPullModeWithCallback(self._sdk_cb, self)

    def status(self) -> dict:
        """Return a dict used by GET /status"""
        return {
            "width": self.w,
            "height": self.h,
            "gain": self.hcam.get_ExpoAGain(),
            "exposure_us": self.hcam.get_ExpoTime(),
            "auto_exposure": bool(self.hcam.get_AutoExpoEnable()),
            "fps": round(self.fps, 1),
        }

    def close(self) -> None:
        """Gracefully stop streaming and close USB handle."""
        try:
            self.hcam.Stop()
        except Exception:
            pass
        self.hcam.Close()

# ───────────────────── helper utilities ───────────────────────────────
def list_cameras() -> List[dict]:
    """Return [{'index':0,'name':'...'}, ...] for GUI dropdowns."""
    cams = amcam.Amcam.EnumV2()
    return [{"index": i, "name": c.displayname} for i, c in enumerate(cams)]

def ensure_cam() -> CameraController:
    """HTTP 503 if no camera is currently connected/opened."""
    if camera is None:
        raise HTTPException(status_code=503, detail="Camera not connected.")
    return camera

# ───────────────────── app start/stop hooks ───────────────────────────
@app.on_event("startup")
def _startup() -> None:
    """Auto-connect to the first camera so the API works out-of-the-box."""
    cams = amcam.Amcam.EnumV2()
    if cams:
        global camera
        camera = CameraController(amcam.Amcam.Open(cams[0].id))

@app.on_event("shutdown")
def _shutdown() -> None:
    """Release USB resources on container exit (Ctrl-C / docker stop)."""
    if camera:
        camera.close()

# ───────────────────────── API routes ─────────────────────────────────
@app.get("/cameras")
def cameras():
    """List all detected cameras (even if one is already open)."""
    return list_cameras()

@app.post("/connect")
def connect(req: ConnectRequest):
    """Open the selected camera index and close any previous one."""
    cams = amcam.Amcam.EnumV2()
    if req.index >= len(cams):
        raise HTTPException(404, "Index out of range")
    global camera
    if camera:
        camera.close()
    camera = CameraController(amcam.Amcam.Open(cams[req.index].id))
    return {"status": "connected", "name": cams[req.index].displayname}

@app.post("/disconnect")
def disconnect():
    """Close the active camera handle."""
    global camera
    if camera:
        camera.close()
        camera = None
    return {"status": "disconnected"}

@app.get("/status")
def status():
    """Return width/height, gain, exposure, AE flag, FPS."""
    return ensure_cam().status()

@app.post("/gain")
def set_gain(req: GainRequest):
    """Force manual mode then set electronic gain (%)."""
    cam = ensure_cam()
    cam.set_auto_exp(False)
    cam.set_gain(req.gain)
    return {"gain": req.gain}

@app.post("/exposure")
def set_exposure(req: ExposureRequest):
    """Validate range, disable AE, then set exposure time (µs)."""
    cam = ensure_cam()
    lo, hi, _ = cam.hcam.get_ExpTimeRange()
    if not lo <= req.us <= hi:
        raise HTTPException(400, f"Valid exposure range is {lo}–{hi} µs")
    cam.set_auto_exp(False)
    cam.set_exposure(req.us)
    return {"exposure_us": req.us, "auto_exposure": False}

@app.post("/auto_exposure")
def set_auto_exp(req: AutoExpRequest):
    """Enable/disable auto-exposure mode."""
    cam = ensure_cam()
    cam.set_auto_exp(req.enabled)
    return {"auto_exposure": req.enabled}

@app.post("/resolution")
def set_resolution(req: ResolutionRequest):
    """Switch to \"high\", \"mid\" or \"low\" pre-defined sensor size."""
    cam = ensure_cam()
    try:
        cam.set_resolution(req.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"resolution": req.mode}

@app.get(
    "/frame",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def frame():
    """
    Return the most recent RGB frame as PNG bytes.
    Heavy PNG encoding happens *here* (FastAPI thread),
    not in the SDK callback, so streaming stays smooth.
    """
    cam = ensure_cam()
    with cam._raw_lock:
        raw = cam._latest_raw
    if raw is None:
        raise HTTPException(503, "No frame yet")

    img = Image.frombuffer(
        "RGB",
        (cam.w, cam.h),
        raw,
        "raw",
        "BGR" if cam.hcam.get_Option(amcam.AMCAM_OPTION_BYTEORDER) else "RGB",
        0,
        1,
    )
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return Response(
        content=bio.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )

@app.get("/ping")
def ping():
    """Tiny endpoint so a GUI can test connectivity."""
    return {"backend": "AmScope"}
