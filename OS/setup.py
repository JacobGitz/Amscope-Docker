#!/usr/bin/env python3
"""
setup_docker.py – Manage camera containers in a docker-compose stack

Features
────────
• ADD  – append a fully configured camera service block.
• DELETE – remove an existing service block.
• Writes `device_config.json` into Code/Project/Controller+fastapi/ before any build.
• Optionally builds the new image AND always exports it to
  Docker-images/<image>_<tag>.tar (relative to the repo root).
• Prevents duplicate service names and host-side ports.

Repo layout (resolved dynamically – no hard-coded absolute paths)
──────────────────────────────────────────────────────────────────
Amscope-Docker/
├── Code/Project/Controller+fastapi/
│     └── (Dockerfile, amscope_server.py, device_config.json …)
├── Docker-images/
│     └── amscope-camera-backend_camera-7.tar   ← auto-created
└── OS/
      └── setup_docker.py   ← THIS SCRIPT
"""
from __future__ import annotations

import os, re, sys, json, yaml, socket, subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# ──────────── external deps ─────────────────────────────────────
try:
    import amcam
except ImportError as exc:
    raise SystemExit("The amcam SDK package is required.") from exc

try:
    import usb.core          # type: ignore
    import usb.util          # type: ignore
except Exception:
    usb = None               # pyusb missing/failed

# ──────────── constants & paths ─────────────────────────────────
REPO_ROOT     = Path(__file__).resolve().parents[1]   # Amscope-Docker/
CTRL_DIR      = REPO_ROOT / "Code/Project/Controller+fastapi"
IMAGES_DIR    = REPO_ROOT / "Docker-images"
INTERNAL_PORT = 8000
DEFAULT_IMAGE = "amscope-camera-backend"

# ──────────── helpers ───────────────────────────────────────────
def die(msg: str, code: int = 1):
    print(f"[ERROR] {msg}")
    sys.exit(code)

def run(cmd: list[str], capture=False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=capture, check=False)

def run_or_die(cmd: list[str]):
    if run(cmd).returncode:
        die(f"Command failed: {' '.join(cmd)}")

def pick_free_port(start=8001, end=8999, taken: set[int] | None = None) -> int:
    taken = taken or set()
    def busy(p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", p)) == 0
    for p in range(start, end + 1):
        if p not in taken and not busy(p):
            return p
    raise RuntimeError("No free port available")

def list_compose_files(root: Path):
    pats = ("docker-compose*.yml", "docker-compose*.yaml",
            "compose*.yml", "compose*.yaml")
    out: list[Path] = []
    for pat in pats:
        out.extend(root.rglob(pat))
    return sorted(set(out))

def choose_from(items: list[str], prompt: str) -> int:
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
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_compose(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)

# ──────────── camera enumeration ───────────────────────────────
def _usb_ids(serial: str) -> tuple[Optional[str], Optional[str]]:
    if serial and usb:
        for dev in usb.core.find(find_all=True):
            try:
                s = usb.util.get_string(dev, dev.iSerialNumber) if dev.iSerialNumber else None
            except Exception:
                s = None
            if s and s.strip() == serial:
                return f"0x{dev.idVendor:04x}", f"0x{dev.idProduct:04x}"
    return None, None

def discover_cameras() -> List[Dict[str, Any]]:
    out = []
    for idx, dev in enumerate(amcam.Amcam.EnumV2()):
        serial = vid = pid = None
        h = None
        try:
            h = amcam.Amcam.Open(dev.id)
            if h:
                try: serial = h.SerialNumber()
                except Exception: pass
                if serial: vid, pid = _usb_ids(serial)
        finally:
            try: h and h.Close()
            except Exception: pass
        out.append({
            "index": idx, "id": dev.id, "name": dev.displayname,
            "serial": serial, "vid": vid, "pid": pid,
        })
    return out

# ──────────── ADD mode ─────────────────────────────────────────
def add_service(compose_path: Path):
    compose = load_compose(compose_path)
    svcs: dict = compose.setdefault("services", {})

    # gather existing host ports
    taken_ports = {
        int(str(prt).split(":")[0])
        for svc in svcs.values()
        for prt in svc.get("ports", [])
        if str(prt).split(":")[0].isdigit()
    }

    # 1. service name
    while True:
        svc_name = input("Service / container name (e.g. cam1): ").strip()
        if not svc_name:
            die("Service name cannot be blank.")
        if svc_name in svcs:
            print("That name already exists.")
            continue
        break

    # 2. image + tag
    img = input(f"Docker image [{DEFAULT_IMAGE}]: ").strip() or DEFAULT_IMAGE
    tag = input("Tag (unique per camera) [latest]: ").strip() or "latest"

    # 3. host port
    hp = input("Host port (blank ⇒ auto): ").strip()
    host_port = int(hp) if hp else pick_free_port(taken=taken_ports)
    if host_port in taken_ports:
        die(f"Host port {host_port} already used.")

    # 4. choose camera
    cams = discover_cameras()
    if not cams:
        die("No cameras detected.")
    for c in cams:
        print(f" {c['index']}) {c['name']} (Serial: {c['serial']})")
    cam_idx = int(input("Pick camera [0]: ") or "0")
    cam = cams[cam_idx]

    # 5. write device_config.json
    CTRL_DIR.mkdir(parents=True, exist_ok=True)
    (CTRL_DIR / "device_config.json").write_text(json.dumps({
        "device_id": cam["id"],
        "device_name": cam["name"],
        "serial_number": cam["serial"],
        "vendor_id": cam["vid"],
        "product_id": cam["pid"],
    }, indent=2))
    print(f"📄  device_config.json written to {CTRL_DIR.relative_to(REPO_ROOT)}")

    # 6. add service block
    svcs[svc_name] = {
        "build": "./Controller+fastapi",
        "image": f"{img}:{tag}",
        "container_name": svc_name,
        "privileged": True,
        "devices": ["/dev:/dev"],
        "restart": "unless-stopped",
        "environment": { "TZ": "America/New_York", "PORT": str(INTERNAL_PORT) },
        "ports": [f"{host_port}:{INTERNAL_PORT}"],
    }
    save_compose(compose_path, compose)
    print(f"✓ Added service **{svc_name}** on host port {host_port}")

    # 7. build?  (after which we always export)
    if input("Build this image now? [y/N] ").lower().startswith("y"):
        run_or_die(["docker", "compose", "-f", str(compose_path),
                    "build", "--pull", svc_name])

    # 8. export image to Docker-images/
    full_ref = f"{img}:{tag}"
    print(f"[INFO] Exporting {full_ref} …")
    IMAGES_DIR.mkdir(exist_ok=True)
    tar_path = IMAGES_DIR / f"{img.replace('/','_')}_{tag}.tar"
    if tar_path.exists():
        print(f"  (overwriting existing {tar_path.name})")
        tar_path.unlink()
    run_or_die(["docker", "save", "-o", str(tar_path), full_ref])
    print(f"[OK] Image archived → {tar_path.relative_to(REPO_ROOT)}")

    # 9. final hint
    rel = compose_path.relative_to(REPO_ROOT)
    print(f"\nNext:\n  docker compose -f {rel} up -d {svc_name}")
    print(f"  # API: http://<host>:{host_port}/")

# ──────────── DELETE mode ───────────────────────────────────────
def delete_service(compose_path: Path):
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

# ──────────── main ──────────────────────────────────────────────
def main():
    files = list_compose_files(REPO_ROOT)
    if not files:
        die("No docker-compose files found.")
    cmp_idx = choose_from(
        [str(f.relative_to(REPO_ROOT)) for f in files],
        "\nPick a docker-compose file: "
    )
    compose_path = files[cmp_idx]

    act_idx = choose_from(
        ["Add a camera service", "Delete a service", "Quit"],
        "\nSelect action: "
    )
    if act_idx == 0:
        add_service(compose_path)
    elif act_idx == 1:
        delete_service(compose_path)
    else:
        print("Bye!")

if __name__ == "__main__":
    main()

