#!/usr/bin/env python3
"""
setup_docker.py – Modify Docker Compose configuration
▶  Lists compose files under this repo (recursive)
▶  Allows modification of image name, tag, and port
"""
import yaml
import subprocess
import sys
import re
from pathlib import Path

# ───────────────── helpers ────────────────────────────────────────────────────
def die(msg: str, code: int = 1):
    print(f"[ERROR] {msg}")
    sys.exit(code)

def run(cmd: list[str], capture=False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=capture, check=False)

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
    common_root = Path(__file__).resolve().parent.parent  # This should resolve to the project root
    
    for i, p in enumerate(items, 1):
        try:
            # Make paths relative to the project root directory (common_root)
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

def edit_docker_compose(compose_file, new_image_name, new_port, new_tag):
    with open(compose_file, 'r') as f:
        # Load the existing docker-compose.yml
        compose_data = yaml.safe_load(f)

    # Modify the backend image, port, and tag
    services = compose_data.get('services', {})

    # Assume we are modifying the 'backend' service; this can be extended for multiple services
    backend_service = services.get('backend', {})

    # Modify image name and tag
    backend_service['image'] = f"{new_image_name}:{new_tag}"

    # Update the ports exposed by the backend
    if 'ports' in backend_service:
        backend_service['ports'] = [f"{new_port}:8000"]

    # Save the modified docker-compose.yml
    with open(compose_file, 'w') as f:
        yaml.dump(compose_data, f, default_flow_style=False)

    print(f"Updated {compose_file} with image name: {new_image_name}, tag: {new_tag}, and port: {new_port}")

# ───────────────── main ──────────────────────────────────────────────────────
def main():
    # Search for docker-compose files in the current directory and subdirectories
    compose_dir = Path(__file__).resolve().parent.parent / "Code" / "Project"
    compose_files = find_compose_files(compose_dir)
    chosen = choose_from_list(compose_files, "Select a compose file to modify:")

    # Get user input for new image name, tag, and port
    new_image_name = input("Enter the new Docker image name (e.g., amscope-camera-backend): ")
    new_tag = input("Enter the new tag (camera-1): ")
    new_port = input("Enter the new exposed port (e.g., 8000): ")

    # Validate input
    if not new_image_name or not new_tag or not new_port:
        print("Invalid input, all fields are required.")
        sys.exit(1)

    # Edit the docker-compose.yml file
    edit_docker_compose(chosen, new_image_name, new_port, new_tag)

    # Optionally, rebuild the image if needed
    rebuild = input("Do you want to rebuild the Docker image? [y/N] ").strip().lower().startswith("y")
    if rebuild:
        print(f"[INFO] Building image for {new_image_name}...")
        cmd = ["docker", "compose", "-f", str(chosen), "build", "--pull", "backend"]
        if run(cmd).returncode != 0:
            die("Build failed.")

if __name__ == "__main__":
    main()
