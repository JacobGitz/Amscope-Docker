#!/usr/bin/env python3
"""
launch.py  –  build/(re)start containers from a chosen Docker-Compose file
▶  Lists compose files under this repo (recursive)
▶  Prompts for rebuild if an image already exists
▶  Starts backend first, waits for it, then starts frontend
▶  Opens the first exposed host port of each launched service in the default browser
"""
import subprocess, sys, socket, time, webbrowser, os, re
from pathlib import Path

# ───────────────── helpers ────────────────────────────────────────────────────
def die(msg: str, code: int = 1):
    print(f"[ERROR] {msg}")
    sys.exit(code)

def run(cmd: list[str], capture=False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=capture, check=False)

def docker_ok():
    if run(["docker", "info"]).returncode != 0:
        die("Docker daemon not running or docker CLI missing.")

def find_compose_files(root: Path):
    patterns = ("docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml")
    files = []
    for pat in patterns:
        files.extend(root.rglob(pat))
    return sorted(set(files))

def choose_from_list(items: list[Path], prompt: str) -> Path:
    if not items:
        die("No Docker-Compose files found.")
    print(prompt)
    compose_dir = Path(__file__).resolve().parent.parent / "Code" / "Project"
    for i, p in enumerate(items, 1):
        try:
            rel = p.relative_to(compose_dir)
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

def load_yaml(path: Path):
    try:
        import yaml
    except ModuleNotFoundError:
        die("pyyaml not installed.  `pip install pyyaml`.")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def host_ports(service_dict: dict) -> list[int]:
    """Return list of host-side ports for service (int)."""
    ports = service_dict.get("ports", [])
    out = []
    for entry in ports:
        # entry can be "8080:80", "127.0.0.1:3000:3000", or just "80"
        if isinstance(entry, int):
            out.append(entry)
        elif isinstance(entry, str):
            host = entry.split(":")[-2] if entry.count(":") >= 2 else entry.split(":")[0]
            if re.match(r"^\d+$", host):
                out.append(int(host))
    return out

def image_exists(image: str) -> bool:
    return bool(run(["docker", "images", "-q", image], capture=True).stdout.strip())

def wait_port(port: int, timeout: int = 60):
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket() as s:
            s.settimeout(1)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except (socket.timeout, ConnectionRefusedError):
                time.sleep(0.5)
    return False

# ───────────────── main ──────────────────────────────────────────────────────
def main():
# Point directly to where your compose files live
    compose_dir = Path(__file__).resolve().parent.parent / "Code" / "Project"
    compose_files = find_compose_files(compose_dir)    
    chosen = choose_from_list(compose_files, "Select a compose file to launch:")
    data = load_yaml(chosen)
    services = data.get("services", {})
    if not services:
        die("No services found in compose file.")

    backend_name = None
    frontend_name = None
    if len(services) == 2:
        names = list(services)
        backend_name, frontend_name = names  # assume order
    else:
        print("Detected services:")
        for i, name in enumerate(services, 1):
            print(f" {i:2d}) {name}")
        b_idx = int(input("Pick backend service number (or 0 if none): "))
        f_idx = int(input("Pick frontend service number (or 0 if none): "))
        backend_name = list(services)[b_idx-1] if b_idx else None
        frontend_name = list(services)[f_idx-1] if f_idx else None

    docker_ok()

    # ───── backend first ─────
    up_order = []
    if backend_name:
        img = services[backend_name].get("image", backend_name)
        rebuild = False
        if image_exists(img):
            rebuild = input(f"Rebuild existing image '{img}'? (y/N) ").lower() == "y"
        cmd = ["docker", "compose", "-f", str(chosen), "up", "-d"]
        if rebuild:
            cmd.append("--build")
        cmd.append(backend_name)
        if run(cmd).returncode != 0:
            die("Docker compose failed starting backend.")
        up_order.append((backend_name, services[backend_name]))

        # wait for first port
        ports = host_ports(services[backend_name])
        if ports and wait_port(ports[0], 60):
            print(f"[OK] Backend listening on port {ports[0]}")
        else:
            print("[WARN] Backend port not ready after 60 s.")

    # ───── frontend ─────
    if frontend_name:
        img = services[frontend_name].get("image", frontend_name)
        if image_exists(img):
            rebuild = input(f"Rebuild existing image '{img}'? (y/N) ").lower() == "y"
        else:
            rebuild = False
        cmd = ["docker", "compose", "-f", str(chosen), "up", "-d"]
        if rebuild:
            cmd.append("--build")
        cmd.append(frontend_name)
        if run(cmd).returncode != 0:
            die("Docker compose failed starting frontend.")
        up_order.append((frontend_name, services[frontend_name]))

    # ───── open browsers ─────
    for name, svc in up_order:
        ports = host_ports(svc)
        if ports:
             url = f"http://localhost:{ports[0]}"
             if name == backend_name:
                 url += "/docs"
             webbrowser.open(url)
             print(f"[INFO] Opened {url}")

    print("\n[ALL DONE] Containers running.\n")

if __name__ == "__main__":
    main()
