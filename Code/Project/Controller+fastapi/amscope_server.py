#!/usr/bin/env python3
"""
Modified FastAPI backend for AmScope/Toupcam cameras
====================================================

This server exposes a minimal REST API to a single AmScope camera.  It is
designed to be run inside a dedicated Docker container where exactly one
camera is available.  Unlike the original implementation, this version
removes public endpoints that enumerate or switch cameras at runtime.  A
separate setup script (see ``setup.py``) is used to select which USB
camera should be associated with the container.  The selected camera's
identifier and friendly name are stored in a small JSON file (by default
``device_config.json``) that the API reads on startup.  During startup
the server attempts to open that specific device and ignores any other
connected cameras.  The ``/ping`` endpoint has also been extended to
report whether the assigned device is currently attached to the system.

All of the functionality for controlling exposure, gain, resolution and
streaming frames remains intact and is exposed via the same endpoints
used previously.  Removing the enumeration endpoints prevents a client
from accidentally connecting to the wrong camera when multiple devices
are present in the lab.

"""

from __future__ import annotations

# ── stdlib ────────────────────────────────────────────────────────────
import ctypes
import io
import json
import os
import threading
import time
from typing import List, Optional

# ── third‑party ───────────────────────────────────────────────────────
import amcam                              # Vendor SDK Python wrapper
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image                     # Pillow (add to requirements)


# Path to the device configuration file.  A different path can be supplied
# by setting the ``DEVICE_CONFIG`` environment variable when launching
# the container.  The file should contain a JSON object with two keys:
# ``device_id`` (the opaque identifier returned by ``amcam.Amcam.EnumV2``)
# and ``device_name`` (a human readable label for the camera).  See
# ``setup.py`` for a helper script that populates this file.
CONFIG_PATH: str = os.getenv("DEVICE_CONFIG", "device_config.json")

# Internal record of the camera that the API should manage.  These
# variables are populated during startup by reading the configuration
# file and then locating the corresponding device through the amcam SDK.
assigned_device_id: Optional[str] = None
assigned_device_name: Optional[str] = None

# Global singleton (one camera per backend container)
camera: "CameraController | None" = None

app = FastAPI(title="AmScope Camera API", version="0.2.0")


def load_config() -> None:
    """Load the assigned device information from ``CONFIG_PATH``.

    This helper populates the global ``assigned_device_id`` and
    ``assigned_device_name`` variables.  If the file cannot be read or
    does not contain the expected keys, both variables are set to ``None``.
    """
    global assigned_device_id, assigned_device_name
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        assigned_device_id = cfg.get("device_id")
        assigned_device_name = cfg.get("device_name")
    except Exception:
        assigned_device_id = None
        assigned_device_name = None


class ConnectRequest(BaseModel):
    # This model remains for backwards compatibility but is unused in
    # the modified API.  The ``index`` field is ignored because the
    # container will always connect to the device specified in the
    # configuration file.
    index: int = 0


class GainRequest(BaseModel):
    gain: int  # 100–300 %


class ExposureRequest(BaseModel):
    us: int  # micro‑seconds


class AutoExpRequest(BaseModel):
    enabled: bool


class ResolutionRequest(BaseModel):
    mode: str  # "high" | "mid" | "low"


class CameraController:
    """
    Thin wrapper around ``amcam.Amcam`` providing:

    • persistent frame buffer
    • background callback to pull frames
    • convenience setters/getters
    """

    def __init__(self, dev: amcam.Amcam) -> None:
        self.hcam = dev

        # Default preview resolution (index 2 is usually 640×480)
        self.hcam.put_eSize(2)
        self.w, self.h = self.hcam.get_Size()

        # Thread‑safe storage for the latest raw RGB frame
        self._raw_lock = threading.Lock()
        self._latest_raw: bytes | None = None

        # Stats for FPS calculation
        self._frame_count = 0
        self._last_tick = time.perf_counter()
        self.fps = 0.0

        # Allocate one RGB888 buffer big enough for the chosen size
        stride = ((self.w * 24 + 31) // 32) * 4         # 4‑byte aligned
        self.buf = ctypes.create_string_buffer(stride * self.h)
        self.stride = stride

        # Kick off continuous streaming; ``self._sdk_cb`` will fire per frame
        self.hcam.StartPullModeWithCallback(self._sdk_cb, self)

    # ------------------------------------------------------------------
    # SDK callback – runs on SDK thread, *not* the FastAPI thread pool
    # ------------------------------------------------------------------
    @staticmethod
    def _sdk_cb(event: int, ctx: "CameraController"):
        if event != amcam.AMCAM_EVENT_IMAGE:
            return  # Ignore non‑image events for now
        try:
            ctx.hcam.PullImageV2(ctx.buf, 24, None)
        except amcam.HRESULTException:
            # USB glitch → just drop the frame
            return
        # Copy the buffer to bytes so FastAPI threads can use it safely
        with ctx._raw_lock:
            ctx._latest_raw = bytes(ctx.buf)
        # --- Simple FPS meter (1‑second sliding window) ---------------
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
        Change sensor binning/ROI for "high", "mid", or "low".

        Implements:  Stop → eSize → re‑alloc buffer → Start
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
        time.sleep(0.2)  # allow firmware to settle
        self.hcam.put_eSize(idx)
        self.w, self.h = self.hcam.get_Size()
        self.stride = ((self.w * 24 + 31) // 32) * 4
        self.buf = ctypes.create_string_buffer(self.stride * self.h)
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
    """Return a list of cameras detected by the SDK.

    Each entry contains the device index and the display name.  This
    function remains useful for the setup script but is no longer
    exposed as a FastAPI route.
    """
    cams = amcam.Amcam.EnumV2()
    return [{"index": i, "id": c.id, "name": c.displayname} for i, c in enumerate(cams)]


def ensure_cam() -> CameraController:
    """HTTP 503 if no camera is currently connected/opened."""
    if camera is None:
        raise HTTPException(status_code=503, detail="Camera not connected.")
    return camera


# ───────────────────── app lifecycle hooks ────────────────────────────
@app.on_event("startup")
def _startup() -> None:
    """
    Attempt to connect to the configured camera on startup.

    When the server boots it reads the ``device_config.json`` file (or
    another file specified by ``DEVICE_CONFIG``) and then searches for a
    matching device in the list returned by ``amcam.Amcam.EnumV2``.
    If a match is found a ``CameraController`` is created and stored in
    the module‑level ``camera`` variable.  If no match is found the
    server starts in a degraded state where control endpoints will
    return HTTP 503.
    """
    global camera
    load_config()
    cams = amcam.Amcam.EnumV2()
    if assigned_device_id:
        # Try to locate the configured device by ID
        for dev in cams:
            # ``dev.id`` on Linux/Mac is a string; on Windows it's a pointer
            # object that ``amcam.Amcam.Open`` accepts directly.  We use
            # string comparison where possible but fall back to equality.
            try:
                if canonical_id(dev.id) == canonical_id(assigned_device_id):
                    camera = CameraController(amcam.Amcam.Open(dev.id))
                    break
            except Exception:
                # Some platforms may not support comparison of the id
                # attribute – ignore and continue searching.
                pass
    # Fallback: If no configuration or match, do not auto‑connect.  A
    # missing connection will cause API endpoints to return HTTP 503.


@app.on_event("shutdown")
def _shutdown() -> None:
    global camera
    if camera:
        camera.close()
        camera = None


# ───────────────────────── API routes ─────────────────────────────────

@app.get("/get_status")
def status():
    """Return width/height, gain, exposure, AE flag and FPS."""
    return ensure_cam().status()


@app.post("/set_gain")
def set_gain(req: GainRequest):
    """Force manual mode then set electronic gain (%)."""
    cam = ensure_cam()
    cam.set_auto_exp(False)
    cam.set_gain(req.gain)
    return {"gain": req.gain}


@app.post("/get_exposure")
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
def set_auto_exp_endpoint(req: AutoExpRequest):
    """Enable/disable auto‑exposure mode."""
    cam = ensure_cam()
    cam.set_auto_exp(req.enabled)
    return {"auto_exposure": req.enabled}


@app.post("/set_resolution")
def set_resolution_endpoint(req: ResolutionRequest):
    """Switch to "high", "mid" or "low" pre‑defined sensor size."""
    cam = ensure_cam()
    try:
        cam.set_resolution(req.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"resolution": req.mode}


@app.get(
    "/get_frame",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def frame():
    """
    Return the most recent RGB frame as PNG bytes.

    Heavy PNG encoding happens *here* (FastAPI thread), not in the SDK
    callback, so streaming stays smooth.
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

def canonical_id(dev_id: str) -> str:
    """
    Return the USB-ID with the volatile *third* token stripped.

    Example
    -------
    'tp-1-7-1351-25360'   →  'tp-1-1351-25360'
    'tp-1-13-1351-25360'  →  'tp-1-1351-25360'
    """
    parts = dev_id.split('-')
    if len(parts) >= 5:
        del parts[2]               # drop the port number
    return '-'.join(parts)

@app.get("/get_ping")
def ping():
    """
    Health check for the backend.

    This endpoint reports whether the assigned camera (as configured by
    ``setup.py``) is physically attached to the system.  If the device

    configuration file has not been created the status is reported as
    ``not-configured``.

    """
    load_config()  # reload in case the config was updated while running
    status: str
    name: Optional[str]
    if assigned_device_id is None:
        status = "not-configured"
        name = None
    else:
        # Enumerate currently connected devices and see if the assigned ID
        # appears in the list.  ``amcam.Amcam.EnumV2`` returns objects
        # whose ``id`` attribute matches the string saved in the config.
        cams = amcam.Amcam.EnumV2()
        found = False
        for dev in cams:
            #printouts for debugging purposes
            #the returned device id varies by one number by plugging and replugging the camera for some reason, we will remove this single number to perform the conditional
            #print("assigned id:" + assigned_device_id)
            #print(dev.id)
            try:
                for dev in cams:
                    dev_id_canon = canonical_id(dev.id)
                    assigned_id_canon = canonical_id(assigned_device_id)
                    if dev_id_canon == assigned_id_canon:
                        found = True
                        break
            except Exception:
                pass
        status = "connected" if found else "not-connected"
        name = assigned_device_name
    return {"status": status, "name": name}

from fastapi.responses import StreamingResponse

import cv2
import numpy as np

@app.get("/get_stream")
def stream():
    """
    MJPEG stream of the live camera feed.
    Streamed as multipart/x-mixed-replace.
    Compatible with most web browsers.
    """
    cam = ensure_cam()

    def mjpeg_generator():
        while True:
            with cam._raw_lock:
                raw = cam._latest_raw
            if raw is None:
                time.sleep(0.01)
                continue
            # Convert to RGB image
            img = Image.frombuffer(
                "RGB",
                (cam.w, cam.h),
                raw,
                "raw",
                "BGR" if cam.hcam.get_Option(amcam.AMCAM_OPTION_BYTEORDER) else "RGB",
                0,
                1,
            )
            # Convert to JPEG (in-memory)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            frame = buf.getvalue()

            # Yield in MJPEG format
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + f"{len(frame)}".encode() + b"\r\n\r\n" +
                frame + b"\r\n"
            )
            time.sleep(0.01)  # ~100 FPS max

    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# The following endpoints have intentionally been removed from the public
# interface: ``/get_cameras``, ``/set_connected`` and ``/set_disconnected``.
# These routes previously allowed clients to enumerate cameras and switch
# between them by index.  In a one-device-per-container model such
# functionality is undesirable because it can lead to accidental control
# of the wrong device.  The helper functions remain available internally
# (e.g. ``list_cameras()``) for use by setup scripts or debugging.
