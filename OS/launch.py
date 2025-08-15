#!/usr/bin/env python3
"""
launch.py – load a saved .tar image if needed, then start a service
            and open its FastAPI docs page.

Workflow
────────
1. Lists compose files inside the repo (recursive).
2. Lets you pick one, then shows its services.
3. For the selected service:
   • If the Docker image isn’t present, looks for
     Docker-images/<image>_<tag>.tar, loads it.
   • Runs `docker compose up -d <service>`.
   • Finds the first host-side port mapped to the container and
     opens `http://localhost:<port>/docs` in your default browser.

Images must have been archived by setup_docker.py as
Docker-images/<image path slashes replaced by _>_<tag>.tar
(e.g. amscope-camera-backend_camera-7.tar).
"""
from __future__ import annotations
import subprocess, sys, re, time, urllib.request, webbrowser
from pathlib import Path
from typing import List

REPO_ROOT  = Path(__file__).resolve().parents[1]
IMAGES_DIR = REPO_ROOT / "Docker-images"

# ───────── helpers ──────────────────────────────────────────────
def die(msg, code=1):
    print(f"[ERROR] {msg}"); sys.exit(code)

def run(cmd: List[str], capture=False):
    return subprocess.run(cmd, text=True,
                          capture_output=capture, check=False)

def docker_ready():
    if run(["docker", "info"]).returncode != 0:
        die("Docker daemon not running or docker CLI missing.")

def find_compose_files(root: Path) -> List[Path]:
    pats = ("docker-compose*.yml", "docker-compose*.yaml",
            "compose*.yml", "compose*.yaml")
    out: List[Path] = []
    for pat in pats: out.extend(root.rglob(pat))
    return sorted(set(out))

def choose(items: list[str], prompt: str) -> int:
    for i, v in enumerate(items, 1): print(f" {i:2d}) {v}")
    try: idx = int(input(prompt)) - 1
    except ValueError: die("Invalid selection.")
    if idx not in range(len(items)): die("Choice out of range.")
    return idx

def load_yaml(path: Path):
    import yaml; return yaml.safe_load(path.read_text()) or {}

def image_exists(ref: str) -> bool:
    return bool(run(["docker", "images", "-q", ref], capture=True).stdout.strip())

def archive_path(img: str, tag: str) -> Path:
    return IMAGES_DIR / f"{img.replace('/','_')}_{tag}.tar"

def host_ports(service_dict: dict) -> List[int]:
    """Return host-side ports extracted from a Compose service block."""
    ports = service_dict.get("ports", [])
    out: List[int] = []
    for entry in ports:
        if isinstance(entry, int):
            out.append(entry)
        elif isinstance(entry, str):
            # handle forms like "8005:8000" or "0.0.0.0:8005:8000"
            parts = entry.split(":")
            host = parts[-2] if len(parts) >= 3 else parts[0]
            if re.fullmatch(r"\d+", host): out.append(int(host))
    return out

def wait_http(port: int, path: str = "/docs", timeout: int = 20) -> bool:
    url = f"http://localhost:{port}{path}"
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200: return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

# ───────── main ─────────────────────────────────────────────────
def main():
    docker_ready()

    # 1. pick compose
    files = find_compose_files(REPO_ROOT)
    if not files: die("No docker-compose files found.")
    cidx  = choose([str(p.relative_to(REPO_ROOT)) for p in files],
                   "\nSelect a compose file: ")
    cfile = files[cidx]
    data  = load_yaml(cfile)
    svcs  = data.get("services", {})
    if not svcs: die("No services defined.")

    # 2. pick service
    sidx = choose(list(svcs), "Pick a service to start: ")
    svc  = list(svcs)[sidx]
    svc_dict = svcs[svc]

    img_field = svc_dict.get("image", svc)
    img, tag = img_field.split(":", 1) if ":" in img_field else (img_field, "latest")
    full_ref = f"{img}:{tag}"

    # 3. ensure image present
    if not image_exists(full_ref):
        tar = archive_path(img, tag)
        if not tar.exists():
            die(f"Image archive {tar.relative_to(REPO_ROOT)} not found.")
        print(f"[INFO] Loading image from {tar.relative_to(REPO_ROOT)} …")
        if run(["docker", "load", "-i", str(tar)]).returncode != 0:
            die("docker load failed.")
        print("[OK] Image loaded.")

    # 4. start container
    print(f"[INFO] Starting service '{svc}' …")
    if run(["docker", "compose", "-f", str(cfile), "up", "-d", svc]).returncode != 0:
        die("docker compose up failed.")

    # 5. open FastAPI docs
    ports = host_ports(svc_dict)
    if not ports:
        print("[WARN] Could not determine host port; skipping browser open.")
        return
    port = ports[0]
    print(f"[INFO] Waiting for http://localhost:{port}/docs …")
    if wait_http(port):
        webbrowser.open(f"http://localhost:{port}/docs")
        print("[OK] Docs opened in your browser.")
    else:
        print("[WARN] Service didn't answer within timeout; open browser manually.")

if __name__ == "__main__":
    main()

