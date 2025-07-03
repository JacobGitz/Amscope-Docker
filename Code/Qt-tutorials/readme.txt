
-----------Intro to This Directory ----------------------------
These scripts are just from the series "PyQT5 Python 3 Tutorial" by Tech With Tim on Youtube.
Each of them is for the individual videos, 1-3 of that series. 
If you want to do this quickly, just look at his third video, which covers QT designer
https://youtu.be/FVpho_UiDAY?si=Tzy-oNgWFcjNwXPt
I just decided to leave these here for future reference, and anyone who isn't familiar with Qt to get some practice. 

----------------Why I Used QT6 ------------------------------------------------------------------------

As of python 3.8, qt6 is supported. 
Most of QT5 isn't supported by newer versions of python (3.13), so yeah. 
Also, while less learning resources exist of QT6 as of 2025, it is the newest and most robust version, so I chose to use it instead. 
There also isn't a significant difference in use or syntax between the two, especially when using QT designer. 

----------------Running Instructions ----------------------------------------
To run, make sure to run the .venv file in the "code" directory above this one to be able to run these python scripts. 

.ui files are made in qt6-designer, you will have to install this for your desktop, it doesn't need to be in the .venv

a .ui file can be opened by qt-designer, edited, and then by using "pyuic6 -x file-name.ui" (in the venv) it will turn that .ui file into a full python script.

the version 1.0.0 thorlabs frontend was made with very little instruction and is very crude. 

