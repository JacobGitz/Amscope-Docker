"""this is a script for the youtube tutorial series "PyQt5 Python 3 Tutorial" by Tech With Tim"""
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QApplication, QMainWindow 
import sys

def window():
    #important for something, idk what argv does?
    app = QApplication(sys.argv)
    #this obviously creates the main window here
    win = QMainWindow()
    #takes xpos,ypos,width,height
    win.setGeometry(0,0,900,900)
    #sets the little window title at the top left or dead center or something
    win.setWindowTitle("Thorlabs TDC001 Interface by Jacob Lazarchik")
    #putting a text box on the screen
    label = QtWidgets.QLabel(win)
    label.setText("Here is a label!")
    #necessary to make the window appear
    win.show()
    #clean exit command
    sys.exit(app.exec())

window()
