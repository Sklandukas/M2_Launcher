import requests 
from config.environment_config import EnvironmentConfig
from config.logging_config import logger

class ErpNextApi:
    def __init__(self, username, password, serial_no):
        self.session = requests.Session()
        self.base_url = "https://integratedoptics.com"
        # self.env_config = EnvironmentConfig()
        self.custom_username = username
        self.custom_password = password
        self.serial_no = serial_no
        
    def connect(self):
        url = f"{self.base_url}/api/method/login"
        print(f"url: {url}")
        payload = {
            'usr': self.custom_username,
            'pwd': self.custom_password
        }
        headers = {'Accept': 'Application/json'}
        response = self.session.post(url, headers=headers, data=payload)
        if response.status_code == 200:
            logger.info("Login successful!")

            self.get_serial_no_data()
        else:
            logger.error(f"Error during login: {response.status_code}, {response.text}")

    def get_serial_no_data(self):
        url = f"{self.base_url}/api/resource/Serial%20No/{self.serial_no}"
        response = self.session.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error retrieving data: {response.status_code}, {response.text}")
            return None
    
    def get_laser_test_data(self):
        url = f"{self.base_url}/api/resource/CW Laser Test Data/{self.serial_no}"
        response = self.session.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error retrieving data: {response.status_code}, {response.text}")

    def get_combiner_test_data(self):
        url = f"{self.base_url}/api/resource/Serial No Combiners/{self.serial_no}"
        response = self.session.get(url)
        print(f"response: {response}")
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error retrieving data: {response.status_code}, {response.text}")

    def put_serial_no_data(self, json_payload):
        url = f"{self.base_url}/api/resource/Serial%20No/{self.serial_no}"
        response = self.session.put(url, data=json_payload)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error retrieving data: {response.status_code}, {response.text}")

    def put_laser_test_data(self, json_payload):
        url = f"{self.base_url}/api/resource/CW Laser Test Data/{self.serial_no}"
        response = self.session.put(url, data=json_payload)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error retrieving data: {response.status_code}, {response.text}")
    
    def upload_file(self, form_payload):
        url = f"{self.base_url}/api/method/uploadfile"
        self.session.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})
        response = self.session.post(url, data=form_payload)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error uploading file: {response.status_code}, {response.text}")

    def replace_attach_file(self, form_payload):
        url = f"{self.base_url}/api/method/frappe.desk.form.utils.replace_attach"
        self.session.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})
        response = self.session.post(url, data=form_payload)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error uploading file: {response.status_code}, {response.text}")

    def generate_file_upload_form_payload(self,doc_type, doc_name, filename, file_data, is_private = True):
        if is_private:
            is_private = 1
        else:
            is_private = 0
        payload = (
            f"from_form=1&"
            f"doctype={doc_type}&"
            f"docname={doc_name}&"
            f"filedata={file_data}&"
            f"filename={filename}&="
            f"is_private={is_private}&"
        )
        return payload

    def generate_file_replace_attach_form_payload(self,doctype, doc_name, field_name, new_file_url):
        form_payload = (
            f"doctype={doctype}&"
            f"docname={doc_name}&"
            f"fieldname={field_name}&"
            f"new_file_url={new_file_url}&"
        )
        return form_payload
    

