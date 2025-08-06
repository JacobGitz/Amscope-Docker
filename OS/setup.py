#!/usr/bin/env python3
"""
setup_docker.py – Add a new camera service to a Docker-Compose stack

• Recursively lists compose files.
• Appends a camN service with its own host port.
• Enumerates AmScope cameras; writes device_config.json
  into Code/Project/Controller+fastapi/ (same dir as Dockerfile).
• Optionally builds the new service image.

Repo layout assumed:
  Amscope-Docker/
  ├── Code/Project/Controller+fastapi/
  │      ├── Dockerfile
  │      └── amscope_server.py
  └── OS/
         └── setup_docker.py   ← this file
"""

from __future__ import annotations

import os, re, sys, json, yaml, socket, subprocess, shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

# ───────────────────────────────────────── AmScope / USB ─────────
try:
    import amcam
except ImportError as exc:
    raise SystemExit(
        "The amcam SDK package is required. Please install it before running setup."
    ) from exc

try:
    import usb.core  # type: ignore
    import usb.util  # type: ignore
except Exception:
    usb = None  # sentinel if pyusb missing

# ───────────────────────────────────────── helpers ───────────────
def die(msg: str, code: int = 1):
    print(f"[ERROR] {msg}")
    sys.exit(code)

def run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, text=True)
    if res.returncode:
        die(f"Command failed: {' '.join(cmd)}")

def find_compose_files(root: Path):
    pats = ("docker-compose*.yml", "docker-compose*.yaml",
            "compose*.yml", "compose*.yaml")
    out: list[Path] = []
    for pat in pats:
        out.extend(root.rglob(pat))
    return sorted(set(out))

def choose_from_list(items: list[Path], prompt: str) -> Path:
    print(prompt)
    common_root = repo_root
    for i, p in enumerate(items, 1):
        try:
            rel = p.relative_to(common_root)
        except ValueError:
            rel = p.name
        print(f" {i:2d}) {rel}")
    try:
        idx = int(input("> ")) - 1
    except ValueError:
        die("Invalid selection.")
    if idx not in range(len(items)):
        die("Choice out of range.")
    return items[idx]

# ─────────────────────────────────── compose-edit helpers ────────
def pick_free_port(start: int = 8001, end: int = 8999) -> int:
    """Return first TCP port in range that isn't in use."""
    def busy(p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", p)) == 0
    for p in range(start, end + 1):
        if not busy(p):
            return p
    raise RuntimeError("No free port in range")

def next_service_name(svcs: dict, base: str = "cam") -> str:
    nums = {int(m.group(1)) for s in svcs
            if (m := re.fullmatch(fr"{base}(\d+)", s))}
    n = 1
    while n in nums:
        n += 1
    return f"{base}{n}"

def append_camera_service(
    compose_path: Path,
    image_name: str,
    tag: str,
    internal_port: int,
    host_port: int | None,
) -> tuple[str, int]:
    with compose_path.open("r", encoding="utf-8") as f:
        compose = yaml.safe_load(f) or {}
    svcs = compose.setdefault("services", {})
    svc = next_service_name(svcs)
    host_port = host_port or pick_free_port()

    svcs[svc] = {
        "image": f"{image_name}:{tag}",
        "container_name": svc,
        "environment": {"PORT": str(internal_port)},
        "ports": [f"{host_port}:{internal_port}"],
    }

    with compose_path.open("w", encoding="utf-8") as f:
        yaml.dump(compose, f, default_flow_style=False)

    print(f"✓ Added {svc}  →  host:{host_port}  ({image_name}:{tag})")
    return svc, host_port

# ─────────────────────────────────── camera discovery ────────────
def _usb_info(serial: str) -> tuple[Optional[str], Optional[str]]:
    if serial and usb:
        for dev in usb.core.find(find_all=True):
            try:
                s = usb.util.get_string(dev, dev.iSerialNumber) if dev.iSerialNumber else None
            except Exception:
                s = None
            if s and s.strip() == serial:
                return f"0x{dev.idVendor:04x}", f"0x{dev.idProduct:04x}"
    return None, None

def list_cameras() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, dev in enumerate(amcam.Amcam.EnumV2()):
        serial = vid = pid = None
        h = None
        try:
            h = amcam.Amcam.Open(dev.id)
            if h:
                try:
                    serial = h.SerialNumber()
                except Exception:
                    pass
                if serial:
                    vid, pid = _usb_info(serial)
        except Exception:
            pass
        finally:
            try:
                if h:
                    h.Close()
            except Exception:
                pass
        out.append({
            "index": idx,
            "id": dev.id,
            "name": dev.displayname,
            "serial": serial,
            "vid": vid,
            "pid": pid,
        })
    return out

# ────────────────────────────────────────── main ────────────────
repo_root = Path(__file__).resolve().parents[1]          # Amscope-Docker/
controller_dir = repo_root / "Code/Project/Controller+fastapi"
internal_port = 8000

def main():
    # 1) pick compose file
    cmp_files = find_compose_files(repo_root)
    cmp_path  = choose_from_list(cmp_files, "\nSelect a compose file:")

    # 2) get image info
    img = input("Docker image name [amscope-camera-backend]: ").strip() or "amscope-camera-backend"
    tag = input("Unique tag for this camera [camera-1]: ").strip() or "camera-1"
    hp  = input("Host port (blank ⇒ auto): ").strip()
    host_port = int(hp) if hp else None

    # 3) select camera *before* building (so file is ready)
    devs = list_cameras()
    if not devs:
        die("No cameras detected.")
    for d in devs:
        print(f" {d['index']}) {d['name']}  (Serial: {d['serial']})")
    sel = int(input("Pick camera [0]: ") or "0")
    cam = devs[sel]

    # 4) write device_config.json into Controller+fastapi/
    cfg_path = controller_dir / "device_config.json"
    cfg = {
        "device_id": cam["id"],
        "device_name": cam["name"],
        "serial_number": cam["serial"],
        "vendor_id": cam["vid"],
        "product_id": cam["pid"],
    }
    controller_dir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2))
    print(f"📄  device_config.json → {cfg_path.relative_to(repo_root)}")

    # 5) append service
    svc, host_port = append_camera_service(
        cmp_path, img, tag, internal_port, host_port
    )

    # 6) optionally build *after* config file exists in context
    if input("Build the new service image now? [y/N] ").lower().startswith("y"):
        print("[INFO] Building …")
        run(["docker", "compose", "-f", str(cmp_path), "build", "--pull", svc])

    # 7) final hint
    rel_cmp = cmp_path.relative_to(repo_root)
    print("\nNext step:")
    print(f"  docker compose -f {rel_cmp} up -d {svc}")
    print(f"  # API will be reachable at http://<host>:{host_port}/")

if __name__ == "__main__":
    main()

