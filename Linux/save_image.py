#!/usr/bin/env python3
"""
save_image.py – save any local Docker image to ../Docker-images/<file>.tar
"""
import subprocess, sys
from pathlib import Path
from launch import die, run

def list_images() -> list[str]:
    out = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]).stdout
    return [l.strip() for l in out.splitlines() if l.strip() and "<none>" not in l]

def choose(items: list[str], prompt: str) -> str:
    if not items:
        die("No Docker images found.")
    print(prompt)
    for i, it in enumerate(items, 1):
        print(f" {i:2d}) {it}")
    try:
        idx = int(input("> ")) - 1
    except ValueError:
        die("Invalid selection.")
    if idx not in range(len(items)):
        die("Choice out of range.")
    return items[idx]

def main():
    images = list_images()
    image = choose(images, "Select an image to save:")
    safe = image.replace("/", "_").replace(":", "_") + ".tar"
    dest_dir = Path(__file__).resolve().parent.parent / "Docker-images"
    dest_dir.mkdir(exist_ok=True)
    fname = input(f"Output file name [default {safe}]: ").strip() or safe
    out_path = dest_dir / fname
    if out_path.exists() and input("Overwrite existing file? (y/N) ").lower() != "y":
        die("Aborted.")
    print(f"[INFO] Saving {image} → {out_path} ...")
    if run(["docker", "save", "-o", str(out_path), image]).returncode != 0:
        die("docker save failed.")
    print("[OK] Image saved.")

if __name__ == "__main__":
    main()
