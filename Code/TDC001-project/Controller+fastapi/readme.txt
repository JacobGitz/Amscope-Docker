For anyone who is concerned, the /wheelhouse and requirements.lock should be direct clones of whats in the top "/code" directory. 

The dockerfile only has access to this local directory for building the image, so it has to have these items in the same directory as the dockerfile itself.

When this is run, it should create an API backend docker container that can be accessed by a respective frontend anywhere in the lab.

In this case, the backend docker container stores the code for controlling the stepper motor, as well as the fastapi interface for interacting with it via http requests externally.

The frontend docker container, which isn't built here, is for running the pyqt interface for controlling the stepper motor(s). This can be run separately on any computer in the lab.

# amscope-camera
Python code to control the AmScope camera (model: MU2003-BI - compatible with MU503B).

This is based on the SDK provided by AmScope [(see here)](https://amscope.com/pages/software-downloads) - you will need to search for your camera model and download the appropriate SDK. The Python code was run on an x64 computer for our testing; be sure to use the appropriate .dll file for your computer.

AmScope provides the following files in Python, which are in this repository for reference:
* amcam.py - this file provides an API for the camera. For more information about the API, see [API.pdf](API.pdf).
* simplest.py - this file provides a simple example that opens the camera and grabs frames from the camera, though it does not display these frames.
* qt.py - this file provides an example that grabs frames from the camera and renders them in a GUI.

Update for DuttLab: For now use simple registration.py, the others seem to be broken with the MU503B
