from ExternalFileServer.smb.smb_client import ExternalFileClient
_smb_client = None

def check_server_connection(username, password, serial_no):
    global _smb_client
    
    try:
        _smb_client = ExternalFileClient(username, password, "MatchBox Produced Units", serial_no=serial_no)
        
        if _smb_client.connect("ioproduction"):
            return _smb_client
        else:
            _smb_client = None
            return None
    except Exception as e:
        _smb_client = None
        return None

def get_smb_client():
    global _smb_client
    return _smb_client