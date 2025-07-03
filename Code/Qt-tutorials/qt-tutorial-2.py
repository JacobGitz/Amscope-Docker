"""
A script for the Youtube tutorial series "PyQt5 Python 3 Tutorial" by Tech With Tim
Specifically, an intro to buttons
"""


from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QApplication, QMainWindow 
import sys


"""
script for setting up the entire window
"""

#construct a QMainWindow object 
class MyWindow(QMainWindow):

    #initializes itself as a QMainWindow object, calls the initUI function on itself
    def __init__(self):
        super(MyWindow, self).__init__()
        #takes xpos,ypos,width,height
        self.setGeometry(0,0,900,900)
        #sets the little window title at the top left or dead center or something
        self.setWindowTitle("Thorlabs TDC001 Interface by Jacob Lazarchik")
        self.initUI()

    def initUI(self):
        #----------------------------------Qt Labels--------------------------------------------
        #putting a text box on the screen
        self.label = QtWidgets.QLabel(self)
        self.label.setText("Here is a 'label'")
        #move this label a bit
        self.label.move(50,50)

        #-----------------------------------Qt Buttons--------------------------------------------
        #button time
        self.home_button = QtWidgets.QPushButton(self)
        #set the text inside the button
        self.home_button.setText("home")
        #adding button click events, when button is clicked, it calls the function below "home_button_clicked()"
        self.home_button.clicked.connect(self.home_button_clicked) 
    
    #this activates anytime the window changes
    def update(self):
        #adjusts size of label, useful because if text bigger than label, it will cut off
        self.label.adjustSize()
    
    def home_button_clicked(self):
        #prints to the terminal
        print("homing stepper")
        self.label.setText("You are homing the stepper")
        self.update()
        #do something here to call to the stepper motor docker file....

    
def window():
    #--------------------------------------Setup-----------------------------------------------
    #important for something, idk what argv does?
    app = QApplication(sys.argv)
    #this obviously creates the main window here
    win = MyWindow()
 
    #----------------------------------------------------------------------------------------
    #necessary to make the window appear
    win.show()
    #clean exit command
    sys.exit(app.exec())


window()
