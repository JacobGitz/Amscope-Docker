#!/usr/bin/env python3
"""
save_image.py – interactively save a local Docker image to
../Docker-images/<name>.tar

Features
--------
• Lists every local image as  REPOSITORY:TAG
• Lets you pick one via a numbered menu
• Prompts for the .tar filename (sensible default, mkdir-p)
• Gracefully aborts or overwrites if the file already exists
• No external dependencies beyond Python ≥3.8 and Docker CLI
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path


# ───────────────────────── helper utilities ──────────────────────────

def die(msg: str, code: int = 1) -> None:
    """Print *msg* to stderr and exit."""
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str]) -> str:
    """Run *cmd* and return its stdout (raise on non-zero exit)."""
    cp = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if cp.returncode != 0:
        die(f"{cmd[0]} failed: {cp.stderr.strip()}")
    return cp.stdout


def list_images() -> list[str]:
    """Return ['repo:tag', …] for all local images (skip <none>)."""
    out = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    return sorted(
        l for l in (line.strip() for line in out.splitlines())
        if l and "<none>" not in l
    )


def choose(opts: list[str], prompt: str) -> str:
    """Prompt user to choose an item from *opts* (1-based)."""
    if not opts:
        die("No Docker images found.")
    print(prompt)
    for i, opt in enumerate(opts, 1):
        print(f" {i:2d}) {opt}")
    try:
        idx = int(input("> ")) - 1
    except ValueError:
        die("Invalid selection.")
    if idx not in range(len(opts)):
        die("Choice out of range.")
    return opts[idx]


# ─────────────────────────────── main ────────────────────────────────

def main() -> None:
    images = list_images()
    image  = choose(images, "Select an image to save:")

    default_name = image.replace("/", "_").replace(":", "_") + ".tar"
    dest_dir     = Path(__file__).resolve().parent.parent / "Docker-images"
    dest_dir.mkdir(exist_ok=True)

    user_name = input(f"Output file name [default {default_name}]: ").strip()
    tar_path  = dest_dir / (user_name or default_name)

    if tar_path.exists():
        if input(f"'{tar_path.name}' exists. Overwrite? [y/N] ").lower() != "y":
            die("Aborted by user.")

    print(f"[INFO] Saving {image} → {tar_path} …")
    run(["docker", "save", "-o", str(tar_path), image])
    print("[DONE] Image saved.")


if __name__ == "__main__":
    main()

