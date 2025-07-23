
"""
launch.py  –  build/(re)start containers from a chosen Docker-Compose file
▶  Lists compose files under this repo (recursive)
▶  Prompts for rebuild if an image already exists
▶  Starts backend first, waits for it, then starts frontend
▶  Opens the first exposed host port of each launched service in the default browser
"""
import subprocess, sys, socket, time, webbrowser, re
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
    
    # Set the common root directory (root of the project)
    common_root = Path(__file__).resolve().parent.parent
    
    for i, p in enumerate(items, 1):
        try:
            # Make paths relative to the project root directory
            rel = p.relative_to(common_root)
        except ValueError:
            # Fallback: use the filename if relative path computation fails
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
    ports = service_dict.get("ports", [])
    out = []
    for entry in ports:
        if isinstance(entry, int):
            out.append(entry)
        elif isinstance(entry, str):
            host = entry.split(":")[-2] if entry.count(":") >= 2 else entry.split(":")[0]
            if re.match(r"^\d+$", host):
                out.append(int(host))
    return out

def image_exists(image: str) -> bool:
    return bool(run(["docker", "images", "-q", image], capture=True).stdout.strip())

def wait_ping(port: int, path="/ping", timeout: int = 15) -> bool:
    import urllib.request
    url = f"http://localhost:{port}{path}"
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except:
            pass
        time.sleep(0.5)
    return False

# ───────────────── main ──────────────────────────────────────────────────────
def main():
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
        backend_name, frontend_name = names
    else:
        print("Detected services:")
        for i, name in enumerate(services, 1):
            print(f" {i:2d}) {name}")
        b_idx = int(input("Pick backend service number (or 0 if none): "))
        f_idx = int(input("Pick frontend service number (or 0 if none): "))
        backend_name = list(services)[b_idx-1] if b_idx else None
        frontend_name = list(services)[f_idx-1] if f_idx else None

    docker_ok()
    up_order = []

    for role, name in (("backend", backend_name), ("frontend", frontend_name)):
        if not name:
            continue
        img = services[name].get("image", name)
        if image_exists(img):
            print(f"[INFO] Found existing image for {role} ({img})")
            rebuild = input(f"Rebuild {role}? [y/N] ").strip().lower().startswith("y")
        else:
            print(f"[INFO] No existing image for {role} – will build.")
            rebuild = True

        if rebuild:
            print(f"[INFO] Building image for {role}...")
            if run(["docker", "compose", "-f", str(chosen), "build", "--pull", name]).returncode != 0:
                die(f"Build failed for {role}.")

        cmd = ["docker", "compose", "-f", str(chosen), "up", "-d", "--force-recreate", name]
        if run(cmd).returncode != 0:
            die(f"Docker compose failed starting {role}.")
        up_order.append((name, services[name]))

        ports = host_ports(services[name])
        if role == "backend" and ports:
            if wait_ping(ports[0]):
                print(f"[OK] Backend at http://localhost:{ports[0]}/ping is ready")
            else:
                print("[WARN] Backend did not respond to /ping within timeout.")

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

