------------------Intro to the "Code" Directory ----------------------------

Welcome to my Code directory! If you are here, chances are you realize there are a bunch of directories; This readme is a description of each of these directories. 

(Written by Jacob Lazarchik, Summer of 2025)

------------------Fastapi-tutorials------------------------------------------
This directory is specifically for introducing you to the basics of FastAPI, a super useful python package for getting two docker containers to communicate using network requests in python - it can also be used to make various websites, user interfaces, etc. Generally, just getting two python scripts to communicate via web requests - exactly how websites work. 

Using FastAPI, you can write your normal python script (for example, functions to control a piece of lab hardware), and then turn it into code that can be requested via internet requests by simply importing the FastAPI package. 

Upon running your python script with FastAPI commands, FastAPI basically turns your script into a local server, where a webpage or python gui can send requests to and receive information; For example, moving a stepper motor, then returning its position. The formal term of what your code turns into is called an "API" - FastAPI makes this process fast. 

Also, Fastapi automatically generates interactive documentation for your code. You can see how to structure http requests, send example requests, and see responses all in an interactive webpage (very useful). 

I suggest reading FastAPI's website, which includes a very useful intro page that was used for the scripts included in this directory. 

-----------------Qt-tutorials------------------------------------------
This directory is for an introduction into pyqt, and how to use qt-designer to quickly build graphical user interfaces (GUIs) for laboratory equipment. 

In short, qt-designer is a drag and drop software to design a UI with buttons, labels, dials, and all other fancy things really quickly. When you are done, qt-designer saves your interface as a .ui file, which can be then turned into a pyqt6 python script. 

I included some examples of what qt6 code looks like from an online youtube tutorial. All things are in that youtube tutorial. I included the name of the video series inside of a comment in one of the python scripts (forget which); You can find it lol. 

Also in this directory is a quickly made (version 1.0) of what will become the TDC001 interface.

-------------requirements.lock (or requirements.txt) ----------------------

ANY TIME YOU DO ANYTHING IN PYTHON, ALWAYS INCLUDE THIS.

I suggest you refer to the top level "Documentation" directory. Inside of there is a presentation called "How To Docker #1". This covers what a requirements.lock (or .txt) file is and how to properly create one. You should read that presentation in entirety before even beginning to read any code in this project, or honestly ever coding. 

It is absolutely necessary you create this file for all your projects, so people know the packages you used in your code, as well as their exact versions. Otherwise, you will damn people in the future who try to build a new docker image from your github project. Any time you do anything in python, ALWAYS INCLUDE THIS. 

I cannot stress this enough, if you do not include this file, you will make code that is buggy and basically useless in the long run. Once the packages are updated to newer versions, much of what you wrote will be left broken in entirety. 

Even with this file, sometimes the old packages are not provided on the internet (or downloadable by pip install); For these reasons, I have included a "wheelhouse" directory, which fixes this problem. 

-------------------TDC001-project------------------------------------------

This directory contains all the scripts that build up the GUI, API, and controller for making this whole project work for the TDC001 thorlabs stepper driver.

In an ideal world, this directory will build 2 docker containers, one for the controller's api, another for the GUI. Hopefully, they network together and work amazing with zero problems.

-------------------wheelhouse-----------------------------------------

ALWAYS INCLUDE THIS IN ANY PYTHON PROJECT YOU DO, just like the requirements.lock (or .txt) - Otherwise, you will make broken/useless code. This is for the case that you have python packages (dependencies) no longer available on the internet in the future. Many of the problems that arose with previous code could've been entirely avoided had this been included.

The wheelhouse directory stores the .whl files normally that you'd install using pip from the internet. You should refer to my "How to Docker #1" presentation on how to create this directory. 

Once this directory is created, your docker images can be built without access to the internet at all, and this saves people from having to rewrite your whole code in a new python version. 

If you don't do this, I will personally rise from hell long after I leave the laboratory to punish you. Same with the requirements file. 

-----------------.venv------------------------------------------

ALSO ALWAYS MAKE THIS FOR ANYTHING IN PYTHON. This directory is known as a python "virtual environment". If you don't know how to create one, go ask ChatGPT or some other AI (idk what they will have in the future).

A virtual environment stores the python version, all dependencies, everything. It is a self contained python install for running your scripts in a project. 

By default, a "gitignore" file is included when you create a virtual environment directory. Delete this. If you delete it, it will commit the venv file to github when you push your project. Therefore, anyone who downloads this project can enter this virtual environment from the command line.

You can use this already existing .venv file by typing ".venv/Scripts/activate" in Windows and "source .venv/bin/activate" in Linux (command line or terminal). 

Once you do this, you can run any script I have made normally. Pretty useful.



