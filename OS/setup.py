#!/usr/bin/env python3
"""
setup_docker.py — Manage camera containers in a docker-compose stack

What this script does:
  • Lists USB devices (via PyUSB) so you can pick one
  • If the picked device has no USB serial, it offers to call vendor-serial-identifier.py
    (which can use your local OS/amcam.py SDK to get a per-device serial and SDK IDs)
  • Writes Code/Project/Controller+fastapi/device_config.json BEFORE any build
  • Adds/Removes services in a docker-compose file
  • Optionally builds, and always exports the resulting image as Docker-images/<image>_<tag>.tar

Repo layout (derived at runtime — no absolute paths):
Amscope-Docker/
├── Code/Project/Controller+fastapi/
│     └── (Dockerfile, amscope_server.py, device_config.json …)
├── Docker-images/
└── OS/
      ├── setup_docker.py           ← this file
      └── vendor-serial-identifier.py
"""

from __future__ import annotations

# stdlib
import os
import sys
import json
import yaml
import socket
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

#-----------------------------libusb install for windows --------------
import urllib.request
import zipfile
import platform 
import ctypes

LIBUSB_VERSION = "1.0.26.11754"
DLL_FILENAME = "libusb.dll"
LOCAL_DLL_PATH = os.path.join(os.path.dirname(__file__), "libs", DLL_FILENAME)

import usb.backend.libusb1

backend = usb.backend.libusb1.get_backend()
if not backend:
    print("[ERROR] PyUSB cannot find a usable libusb backend.")
else:
    print("[OK] PyUSB backend is available.")

def setup_libusb_windows():
    if os.path.exists(LOCAL_DLL_PATH):
        print(f"[INFO] Found existing {DLL_FILENAME}")
    else:
        print(f"[INFO] {DLL_FILENAME} not found. Downloading libusb...")
        download_and_extract_libusb()

    # Add DLL folder to runtime path
    try:
        os.add_dll_directory(os.path.dirname(LOCAL_DLL_PATH))
    except AttributeError:
        # For older Python versions that don’t support add_dll_directory
        os.environ["PATH"] = os.path.dirname(LOCAL_DLL_PATH) + os.pathsep + os.environ["PATH"]

    # 💥 FORCE DLL to load now
    try:
        ctypes.CDLL(LOCAL_DLL_PATH)
        print("[INFO] libusb DLL successfully loaded")
    except OSError as e:
        print(f"[ERROR] Failed to load {DLL_FILENAME}: {e}")
        sys.exit(1)

    print("[INFO] libusb DLL path set for runtime")

def download_and_extract_libusb():
    zip_url = f"https://github.com/libusb/libusb/releases/download/v{LIBUSB_VERSION}/libusb-{LIBUSB_VERSION}.zip"
    zip_path = os.path.join(os.path.dirname(__file__), "libusb.zip")

    urllib.request.urlretrieve(zip_url, zip_path)
    print("[INFO] libusb.zip downloaded")

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(os.path.join(os.path.dirname(__file__), "libusb_extracted"))

    # Copy DLL from MS64\dll into ./libs/
    src_dll_path = os.path.join(os.path.dirname(__file__), "libusb_extracted", f"libusb-{LIBUSB_VERSION}", "MS64", "dll", DLL_FILENAME)
    os.makedirs(os.path.dirname(LOCAL_DLL_PATH), exist_ok=True)
    with open(src_dll_path, 'rb') as src, open(LOCAL_DLL_PATH, 'wb') as dst:
        dst.write(src.read())

    print(f"[INFO] {DLL_FILENAME} extracted to ./libs/")

    # Cleanup
    os.remove(zip_path)

def check_os_and_setup_libusb():
    current_os = platform.system()
    print(f"[INFO] Detected OS: {current_os}")

    if current_os == "Windows":
        setup_libusb_windows()
    elif current_os == "Linux":
        print("[INFO] You're on Linux. Please make sure libusb is installed (e.g., sudo apt install libusb-1.0-0-dev).")
    elif current_os == "Darwin":
        print("[INFO] You're on macOS. Please make sure libusb is installed (e.g., brew install libusb).")
    else:
        print("[WARNING] Unsupported OS. libusb may not work.")

# Call this before using PyUSB
check_os_and_setup_libusb()

# third-party (required): pyusb
try:
    import usb.core          # type: ignore
    import usb.util          # type: ignore
except ImportError as exc:
    raise SystemExit("PyUSB is required. run: 'pip install pyusb' or refer to the readme") from exc


# ------------------------- paths & constants -------------------------

# OS_DIR is .../Amscope-Docker/OS
OS_DIR: Path = Path(__file__).resolve().parent

# REPO_ROOT is the repo top: .../Amscope-Docker
REPO_ROOT: Path = OS_DIR.parent

# sanity check: REPO_ROOT/OS should be this folder
if (REPO_ROOT / "OS").resolve() != OS_DIR:
    raise SystemExit("[ERROR] Repo root detection failed. Expected REPO_ROOT/OS to be this script's folder.")

# Where the FastAPI backend expects device_config.json
CTRL_DIR: Path = REPO_ROOT / "Code/Project/Controller+fastapi"

# Where to drop exported images
IMAGES_DIR: Path = REPO_ROOT / "Docker-images"

# Container internals
INTERNAL_PORT = 8000
DEFAULT_IMAGE = "amscope-camera-backend"

# Optional friendly labels (edit for your lab)
KNOWN_DEVICES: Dict[str, str] = {
    "0x0547": "[Amscope] (Anchor/Cypress)",
    "0x1d6b": "[Linux Foundation] USB Root Hub",
}
# Optional model labels keyed by (VID, PID)
KNOWN_MODELS: Dict[tuple[str, str], str] = {
    # ("0x0547", "0x6310"): "Amscope Camera (0547:6310)",
}


# --------------------------- small helpers ---------------------------

def die(msg: str, code: int = 1) -> None:
    """Print an error and exit."""
    print(f"[ERROR] {msg}")
    sys.exit(code)

def run(cmd: List[str], capture: bool = False,
        cwd: Optional[Path] = None, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    """Run a command safely. Never crash if the binary is missing; just return rc=127."""
    try:
        return subprocess.run(
            cmd,
            text=True,
            capture_output=capture,
            check=False,
            cwd=str(cwd) if cwd else None,
            env=env
        )
    except FileNotFoundError as e:
        return subprocess.CompletedProcess(cmd, 127, stdout="", stderr=str(e))

def run_or_die(cmd: List[str]) -> None:
    """Run a command and abort on non-zero exit status."""
    if run(cmd).returncode:
        die(f"Command failed: {' '.join(cmd)}")

def is_port_busy(port: int) -> bool:
    """Is TCP port bound on localhost?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

def pick_free_port(start: int = 8000, end: int = 8999, taken: Optional[set[int]] = None) -> int:
    """Pick the first port in [start, end] that isn't in 'taken' and isn't bound."""
    taken = taken or set()
    for p in range(start, end + 1):
        if p in taken:
            continue
        if not is_port_busy(p):
            return p
    raise RuntimeError("No free port available")

def list_compose_files(root: Path) -> List[Path]:
    """Find docker-compose files anywhere under the repo."""
    patterns = ("docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml")
    out: List[Path] = []
    for pat in patterns:
        out.extend(root.rglob(pat))
    return sorted(set(out))

def choose_from(items: List[str], prompt: str) -> int:
    """Render a numbered list and return the chosen index (0-based)."""
    for i, txt in enumerate(items, 1):
        print(f" {i:2d}) {txt}")
    try:
        idx = int(input(prompt)) - 1
    except ValueError:
        die("Invalid selection.")
    if idx not in range(len(items)):
        die("Choice out of range.")
    return idx

def load_compose(path: Path) -> dict:
    """Load a YAML compose file (empty dict if missing/empty)."""
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_compose(path: Path, data: dict) -> None:
    """Write a YAML compose file."""
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)

def _get_string(dev, idx: Optional[int]) -> Optional[str]:
    """Safely read a USB string descriptor."""
    if not idx:
        return None
    try:
        return usb.util.get_string(dev, idx)
    except Exception:
        return None


# ------------------------ USB device enumeration ------------------------

def discover_usb_devices_all() -> List[Dict[str, Any]]:
    """
    Enumerate all USB devices. We never rely on bus/port path.
    If a device has no USB serial, we mark it with a clear warning.
    """
    devices: List[Dict[str, Any]] = []
    backend = usb.backend.libusb1.get_backend(find_library=lambda name: str(LOCAL_DLL_PATH))
    if not backend:
        die("PyUSB could not initialize libusb backend.")
    for idx, dev in enumerate(usb.core.find(find_all=True)):
        vid = f"0x{dev.idVendor:04x}"
        pid = f"0x{dev.idProduct:04x}"

        manufacturer = _get_string(dev, getattr(dev, "iManufacturer", None))
        product      = _get_string(dev, getattr(dev, "iProduct", None))
        serial       = _get_string(dev, getattr(dev, "iSerialNumber", None))

        vendor_name = KNOWN_DEVICES.get(vid, "unknown device")
        model_name  = KNOWN_MODELS.get((vid, pid))

        # Build a readable one-line label
        parts = [vendor_name]
        if model_name: parts.append(model_name)
        parts.append(f"USB {vid}:{pid}")
        if product: parts.append(product)
        if manufacturer: parts.append(f"by {manufacturer}")
        parts.append(f"serial:{serial}" if serial else "⚠ NO SERIAL (try vendor SDK)")

        devices.append({
            "index": idx,
            "vendor_id": vid,
            "product_id": pid,
            "vendor_name": vendor_name,
            "model_name": model_name,
            "manufacturer": manufacturer,
            "product": product,
            "serial": serial,               # None if there is no USB serial
            "has_serial": bool(serial),
            "display": " - ".join(parts),
        })
    return devices


# ------------------------- vendor SDK invocation -------------------------

def _iter_candidate_pythons() -> List[str]:
    """
    Yield usable python interpreters to run vendor-serial-identifier.py.
    Order:
      1) $VENDOR_PYTHON (if set)
      2) current interpreter (sys.executable)
      3) anything named 'python3' or 'python' on PATH
    """
    order: List[str] = []
    if os.environ.get("VENDOR_PYTHON"):
        order.append(os.environ["VENDOR_PYTHON"])
    order.append(sys.executable)
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path:
            order.append(path)
    # de-dupe while preserving order
    seen, out = set(), []
    for p in order:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out

def try_vendor_identifier(vid_hex: str, pid_hex: str) -> Optional[dict]:
    """
    Ask vendor-serial-identifier.py to resolve a serial and SDK IDs for the given VID/PID.
    Returns a dict with keys:
      serial, device_id, device_name, vendor_id, product_id
    or None if we couldn't resolve it.
    """
    tool = OS_DIR / "vendor-serial-identifier.py"
    if not tool.exists():
        print("[INFO] vendor-serial-identifier.py not found. Skipping.")
        return None

    # ensure the tool can import local OS/amcam.py
    env = os.environ.copy()
    env["PYTHONPATH"] = str(OS_DIR) + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")

    for py in _iter_candidate_pythons():
        proc = run([py, str(tool), "--json", "--vid", vid_hex, "--pid", pid_hex],
                   capture=True, cwd=OS_DIR, env=env)
        if proc.returncode != 0:
            continue

        # parse JSON (empty list if parse fails)
        try:
            candidates = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            continue
        if not candidates:
            continue

        # prefer exact VID/PID matches if available
        matching = [
            c for c in candidates
            if (c.get("vendor_id") or "").lower() == vid_hex.lower()
            and (c.get("product_id") or "").lower() == pid_hex.lower()
        ]
        pool = matching or candidates

        # one result → use it
        if len(pool) == 1:
            c = pool[0]
            return {
                "serial": c.get("serial"),
                "device_id": c.get("device_id"),
                "device_name": c.get("display_name") or c.get("device_name"),
                "vendor_id": c.get("vendor_id") or vid_hex,
                "product_id": c.get("product_id") or pid_hex,
            }

        # multiple results → let the user choose
        print("\nVendor SDK returned multiple serials. Select one:")
        for i, c in enumerate(pool, 1):
            label = c.get("display_name") or c.get("device_name") or c.get("source") or "device"
            print(f" {i:2d}) {label}  serial:{c.get('serial')}  (src={c.get('source')})")
        sel = input(f"Pick [1-{len(pool)}] (or blank to cancel): ").strip()
        if not sel:
            continue
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(pool):
                c = pool[idx]
                return {
                    "serial": c.get("serial"),
                    "device_id": c.get("device_id"),
                    "device_name": c.get("display_name") or c.get("device_name"),
                    "vendor_id": c.get("vendor_id") or vid_hex,
                    "product_id": c.get("product_id") or pid_hex,
                }
        except ValueError:
            pass

    # nothing worked
    return None


# ---------------------- write device_config.json safely ----------------------

def write_device_config_atomic(payload: dict, ctrl_dir: Path) -> Path:
    """
    Write device_config.json atomically:
      • write to a temp file in the same folder
      • fsync
      • replace into final name
    Then re-read & verify required keys exist.
    """
    ctrl_dir.mkdir(parents=True, exist_ok=True)
    target = ctrl_dir / "device_config.json"

    fd, tmp_path = tempfile.mkstemp(prefix="device_config.", suffix=".json", dir=str(ctrl_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)  # atomic on POSIX
    finally:
        # if anything went weird, make sure the temp file doesn't hang around
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    # quick sanity check: file is readable and has what the backend expects
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"device_config.json verification failed: {e}")

    required = ["device_id", "device_name", "serial_number", "vendor_id", "product_id"]
    missing = [k for k in required if k not in data or data[k] in (None, "")]
    if missing:
        die(f"device_config.json missing required fields: {missing}")

    return target


# ------------------------------ ADD a service ------------------------------

def add_service(compose_path: Path) -> None:
    compose = load_compose(compose_path)
    svcs: dict = compose.setdefault("services", {})

    # list USB devices up front
    devices = discover_usb_devices_all()
    if not devices:
        die("No USB devices detected.")

    # collect ports already used by other services in this compose file
    taken_ports = {
        int(str(prt).split(":")[0])
        for svc in svcs.values()
        for prt in svc.get("ports", [])
        if str(prt).split(":")[0].isdigit()
    }

    # 1) service/container name (must be unique within the compose file)
    while True:
        svc_name = input("Service/Container name (e.g. cam1): ").strip()
        if not svc_name:
            die("Service name cannot be blank.")
        if svc_name in svcs:
            print("That name already exists.")
            continue
        break

    # 2) image + tag (we use the service name as the tag for clarity)
    img = input(f"Docker image name [{DEFAULT_IMAGE}]: ").strip() or DEFAULT_IMAGE
    tag = svc_name

    # 3) host port assignment (keep trying until valid)
    while True:
        hp = input("Host port 8000-8999 (blank ⇒ auto-pick): ").strip()
        if hp == "":
            host_port = pick_free_port(start=8000, end=8999, taken=taken_ports)
            print(f"[auto] Selected free port {host_port}")
            break
        try:
            host_port = int(hp)
        except ValueError:
            print("Please enter a number (e.g., 8012) or leave blank for auto.")
            continue
        if not (8000 <= host_port <= 8999):
            print("Port must be between 8000 and 8999.")
            continue
        if host_port in taken_ports:
            print(f"Host port {host_port} is already used by another service in this compose file.")
            continue
        if is_port_busy(host_port):
            print(f"Host port {host_port} is already in use on this machine.")
            continue
        break

    # 4) let the user pick a device from the list
    for d in devices:
        print(f" {d['index']}) {d['display']}")
    while True:
        try:
            dev_idx = int((input("Pick device [0]: ") or "0"))
            dev = devices[dev_idx]
            break
        except (ValueError, IndexError):
            print("Please enter a valid index from the list.")

    # If the device exposes no USB serial, offer the vendor SDK path (local OS/amcam.py)
    sdk_meta: Optional[dict] = None
    if not dev["has_serial"]:
        ans = input("This device has NO USB serial. Try vendor SDK to resolve one? [y/N] ").strip().lower()
        if ans.startswith("y"):
            sdk_meta = try_vendor_identifier(dev["vendor_id"], dev["product_id"])
            if not sdk_meta or not sdk_meta.get("serial"):
                die("Could not resolve a serial via vendor SDK.")
            dev["serial"] = sdk_meta["serial"]
            dev["has_serial"] = True
        else:
            die("A serial number is required to uniquely identify the device across systems.")

    # Build the payload for device_config.json
    # NOTE: amscope_server.py expects a real SDK device_id for Amscope (VID 0x0547)
    vendor_id  = (sdk_meta.get("vendor_id")  if sdk_meta else None) or dev["vendor_id"]
    product_id = (sdk_meta.get("product_id") if sdk_meta else None) or dev["product_id"]

    if vendor_id.lower() == "0x0547":
        # Amscope requires the SDK's device_id so the server can open it
        if not sdk_meta or not sdk_meta.get("device_id"):
            die("Amscope device detected (VID 0x0547) but no SDK device_id was provided.\n"
                "Install/enable the Amscope SDK (amcam) so the vendor tool can supply device_id.")
        device_id = sdk_meta["device_id"]
        device_name = sdk_meta.get("device_name") or "Amscope Camera"
    else:
        # Non-Amscope: we can fall back to a stable label if the SDK didn't provide one
        device_id = (sdk_meta.get("device_id") if sdk_meta else None) or f"{vendor_id}:{product_id}"
        device_name = (sdk_meta.get("device_name") if sdk_meta else None) or \
                      f"{dev['vendor_name']} USB {vendor_id}:{product_id}"

    payload = {
        "device_id": device_id,
        "device_name": device_name,
        "serial_number": dev["serial"],   # unique identifier we will rely on
        "vendor_id": vendor_id,
        "product_id": product_id,
    }

    # 5) write device_config.json BEFORE any build and verify it looks right
    cfg_path = write_device_config_atomic(payload, CTRL_DIR)
    print(f"📄  device_config.json written → {cfg_path}")

    # 6) add/update the compose service
    svcs[svc_name] = {
        "build": "./Controller+fastapi",
        "image": f"{img}:{tag}",
        "container_name": svc_name,
        "privileged": True,
        "devices": ["/dev:/dev"],
        "restart": "unless-stopped",
        "environment": {"TZ": "America/New_York", "PORT": str(INTERNAL_PORT)},
        "ports": [f"{host_port}:{INTERNAL_PORT}"],
    }
    save_compose(compose_path, compose)
    print(f"✓ Added service **{svc_name}** on host port {host_port}")

    # 7) optional build (config is already on disk for the server to read)
    if input("Build this image now? [y/N] ").lower().startswith("y"):
        if not cfg_path.exists():
            die("device_config.json missing just before build; aborting.")
        run_or_die(["docker", "compose", "-f", str(compose_path), "build", "--pull", svc_name])

    # 8) export the image to Docker-images/<image>_<tag>.tar
    full_ref = f"{img}:{tag}"
    print(f"[INFO] Exporting {full_ref} …")
    IMAGES_DIR.mkdir(exist_ok=True)
    tar_path = IMAGES_DIR / f"{img.replace('/','_')}_{tag}.tar"
    if tar_path.exists():
        print(f"  (overwriting existing {tar_path.name})")
        tar_path.unlink()
    run_or_die(["docker", "save", "-o", str(tar_path), full_ref])
    print(f"[OK] Image archived → {tar_path.relative_to(REPO_ROOT)}")

    rel = compose_path.relative_to(REPO_ROOT)
    print(f"\nNext:\n  docker compose -f {rel} up -d {svc_name}")
    print(f"  # API: http://<host>:{host_port}/")

# ----------------------------- DELETE a service -----------------------------

def delete_service(compose_path: Path) -> None:
    compose = load_compose(compose_path)
    svcs: dict = compose.get("services", {})
    if not svcs:
        die("No services defined.")
    victim_idx = choose_from(list(svcs), "Select a service to delete: ")
    victim = list(svcs)[victim_idx]
    if input(f"Type YES to delete '{victim}': ") != "YES":
        print("Aborted.")
        return
    svcs.pop(victim)
    save_compose(compose_path, compose)
    print(f"✓ Removed service '{victim}'")

# --------------------------------- main ------------------------------------

def main() -> None:
    files = list_compose_files(REPO_ROOT)
    if not files:
        die("No docker-compose files found.")
    cmp_idx = choose_from([str(f.relative_to(REPO_ROOT)) for f in files], "\nPick a docker-compose file: ")
    compose_path = files[cmp_idx]

    act_idx = choose_from(["Add a camera service", "Delete a service", "Quit"], "\nSelect action: ")
    if act_idx == 0:
        add_service(compose_path)
    elif act_idx == 1:
        delete_service(compose_path)
    else:
        print("Bye!")

if __name__ == "__main__":
    main()

