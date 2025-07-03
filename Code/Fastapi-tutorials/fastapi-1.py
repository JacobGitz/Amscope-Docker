"""
Tutorial 1 on FastAPI
Written by Jacob Lazarchik + FastAPI documentation
"""

"""
#going off of fastapi's documentation on https://fastapi.tiangolo.com/#installation
#effectively, this script just shows how to navigate to a path in a website using this, as well as query objects 
#to run this script, just type "fastapi dev fastapi-1.py"
#also, you can interact with this script by going to the ip it tells you and go to "/docs" like "http://127.0.0.1:8000/docs"
"""
from typing import Union #this creates a union data type, for more information on what a union actually is, go and check https://www.w3schools.com/c/c_unions.php

from fastapi import FastAPI #obviously just importing fastapi, you have to install this via pip if not included

app = FastAPI() #creates a fast api app

"""if you go to http://127.0.0.1:8000/ (assuming thats your ip+port combo), this will literally return a json file of that""" 
@app.get("/") #this is a decorator, it changes this function into something you can access with an http request, just like you would in normal code 
def read_root():
    return {"Hello": "World"}

"""if you do something like http://127.0.0.1:8000/items/5?q=somequery you get a return of {"item_id": 5, "q": "somequery"}"""
@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}

#effectively, this script just shows how to navigate to a path in a website using this, as well as query objects 
#to run this script, just type "fastapi dev fastapi-1.py"
