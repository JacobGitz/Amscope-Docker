#!/usr/bin/env python3
"""
load_image.py – load a tarred Docker image from ../Docker-images, optional retag
"""
import subprocess, sys, re
from pathlib import Path
from launch import die, run

def list_tars(img_dir: Path):
    return sorted(img_dir.glob("*.tar"))

def choose(items, prompt):
    if not items:
        die("No .tar files found.")
    print(prompt)
    for i, p in enumerate(items, 1):
        print(f" {i:2d}) {p.name}")
    try:
        idx = int(input("> ")) - 1
    except ValueError:
        die("Invalid selection.")
    if idx not in range(len(items)):
        die("Choice out of range.")
    return items[idx]

def main():
    img_dir = Path(__file__).resolve().parent.parent / "Docker-images"
    tar_path = choose(list_tars(img_dir), "Select an image archive to load:")
    print(f"[INFO] Loading {tar_path} ...")
    cp = run(["docker", "load", "-i", str(tar_path)], capture=True)
    if cp.returncode != 0:
        die("docker load failed.")
    print(cp.stdout.strip())
    m = re.search(r"Loaded image:\s+([^\s]+)", cp.stdout)
    loaded = m.group(1) if m else None
    new_tag = input("Add another tag (repo:tag)? (Enter to skip) ").strip()
    if new_tag:
        if loaded:
            if run(["docker", "tag", loaded, new_tag]).returncode == 0:
                print(f"[OK] Also tagged as {new_tag}")
            else:
                print("[WARN] Tagging failed.")
        else:
            print("[WARN] Could not determine loaded image name; tagging skipped.")
    print("[DONE] Image load complete.")

if __name__ == "__main__":
    main()
