######################### Intro ###################################################################

These scripts automatically boot, build, save, load, and shutdown the 2 docker containers for this whole project easily on Linux.

(For Windows, refer to the Windows directory in this repo.  For macOS, see the MacOS directory.)

For these shell scripts, just open a terminal in this directory and type
    bash a-file.sh
(replace with the name of the file you want to run) and it will do its thing.

You can also make them executable with
    chmod +x file-name.sh
They may already be, so right-click and see if it says “Run as Program”.

######################### What Each Script Does ###################################################

  backend-launch.sh      → build / (re)start FastAPI backend   → opens http://localhost:8000/docs
  frontend-launch.sh     → build / (re)start PyQt GUI frontend → opens http://localhost:6080
  backend-shutdown.sh    → stop backend container, optional remove
  frontend-shutdown.sh   → stop frontend container, optional remove
  save-image.sh          → export ANY Docker image → ../Docker-images/<your-file>.tar
  load-image.sh          → import a .tar from ../Docker-images/ → optional re-tag

*Launch order:* backend first, frontend second.  
If the GUI whines that it can’t see the backend, kill the GUI container and run
`frontend-launch.sh` again once the backend’s “/ping” endpoint replies.

######################### Bugs you may encounter ##################################################

You may note on Linux and Windows these two containers do not work entirely out of the box (USB devices are not showing up)....

Docker Desktop runs in a hypervisor for compatibility, and USB devices must be passed through to the virtual machine for docker containers to use them.

There is something called usbipd or something in the Docker documentation, and several softwares that allow you to provide USB devices to containers.

I supplied notes for this on Windows in my original stable release (main-branch readme.md), but not for Linux. It was *partially incorrectly* discussed in the presentation as well.

(On a side note, I highly suggest you read the How-to-Docker presentation in the Documentation directory in this repo.)

But, if you run the frontend on a Linux machine, and then the backend on a separate Windows machine (with usbipd-win or whatever I discussed in readme.md) then it will work successfully.

(backend first, then frontend, otherwise frontend won't see backend, restart frontend container if you cannot find the proper backend)

Another common issue is that stuff isn't working anymore if you unplug a USB device while these containers are running. Reboot them.

######################### Saving & Loading Images #################################################

*Need to move this setup to an offline PC?*  

1.  Run **save-image.sh** on a box that already has the image.  
    Pick the image, accept the suggested filename (or type your own), and a
    `.tar` lands in `../Docker-images/`.

2.  Copy that `.tar` to the new machine (USB stick, network share, whatever).

3.  On the new box run **load-image.sh**.  
    Pick the tar, optionally give it a new tag, and you’re ready to `backend-launch.sh`.

Images are big – stick them on the lab NAS if you can.

############## Notes for a Future Person ##########################################################

For a future person in 2035 or something, this building process *may* fail if you try to do it from scratch in this script. Hopefully, pre-built images from this time (2025) will be stored somewhere and just run those instead. You can build on top of those and edit those internally to get what you like and make revised images from them.

However, in the case you do not like my code or existing images, you can rebuild from scratch using these scripts. If it nukes itself during this process, chances are it is pulling the base "python 3.13 slim" images in the Dockerfiles from Docker Hub, as well as a bunch of other online dependencies for Ubuntu, and this causes the problem.

I will try my best to store everything that is an online dependency for the build process in this git repo, but not all of it can be submitted to Github. So, hopefully we have network storage in the lab or a drive which stores this git repo and stores of all the original Ubuntu dependencies and the base python image as well.

If everything goes wrong, contact a guy named Jacob Lazarchik (me) at lazarchik.jacob@gmail.com, maybe spam me a bit or submit a git issue to my repo on github.

(I don't check my email often lol)

