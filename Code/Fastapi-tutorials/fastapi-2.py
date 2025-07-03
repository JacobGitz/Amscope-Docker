"""
Tutorial Part 2, FastAPI Documentation
"""

from typing import Union #imports union datatype just like the first file I included

from fastapi import FastAPI 
from pydantic import BaseModel #this is pretty special, I suggest learning a bit of pydantic, but it is basically to create an object that stores data of the type you specify to ensure no type errors 
# for more info on pydantic, I suggest the article from the medium "a practical guide to pydantic", I included the pdf in this directory
app = FastAPI()

"""this is a great example of how to create something with pydantic as a pydantic child object"""
class Item(BaseModel):
    name: str
    price: float
    is_offer: Union[bool, None] = None #the equal sets a default value of none if nothing is given 
    #first_name: str
    #middle_name: Union[str, None] # This means the parameter doesn't have to be sent
    #title: Optional[str] # this means the parameter should be sent, but can be None
    #last_name: str
#validating = Item(first_name="marc", last_name="nealer") for example, this will throw an error if you don't set things correctly
    
"""same as last tutorial file"""
@app.get("/")
def read_root():
    #returns a json data type
    return {"Hello": "World"}

"""also basically the same as last time"""
@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q }

"""
This is is where things get weird
As far as I can tell, this creates an Item object + item_id assigned to it
You send an item_id in combination with a proper json file (formatted to what the Item class specifies) and it creates this new object that you can address"""
@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    return {"item_name": item.name, "item_id": item_id}
