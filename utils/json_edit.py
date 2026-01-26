import json
from utils.path import json_path

def change_val(parameter ,val):
    path = json_path()
    with open(path, 'r') as file:
        data = json.load(file)
    
    data['CameraDefaultSettings'][parameter] = val
    with open(path, 'w') as file:
        json.dump(data, file, indent = 4)