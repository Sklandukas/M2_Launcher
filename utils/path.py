import os

def json_path():
    path = os.getcwd()
    path = path + "\\config\\setting.json"  
    path = path.replace("\\", "/") 
    return path

def txt_path():
    path = os.getcwd()
    path = path + "\\config\\steps.txt"  
    path = path.replace("\\", "/")  
    return path
