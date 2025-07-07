#!/usr/bin/env python3
"""Unified FastAPI server for Thorlabs TDC001 – v1.4 UI compatible (no Python Zeroconf)"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from tdc001 import TDCController, find_tdc001_ports
import logging

log = logging.getLogger("tdc-server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="TDC001 API", version="1.4.0")

controller: TDCController | None = None

# ───────────── models ─────────────

class ConnectRequest(BaseModel):
    port: str

class MoveRequest(BaseModel):
    steps: int

class AbsoluteRequest(BaseModel):
    position: int

# ───────────── helper ─────────────

def ensure_controller() -> TDCController:
    if controller is None:
        raise HTTPException(
            status_code=503,
            detail="TDC001 device not connected. Call /ports to see available devices.",
        )
    return controller

# ───────────── lifecycle ─────────────

@app.on_event("startup")
def startup_event() -> None:
    global controller
    ports = find_tdc001_ports()
    if not ports:
        log.warning("No TDC001 cubes detected at startup – API running in degraded mode.")
        controller = None
    else:
        controller = TDCController(serial_port=ports[0])
        log.info("Connected to TDC001 on %s", ports[0])

@app.on_event("shutdown")
def shutdown_event() -> None:
    global controller
    if controller:
        controller.close()
        controller = None
        log.info("TDC001 connection closed.")

# ───────────── endpoints ─────────────

@app.get("/ports")
def list_ports() -> list[str]:
    return find_tdc001_ports()

@app.post("/connect")
def connect(req: ConnectRequest):
    global controller
    try:
        if controller:
            controller.close()
        controller = TDCController(serial_port=req.port)
        return {"status": "connected", "port": req.port}
    except Exception as e:
        controller = None
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/disconnect")
def disconnect():
    global controller
    if controller:
        controller.close()
        controller = None
    return {"status": "disconnected"}

@app.get("/status")
def status():
    return ensure_controller().status

@app.post("/move_relative")
def move_relative(req: MoveRequest):
    ctrl = ensure_controller()
    try:
        ctrl.move_relative(req.steps)
        return {"status": "moved", "steps": req.steps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/move_absolute")
def move_absolute(req: AbsoluteRequest):
    ctrl = ensure_controller()
    try:
        ctrl.move_absolute(req.position)
        return {"status": "moved", "position": req.position}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/home")
def home():
    ctrl = ensure_controller()
    try:
        ctrl.home()
        return {"status": "homed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/identify")
def identify():
    ctrl = ensure_controller()
    ctrl.identify()
    return {"status": "identifying"}

@app.post("/stop")
def stop():
    ctrl = ensure_controller()
    try:
        ctrl._cube.stop(immediate=True)
        return {"status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ───────────── UI Compatibility Aliases ─────────────

@app.post("/move_rel")
def move_rel_alias(req: MoveRequest):
    return move_relative(req)

@app.post("/move_abs")
def move_abs_alias(req: AbsoluteRequest):
    return move_absolute(req)

# ───────────── Optional Health Check ─────────────
# also an identifier for the frontend to locate the actual TDC001 apis on the network
# the script will request all port 8000s on the network and send a ping request, waiting for this reply
# the user will see this as available IPs to connect to for controlling steppers

@app.get("/ping")
def ping():
    return {"backend": "TDC001"}

