Written by Jacob Lazarchik, July 7th 2025


For all who are concerned with what this directory is for, I simply got rid of what I deemed to be not immediately useful code from kai's original repository 

It seems as though app.py (the first one you run), qt.py (which app.py controls), and amcam.py (the python api for the whole camera) are the most useful. 

I made a few tweaks to get this running in fedora linux, so I can begin to put this into a docker container. It seems like this pyqt UI is okay

The only thing I dislike is the like 1 frame per second, I don't know why it is doing that.
