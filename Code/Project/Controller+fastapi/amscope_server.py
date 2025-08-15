#!/usr/bin/env python3
"""
FastAPI backend for AmScope/Toupcam cameras (serial-number only)
================================================================

This server exposes a minimal REST API to a single AmScope camera. It is
intended to run in a dedicated container where exactly one camera is available.

Key design choices (easy to reason about for newcomers):

1) **Serial-only selection**
   We *only* use the camera's immutable serial number (from
   `device_config.json` → key `serial_number`) to decide which device to open.
   We intentionally ignore volatile identifiers like USB paths or `device_id`.

2) **Non-disruptive presence checks**
   The `/get_ping` health endpoint checks whether the target serial is present
   *without* disturbing a live stream:
   - If the camera is already open, we compare the cached serial.
   - Otherwise we briefly open each enumerated slot just long enough to read
     the serial number, then immediately close it.

3) **Single, long-lived handle**
   When we do open the camera, we keep one handle alive for the whole lifetime
   of the process (until shutdown). All imaging and control calls use that
   single handle.

What the API provides:
- `/get_status`     → basic camera status (size, exposure, gain, FPS)
- `/set_gain`       → set manual gain
- `/set_exposure`   → set manual exposure (µs)
- `/auto_exposure`  → enable/disable auto exposure
- `/set_resolution` → pick among "high" | "mid" | "low" sensor presets
- `/get_frame`      → latest frame as PNG (pulls from a rolling buffer)
- `/get_stream`     → MJPEG stream (browser-friendly live preview)
- `/get_ping`       → health check (connected/not-connected/not-configured)

New to FastAPI / this codebase?  Read comments top-to-bottom once; they're
written for folks who are comfortable editing Python but may be new to vendor
SDKs, threads, or streaming endpoints.
"""

from __future__ import annotations

# ── stdlib ────────────────────────────────────────────────────────────
import ctypes
import io
import json
import os
import threading
import time
from typing import List, Optional, Tuple

# ── third-party ───────────────────────────────────────────────────────
# `amcam` is the vendor SDK's Python wrapper (Toupcam/AmScope).  This module
# provides `Amcam.EnumV2()` to list cameras, `Amcam.OpenByIndex(i)` to open a
# camera by its index in that list, and instance methods like
# `hcam.SerialNumber()`, `hcam.get_Size()`, `hcam.StartPullModeWithCallback(...)`,
# etc.
import amcam

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from PIL import Image  # Pillow – used to encode PNG/JPEG frames

# These imports are occasionally useful in deployments. We keep them here so
# folks can add small processing steps without chasing imports.
import cv2  # noqa: F401
import numpy as np  # noqa: F401

# Path to the device configuration file.  Override by setting the
# DEVICE_CONFIG environment variable when launching the container.
CONFIG_PATH: str = os.getenv("DEVICE_CONFIG", "device_config.json")

# Internal record of the camera that the API should manage.
# We deliberately do *not* store or reference `device_id` anywhere.
assigned_device_name: Optional[str] = None
assigned_device_serial: Optional[str] = None  # the only selector we use

# Global singleton (one camera per backend container).  We keep an instance of
# `CameraController` here once a camera is opened.
camera: "CameraController | None" = None

# Create the FastAPI app.  Uvicorn will import this as `amscope_server:app`.
app = FastAPI(title="AmScope Camera API", version="0.4.0")


# ───────────────────── config & helpers ───────────────────────────────
def _canon_serial(s: str | bytes | None) -> str:
    """Return a normalized (canonical) serial string.

    Why: serials can come back as bytes, lowercase, or with stray characters
    depending on the SDK/backends.  For robust comparisons we:
    - decode bytes → str (UTF-8, ignoring odd bytes)
    - uppercase
    - drop all non-alphanumeric characters
    """
    if s is None:
        return ""
    if isinstance(s, bytes):
        try:
            s = s.decode("utf-8", "ignore")
        except Exception:
            s = str(s)
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def load_config() -> None:
    """Load `device_config.json` and populate globals.

    This function reads only two keys: `device_name` and `serial_number`.
    Any `device_id` present in the file is intentionally ignored.

    On any error, we leave the globals as `None` so endpoints can report
    "not-configured".
    """
    global assigned_device_name, assigned_device_serial
    assigned_device_name = None
    assigned_device_serial = None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        assigned_device_name = cfg.get("device_name")
        assigned_device_serial = cfg.get("serial_number")
    except Exception:
        # Silently ignore – consumers will surface a clear status.
        pass


def _read_serial_by_index_once(index: int) -> str:
    """Open by index, read serial, and ALWAYS close (safe for presence checks).

    We use this for `/get_ping` when we don't already have a live handle.  It
    prevents double-opening the same device for long, which some SDKs dislike.
    """
    try:
        h = amcam.Amcam.OpenByIndex(index)
    except Exception:
        return ""
    try:
        return _canon_serial(h.SerialNumber())
    except Exception:
        return ""
    finally:
        try:
            h.Close()
        except Exception:
            pass


def _open_handle_and_read_serial_by_index(index: int) -> Tuple[Optional[amcam.Amcam], str]:
    """Open a device by index and return a *live handle* plus its canonical serial.

    This function is for the one-time *real* open during startup when we want
    to KEEP the handle (we do not close it here).  For presence checks, use
    `_read_serial_by_index_once` instead.
    """
    print("INFO: method _open_handle_and_read_serial_by_index() was called in amscope_server.py")
    try:
        h = amcam.Amcam.OpenByIndex(index)
    except Exception:
        print("WARNING: _open_handle_and_read_serial_by_index(index) was given an index that doesn't exist!")
        return None, ""
    try:
        raw = h.SerialNumber()
        sn = _canon_serial(raw)
    except Exception:
        print("WARNING: h.SerialNumber() failed in _open_handle_and_read_serial_by_index()")
        try:
            h.Close()
        except Exception:
            pass
        return None, ""
    print(f"INFO: _open_handle_and_read_serial_by_index() returned (index,sn): {index} {sn}")
    return h, sn


# NOTE: The function below is duplicated later in the original working file.
# Keeping a single definition is cleaner; Python will use the *last* definition
# it sees. We retain this one (the early definition) and comment on the later
# duplicate to avoid confusing new contributors.

def _serial_present(wanted_serial: str) -> bool:
    """Return True if a device with the given serial is currently attached.

    Order of checks:
    1) If the camera is already open, compare the live handle's serial (fast,
       no re-open, doesn't risk the stream).
    2) Otherwise enumerate and probe each index (open→read→close) to find the
       matching serial.
    """
    wanted = _canon_serial(wanted_serial)
    print("INFO: _serial_present in amscope_server.py is checking for serial number " + wanted)
    if not wanted:
        return False

    # 1) Fast-path: if a camera is open, check its serial without re-opening.
    global camera
    if camera is not None:
        try:
            current = _canon_serial(camera.hcam.SerialNumber())
            print(f"INFO: open handle reports serial: {current}")
            if current == wanted:
                return True
        except Exception:
            print("WARNING: could not read SerialNumber() from existing handle; continuing with probe")

    # 2) Slow-path: enumerate and probe each slot safely.
    try:
        cams = amcam.Amcam.EnumV2()
        if len(cams) >= 1:
            print("INFO: amcam.py is working normally")
    except Exception:
        print("WARNING: Amcam EnumV2() is failing to find devices for some reason!")
        return False

    for i in range(len(cams)):
        sn = _read_serial_by_index_once(i)
        if sn:
            print(f"INFO: found camera slot {i} with serial: {sn}")
        else:
            print(f"INFO: found camera slot {i} but could not read serial (likely already open elsewhere)")
        if sn == wanted:
            return True
    return False


def _find_and_open_by_serial(wanted_serial: str) -> Optional[amcam.Amcam]:
    """Search all enumerated cameras for a matching serial and open it.

    Returns an *open* handle if found, otherwise `None`.
    """
    print("INFO: method _find_and_open_by_serial() was called in amscope_server.py")
    wanted = _canon_serial(wanted_serial)
    print("INFO: _find_and_open_by_serial() in amscope_server.py is looking for sn: " + wanted)
    if not wanted:
        return None
    try:
        cams = amcam.Amcam.EnumV2()
    except Exception:
        return None

    for i in range(len(cams)):
        h, sn = _open_handle_and_read_serial_by_index(i)
        if not h:
            continue
        if sn == wanted:
            print("INFO: Camera with desired serial number found!")
            return h  # keep it open for the caller
        else:
            print("WARNING: index", i, "serial", sn, "!= wanted", wanted)
            try:
                h.Close()
            except Exception:
                pass
    return None


# --- BEGIN: Duplicate (from original working paste) -------------------
# The block below is functionally identical to the earlier `_serial_present`.
# Python will use *this* (later) definition at runtime, shadowing the earlier
# one. We keep it here to preserve your original working file structure, but
# recommend removing the duplication to avoid confusion for new contributors.

def _serial_present(wanted_serial: str) -> bool:  # duplicate definition
    """Duplicate of `_serial_present` (kept to match original working file).

    Return True if a device with the given serial is currently attached.
    """
    wanted = _canon_serial(wanted_serial)
    print("INFO: _serial_present in amscope_server.py is checking for serial number " + wanted)
    if not wanted:
        return False

    global camera
    if camera is not None:
        try:
            current = _canon_serial(camera.hcam.SerialNumber())
            print(f"INFO: open handle reports serial: {current}")
            if current == wanted:
                return True
        except Exception:
            print("WARNING: could not read SerialNumber() from existing handle; continuing with probe")

    try:
        cams = amcam.Amcam.EnumV2()
        if len(cams) >= 1:
            print("INFO: amcam.py is working normally")
    except Exception:
        print("WARNING: Amcam EnumV2() is failing to find devices for some reason!")
        return False

    for i in range(len(cams)):
        sn = _read_serial_by_index_once(i)
        if sn:
            print(f"INFO: found camera slot {i} with serial: {sn}")
        else:
            print(f"INFO: found camera slot {i} but could not read serial (likely already open elsewhere)")
        if sn == wanted:
            return True
    return False
# --- END: Duplicate ----------------------------------------------------


# ───────────────────── models (request bodies) ────────────────────────
# Pydantic models validate incoming JSON payloads for POST endpoints.
class GainRequest(BaseModel):
    gain: int  # expected range: 100–300 % (from vendor docs)


class ExposureRequest(BaseModel):
    us: int  # exposure in microseconds


class AutoExpRequest(BaseModel):
    enabled: bool  # True to enable auto exposure, False to disable


class ResolutionRequest(BaseModel):
    mode: str  # "high" | "mid" | "low"


# ───────────────────── camera controller wrapper ──────────────────────
class CameraController:
    """Tiny helper class around a live `amcam.Amcam` handle.

    Responsibilities:
    - Set a safe default resolution for previews
    - Maintain a rolling RGB frame buffer in memory
    - Track FPS (frames per second) roughly once per second
    - Expose convenience setters/getters (gain/exposure/AE/resolution)
    - Start the SDK's pull-mode callback to receive frames continuously

    The SDK calls our `_sdk_cb` whenever a new frame is ready. We copy it into
    `self.buf` and stash a Python `bytes` snapshot in `self._latest_raw`.
    """

    def __init__(self, dev: amcam.Amcam) -> None:
        self.hcam = dev

        # 1) Choose a conservative default resolution (so UIs load quickly).
        try:
            res_cnt = int(self.hcam.ResolutionNumber())
        except Exception:
            res_cnt = 0

        if res_cnt <= 0:
            default_idx = 0
        elif res_cnt > 2:
            # If the camera exposes 3+ sizes, pick a mid/low-ish one (index 2)
            # for startup preview. Users can switch to "high" later.
            default_idx = 2
        else:
            # If 1 or 2 modes exist, pick the smaller one (0 for 1-mode, 1 for 2-mode)
            default_idx = res_cnt - 1  # 1→0, 2→1

        try:
            self.hcam.put_eSize(default_idx)
        except amcam.HRESULTException:
            # Fallback: try index 0 if the preferred one fails
            try:
                self.hcam.put_eSize(0)
            except Exception:
                pass

        # 2) Cache the active width/height.
        self.w, self.h = self.hcam.get_Size()

        # 3) Concurrency primitives + rolling buffer for latest RGB frame.
        self._raw_lock = threading.Lock()
        self._latest_raw: bytes | None = None

        # 4) FPS stats (computed about once per second in the callback).
        self._frame_count = 0
        self._last_tick = time.perf_counter()
        self.fps = 0.0

        # 5) Allocate a single RGB888 buffer of appropriate stride.
        # Stride is rounded up to a 4-byte boundary (typical SDK requirement).
        stride = ((self.w * 24 + 31) // 32) * 4
        self.buf = ctypes.create_string_buffer(stride * self.h)
        self.stride = stride

        # 6) Start the SDK in pull-mode with our callback.
        self.hcam.StartPullModeWithCallback(self._sdk_cb, self)

    @staticmethod
    def _sdk_cb(event: int, ctx: "CameraController"):
        """SDK callback (runs on a background thread provided by the SDK).

        We only care about image events. When one arrives, we ask the SDK to
        fill our preallocated RGB buffer, then atomically swap in a Python
        `bytes` copy for the web endpoints to read.
        """
        if event != amcam.AMCAM_EVENT_IMAGE:
            return
        try:
            ctx.hcam.PullImageV2(ctx.buf, 24, None)  # 24 = RGB888
        except amcam.HRESULTException:
            return
        with ctx._raw_lock:
            ctx._latest_raw = bytes(ctx.buf)
        ctx._frame_count += 1
        now = time.perf_counter()
        if now - ctx._last_tick >= 1.0:
            ctx.fps = ctx._frame_count / (now - ctx._last_tick)
            ctx._frame_count = 0
            ctx._last_tick = now

    # --- Simple setters / getters for camera controls -----------------
    def set_gain(self, gain: int) -> None:
        self.hcam.put_ExpoAGain(gain)

    def set_exposure(self, us: int) -> None:
        lo, hi, _ = self.hcam.get_ExpTimeRange()
        self.hcam.put_ExpoTime(max(lo, min(us, hi)))

    def set_auto_exp(self, enabled: bool) -> None:
        self.hcam.put_AutoExpoEnable(enabled)

    def set_resolution(self, mode: str) -> None:
        # Translate a human-friendly mode string into a sensor index.
        res_cnt = self.hcam.ResolutionNumber()
        if res_cnt <= 0:
            raise ValueError("No resolutions reported by camera")
        sizes = [self.hcam.get_Resolution(i) for i in range(res_cnt)]

        if mode.lower() == "high":
            idx = max(range(res_cnt), key=lambda i: sizes[i][0] * sizes[i][1])
        elif mode.lower() == "low":
            idx = min(range(res_cnt), key=lambda i: sizes[i][0] * sizes[i][1])
        elif mode.lower() == "mid" and res_cnt > 2:
            idx = sorted(range(res_cnt), key=lambda i: sizes[i][0] * sizes[i][1])[res_cnt // 2]
        else:
            raise ValueError(f"{mode!r} not available; camera has {res_cnt} mode(s)")

        # Applying a new size typically requires stopping the stream briefly.
        self.hcam.Stop()
        time.sleep(0.2)
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

    def close(self) -> None:
        try:
            self.hcam.Stop()
        except Exception:
            pass
        self.hcam.Close()


# ───────────────────── helper utilities (not routes) ──────────────────
def list_cameras() -> List[dict]:
    """Return a list of detected cameras with *names and serials only*.

    This helper is useful when building UIs that let users pick a camera by
    serial. We intentionally do *not* expose SDK-specific IDs here to keep
    everything serial-centric.
    """
    out: List[dict] = []
    try:
        cams = amcam.Amcam.EnumV2()
    except Exception:
        return out
    for i in range(len(cams)):
        name = getattr(cams[i], "displayname", None)
        h, sn = _open_handle_and_read_serial_by_index(i)
        if h:
            try:
                h.Close()
            except Exception:
                pass
        out.append({
            "index": i,
            "name": name,
            "serial": sn or None,
        })
    return out


def ensure_cam() -> CameraController:
    """Fetch the global camera controller or raise a 503 error.

    Many endpoints rely on the camera being connected; this helper centralizes
    that check and returns a consistent HTTP error if not.
    """
    if camera is None:
        raise HTTPException(status_code=503, detail="Camera not connected.")
    return camera


# ───────────────────── app lifecycle hooks ────────────────────────────
@app.on_event("startup")
def _startup() -> None:
    """Attempt to connect to the configured camera by serial at process start.

    If the serial is missing or the device isn't present, we start without a
    camera. Endpoints will return clear errors until the device is attached
    and the process restarted (or until you add hot-plug logic).
    """
    global camera
    load_config()

    if assigned_device_serial:
        h = _find_and_open_by_serial(assigned_device_serial)
        if h is not None:
            # Wrap the live handle in our controller, which starts streaming.
            camera = CameraController(h)
            return
    # Otherwise, remain idle (the API will report "Camera not connected.")


@app.on_event("shutdown")
def _shutdown() -> None:
    """Cleanly stop streaming and close the camera on process shutdown."""
    global camera
    if camera:
        camera.close()
        camera = None


# ───────────────────────── API routes ─────────────────────────────────
@app.get("/get_status")
def status():
    """Return width/height, gain, exposure, AE flag and FPS as JSON."""
    return ensure_cam().status()


@app.post("/set_gain")
def set_gain(req: GainRequest):
    """Disable auto-exposure, then set the electronic gain (percent)."""
    cam = ensure_cam()
    cam.set_auto_exp(False)
    cam.set_gain(req.gain)
    return {"gain": req.gain}


@app.post("/set_exposure")
def set_exposure(req: ExposureRequest):
    """Validate range, disable auto-exposure, then set exposure (µs)."""
    cam = ensure_cam()
    lo, hi, _ = cam.hcam.get_ExpTimeRange()
    if not lo <= req.us <= hi:
        raise HTTPException(400, f"Valid exposure range is {lo}–{hi} µs")
    cam.set_auto_exp(False)
    cam.set_exposure(req.us)
    return {"exposure_us": req.us, "auto_exposure": False}


@app.post("/auto_exposure")
def set_auto_exp_endpoint(req: AutoExpRequest):
    """Enable/disable auto-exposure mode."""
    cam = ensure_cam()
    cam.set_auto_exp(req.enabled)
    return {"auto_exposure": req.enabled}


@app.post("/set_resolution")
def set_resolution_endpoint(req: ResolutionRequest):
    """Switch to \"high\", \"mid\" or \"low\" sensor size preset."""
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
    """Return the most recent RGB frame as PNG bytes.

    Internally, we convert the raw RGB buffer into a Pillow Image, encode it
    to PNG in-memory, then send those bytes as the HTTP response. Browsers
    and most clients can display or save this as a still image.
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
        # Some firmware use BGR byte order; the SDK exposes a flag for that.
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


@app.get("/get_stream")
def stream():
    """Return an MJPEG stream of the live camera feed (browser-friendly).

    This uses HTTP multipart/x-mixed-replace where each part is a JPEG frame.
    Most browsers can render this as a live <img> source.
    """
    cam = ensure_cam()

    def mjpeg_generator():
        while True:
            with cam._raw_lock:
                raw = cam._latest_raw
            if raw is None:
                time.sleep(0.01)
                continue
            img = Image.frombuffer(
                "RGB",
                (cam.w, cam.h),
                raw,
                "raw",
                "BGR" if cam.hcam.get_Option(amcam.AMCAM_OPTION_BYTEORDER) else "RGB",
                0,
                1,
            )
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            frame = buf.getvalue()

            # Yield one JPEG part following the multipart MJPEG format.
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + f"{len(frame)}".encode() + b"\r\n\r\n" +
                frame + b"\r\n"
            )
            time.sleep(0.01)  # ~100 FPS max; adjust as desired

    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ───────────────────────── health check ───────────────────────────────
@app.get("/get_ping")
def ping():
    """Health check reporting one of: connected / not-connected / not-configured.

    - "connected": we found the configured serial currently attached
    - "not-connected": config has a serial, but it isn't present now
    - "not-configured": no serial is configured in device_config.json
    """
    load_config()  # reload in case the config was updated while running
    name: Optional[str] = assigned_device_name

    if assigned_device_serial:
        status = "connected" if _serial_present(assigned_device_serial) else "not-connected"
    else:
        status = "not-configured"
        name = None

    return {"status": status, "name": name}


# No public enumeration/switch routes and absolutely no device_id handling.
