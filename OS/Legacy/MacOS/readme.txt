######################### Intro ###################################################################

These scripts automatically build, boot, save, load, and shutdown the 2 Docker containers for this whole project easily on **macOS**.

(For Linux, hop to the Linux directory.  For Windows, see the Windows directory.)

To run a script you can simply **double-click** any `.command` file in Finder,
or open Terminal in this folder and type
    ./a-file.command
(replace with the file you want). 

If macOS Gatekeeper blocks a double-click the first time, right-click ➜ “Open” ➜ “Open”.

You can also mark scripts executable with
    chmod +x *.command
(which the repo usually preserves).

######################### What Each Script Does ###################################################

  backend-launch.command     → build / (re)start FastAPI backend   → opens http://localhost:8000/docs
  frontend-launch.command    → build / (re)start PyQt GUI frontend → opens http://localhost:6080
  backend-shutdown.command   → stop backend container, optional remove
  frontend-shutdown.command  → stop frontend container, optional remove
  save-image.command         → export ANY Docker image → ../Docker-images/<your-file>.tar
  load-image.command         → import a .tar from ../Docker-images/ → optional re-tag

*Launch order:* backend first, frontend second. 
If the GUI grumbles it can’t talk to the backend, quit it and rerun
`frontend-launch.command` once the backend’s “/ping” replies.

######################### Bugs you may encounter ##################################################

**USB device invisible?** Docker Desktop for Mac runs its engine inside a tiny
VM and does **not** pass USB through by default. 
Work-arounds today:

  • Run the backend on a Windows box (with usbipd-win) or a Linux host that 
    can pass USB, and let this macOS machine run only the frontend GUI. 
  • Try Docker-for-Mac’s *experimental* USB-IP feature (see Docker docs).

Unplug the controller while containers are live?  Stop both containers and restart.

(Also grab the *How-to-Docker* presentation in the Documentation folder for the big picture.)

######################### Saving & Loading Images #################################################

*Need to move this setup to an offline Mac?*

1.  Run **save-image.command** on a Mac that already has the image. 
    Pick the image, keep the suggested filename (or type your own) and a 
    `.tar` lands in `../Docker-images/`.

2.  Copy that `.tar` to the target machine (USB stick, AirDrop, NAS, etc.).

3.  On the target Mac run **load-image.command**. 
    Pick the tar, optionally add a new tag, and you’re ready to `backend-launch.command`.

Images are chunky — park them on the lab NAS if you can.

############## Notes for a Future Person ##########################################################

If you’re in 2035 and the **build** step crashes (probably pulling some long-gone
`python:3.13-slim`), just load a tar from 2025 in `Docker-images/` or on the lab NAS
and work from that.  Retag, tweak, re-save.

############## Contact ###########################################################################

If it all melts down, pester **Jacob Lazarchik** at my email lazarchik.jacob@gmail.com 
(or open a GitHub issue — GitHub pings faster than my inbox)

