import json
import urllib.request
from http.client import HTTPConnection
from base64 import b64encode


class ODLConnector:
    ip_address = ""
    base_address = ""

    def __init__(self, ip, base_address = "/restconf/operational/", config_address="/restconf/config/"):
        self.ip_address = ip
        self.base_address = base_address
        self.config_address = config_address

        username = "admin"
        password = "admin"
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, self.ip_address+self.base_address, username, password)

        handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(handler)
        urllib.request.install_opener(opener)

    def get_request(self, address):
        response = urllib.request.urlopen(self.ip_address + self.base_address + address)

        data = response.read().decode('utf-8')

        return json.loads(data)

    def post_request(self, address, data):
        print("Sending this data:")
        print(self.ip_address + self.config_address + address)
        req = urllib.request.Request(self.ip_address + self.config_address + address, data=data,
                                     headers={'content-type': 'application/json'}, method='PUT')
        userAndPass = b64encode(b"admin:admin").decode("ascii")
        req.add_header('Authorization', 'Basic %s' % userAndPass)
        try:
            response = urllib.request.urlopen(req)
        except Exception as e:
            print(e.reason)
        resp = response.read().decode('utf-8')
        print(resp)

        try:
            return json.loads(resp)
        except:
            return True

        # conn = HTTPConnection(self.ip_address)
        # userAndPass = b64encode(b"admin:admin").decode("ascii")
        # headers = {'Authorization': 'Basic %s' % userAndPass}
        # print("Sending request to " + self.config_address + address)
        # conn.request('POST', self.config_address + address, body=data, headers=headers)
        # response = conn.getresponse()
        # return response.read()

    def delete_request(self, address):
        print("Sending delete to " + address)
        req = urllib.request.Request(self.ip_address + self.config_address + address,
                                     headers={'content-type': 'application/json'}, method='DELETE')
        userAndPass = b64encode(b"admin:admin").decode("ascii")
        req.add_header('Authorization', 'Basic %s' % userAndPass)
        try:
            response = urllib.request.urlopen(req)
        except Exception as e:
            print(e.reason)
