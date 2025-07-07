For anyone who is concerned, the /wheelhouse and requirements.lock should be direct clones of whats in the top "/code" directory. 

The dockerfile only has access to this local directory for building the image, so it has to have these items in the same directory as the dockerfile itself.

When this is run, it should create an API backend docker container that can be accessed by a respective frontend anywhere in the lab.

In this case, the backend docker container stores the code for controlling the stepper motor, as well as the fastapi interface for interacting with it via http requests externally.

The frontend docker container, which isn't built here, is for running the pyqt interface for controlling the stepper motor(s). This can be run separately on any computer in the lab.
