Last updated: August 13th, 2025
Written by: Jacob Lazarchik
Submit issues: @JacobGitz on GitHub

GOAL
----
Provide simple scripts to launch, build, save, load, and configure Docker images
for lab devices (starting with an AmScope camera). You can bind a camera by its
serial number to a specific Docker image and assign it a fixed network port.
Images are portable and shareable across the lab.

QUICK START (MOST PEOPLE)
-------------------------
1) Install Python 3.13 (or create a venv with Python 3.13).
   - Windows installer is in: Prereqs/Windows

2) Install required Python packages:
   - Open a command prompt in this directory, then run (If using Linux or WSL!):
     "pip install --no-index --find-links=wheelhouse -r requirements.txt"
   -For standard Windows, open a command prompt in this directory and run:
      "pip install -r requirements.txt" (requires internet)

3) Get the Docker images (too large for GitHub):
   - Ask me for the .tar files, or use the lab NAS when available.
   - Place all image .tar files in: /Docker-images

4) Start a device:
   - Run: python launch.py
   - Pick the service to launch.
   - Your browser will open to the FastAPI docs at:
     http://your-ip:assigned-port/docs

5) Windows USB note:
   - If the camera shows as “not connected,” install and use the WSL USBIP-WIN
     GUI provided in Prereqs/Windows to bind the USB device to Docker.

WHAT THESE SCRIPTS ENABLE
-------------------------
- Assign a specific camera (by serial number) to a unique Docker image and port.
- Keep a “one device ↔ one image ↔ one port” structure for sanity in the lab.
- Save and share built images as .tar files in /Docker-images.
- Reuse and repurpose the same pattern for future devices.

REPOSITORY COMPOSE DEFAULTS
---------------------------
- The repo’s docker-compose includes two example services: camera-1 and camera-2.
- Ask me for the corresponding images; they will also live on the lab NAS.
- If someone gives you a new image, COPY THEIR docker-compose service block into
  /Code/Project/docker-compose-backend.yml before launching.

REQUIREMENTS
------------
- Python 3.13 (system install or venv). Windows installer in Prereqs/Windows.
- Python dependencies: PyYAML,PYUSB, etc. (included offline in wheelhouse for linux/WSL users).
- Cloned repo does NOT include Docker images (too large); obtain from me/NAS and
  place into /Docker-images before running launch.py.

OFFLINE DOCS & SLIDES
---------------------
- “How to Docker” presentation in /Documentation explains:
  - Building wheelhouse directories
  - Using pip freeze to lock requirements
  - General workflow for this project

LAUNCHING & SHARING IMAGES
--------------------------
- New images you build are written to /Docker-images as .tar archives.
- These can be distributed to others; they just drop them into /Docker-images.
- If you’re using someone else’s image:
  1) Paste their service block into /Code/Project/docker-compose-backend.yml
  2) Ensure the image .tar filename in /Docker-images matches the compose entry

================================================================================
FILE / DIRECTORY REFERENCE
================================================================================

amcam.py
--------
- Current helper that detects connected AmScope cameras and returns serial IDs.
- Used by setup.py to pair a specific camera serial with an image and port.
- Only supports AmScope; long-term plan is to remove this dependency and move to
  a universal approach.
- NOTE: This is for configuration time; launch.py itself does not depend on it.

launch.py
---------
- Looks in /Code/Project for a docker-compose YAML file.
- Lists defined services and asks which you want to start.
- Verifies the required .tar image exists in /Docker-images; if not, it exits.
  Example: service “camera-1” expects an image file like:
           amscope-camera-backend_camera-1.tar
- If you don’t have a matching .tar, either obtain it from NAS/me, or run
  setup.py to build a new one.
- After starting the container with the compose settings, opens:
  http://your-ip:assigned-port/docs
- If you built a custom image or edited the compose, PLEASE commit your updated
  compose and upload the .tar to the NAS so the lab stays consistent.

Legacy/
-------
- Older shell script prototypes. Buggy and superseded, but kept for reference.

libamcam.so
-----------
- Native driver used by amcam.py (Linux/macOS).
- setup.py relies on amcam.py/libamcam.so, but launch.py doesn't
- Long-term plan: remove .so/.dll reliance and use a standard Python USB library.
- For WSL setup details, see the main README in the original TDC001-Docker repo.

readme.txt
----------
- This file.

requirements.txt
----------------
- Pinned Python dependencies for the scripts here. Generated via pip freeze.
- See “How to Docker” slides for instructions on creating/updating this file.

setup.py
--------
- For maintainers/advanced users to create or modify device images.
- Windows + Linux supported; Windows USB detection can be finicky and will be
  patched. Make sure the device is NOT bound to WSL in the USB passthrough GUI
  when you run setup.py from the host Python, or the host won’t see the device.
-Works perfectly on linux

- What it does:
  • ADD — append a fully configured camera service block to docker-compose
  • DELETE — remove a service block from docker-compose
  • Writes device_config.json into Code/Project/Controller+fastapi/ before builds
    (stores device info inside the image)
  • Optionally builds the new image and always exports it as:
    Docker-images/<image>_<tag>.tar
  • Prevents duplicate service names and host-side ports

- Future improvements:
  • Remove dependence on amcam.py and native drivers
  • Use a standard Python USB library to grab serial numbers and write
    device_config.json

wheelhouse/
-----------
- Contains .whl files for offline/long-term installs (e.g., PyYAML).
- Lets you install requirements to run these scripts without internet. Keep this up-to-date.
- See “How to Docker” slides for how to create and maintain this directory.

================================================================================
TROUBLESHOOTING & NOTES
================================================================================

USB / Docker Desktop
--------------------
- On Windows and some Linux setups, containers won’t see USB devices “out of the
  box” because Docker Desktop runs in a hypervisor.
- You must pass USB devices into the VM. On Windows, use usbipd / WSL USBIP-WIN GUI (in prereqs).
- I provided notes for Windows in the TDC001-Docker repo (main branch README).
- On Linux, Docker *native* (not Desktop) avoids the VM and USB passthrough,
  so USB generally works without extra steps.

Runtime disconnects
-------------------
- If you unplug a USB device while a container is running, things may break and you may have to restart the container and check binding. 

General reading
---------------
- Strongly recommend reviewing the “How to Docker” presentation in /Documentation.

================================================================================
FUTURE-PROOFING (HELLO, 2035)
================================================================================
- If building from scratch fails in the future, prefer using the pre-built 2025
  images from the NAS, then modify them.
- Failures usually come from pulling base images (e.g., “python:3.13-slim”) and
  various Ubuntu dependencies from the internet, which may have changed.
- I’m trying to store as many build-time dependencies as possible in this repo,
  but not everything fits on GitHub. Keep a lab NAS or external drive that holds:
  • This git repo
  • The pre-built images (.tar)
  • Mirrors/archives of base images and OS package deps (when feasible)

================================================================================
RUNNING THE CAMERA (DETAIL)
================================================================================
- Use command line:  python launch.py
  (Double-clicking scripts also works, but the window may close on errors.)

- Windows: If the camera shows “not connected,” install and use the WSL USBIP-WIN
  GUI (installer in Prereqs/Windows) to bind the USB device for Docker.

================================================================================
CONTACT
================================================================================
If everything goes wrong, contact:
- Jacob Lazarchik — lazarchik.jacob@gmail.com
- Or open an issue on GitHub: @JacobGitz

(I don’t check email often lol)

