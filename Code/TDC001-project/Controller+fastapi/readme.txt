For anyone who is concerned, the /wheelhouse and requirements.lock should be direct clones of whats in the top "/code" directory. 

The dockerfile only has access to this local directory for building the image, so it has to have these items in the same directory as the dockerfile itself.

When this is run, it should create an API backend docker container that can be accessed by a respective frontend anywhere in the lab.

In this case, the backend docker container stores the code for controlling the camera, as well as the fastapi interface for interacting with it via http requests externally.

The frontend docker container, which isn't built here, is for running the pyqt interface for controlling the stepper motor(s). This can be run separately on any computer in the lab.

You can run the entrypoint.sh if you want to boot the server without running it in a container, and this should open up the fastapi server on 0.0.0.0:8001. You can interact with the api by going to http://localhost:8001/docs#

Make sure you start the virtual environment and have all dependencies installed, and then go and type like "bash entrypoint.sh" in the .venv command enviornment, and it will boot the server. 

You can also just go to the helper scripts (windows/macos/linux) and build the backend docker container and run it if wanted. 
