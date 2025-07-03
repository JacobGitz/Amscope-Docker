######################### Intro ###################################################################

These scripts automatically boot, build, save, load, and shutdown the 2 docker containers for this whole project easily on **Windows**.

(For Linux, hop over to the Linux directory.  For macOS, see the MacOS directory.)

Just **double-click** any `.cmd` file in Explorer *or* open Windows Terminal / CMD / PowerShell and type
    <script>.cmd
(replace with the file you want to run) and it will do its thing.

The `.cmd` files call their matching `.ps1` scripts with **ExecutionPolicy Bypass**, so you don’t have to mess with PowerShell settings. Advanced folks can run the `.ps1` directly if they like.

Docker Desktop **must** be running (little whale icon in your tray) before you start.

######################### What Each Script Does ###################################################

  backend-launch.cmd       → build / (re)start FastAPI backend   → opens http://localhost:8000/docs
  frontend-launch.cmd      → build / (re)start PyQt GUI frontend → opens http://localhost:6080
  backend-shutdown.cmd     → stop backend container, optional remove
  frontend-shutdown.cmd    → stop frontend container, optional remove
  save-image.cmd           → export ANY Docker image  → ..\Docker-images\<your-file>.tar
  load-image.cmd           → import a .tar from ..\Docker-images\ → optional re-tag

*Launch order:* backend first, frontend second.  
If the GUI whines it can’t see the backend, close its window and rerun
`frontend-launch.cmd` once the backend’s “/ping” endpoint replies.

######################### Bugs you may encounter ##################################################

USB device not showing?  Docker Desktop runs in a WSL2 VM, so you must pass
the USB device into WSL with **usbipd-win** (see the main-branch README).

Steps in a nutshell:
  1.  Plug in the TDC001 cube.
  2.  `usbipd wsl list`   → find the busid.
  3.  `usbipd wsl attach --busid <id>`  (run as admin).
  4.  Now run `backend-launch.cmd`.

Unplugging the cube while containers are live?  Stop both containers with the
shutdown scripts, re-attach USB via usbipd, and relaunch.

######################### Saving & Loading Images #################################################

*Need to move this image to another PC?*

1.  Run **save-image.cmd** on a computer that already has the image.  
    Pick the image, accept the suggested filename (or type your own) and a  
    `.tar` lands in `..\Docker-images\`.

2.  Copy that `.tar` to the target machine (USB stick, NAS, whatever), make sure it is in the Docker-images directory.

3.  On the target PC run **load-image.cmd**.  
    Pick the tar, optionally slap on a new tag, and you’re ready to `backend-launch.cmd`.

Big images = big files — park them on the lab NAS if you can.

############## Notes for a Future Person ##########################################################

If you’re in 2035 and a clean build croaks (likely because Docker Hub nuked
`python:3.13-slim`), just load one of the 2025 tars from `Docker-images\`
(or the lab NAS) and work from that.  Retag, tweak, re-save.

############## Contact ###########################################################################

If everything explodes, annoy **Jacob Lazarchik**  at my email lazarchik.jacob@gmail.com  
(or open a GitHub issue — GitHub pings faster than my inbox).  Good Luck!

