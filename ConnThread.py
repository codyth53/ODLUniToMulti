from http.server import BaseHTTPRequestHandler
from http.client import HTTPConnection
from FileThread import FileThread

class ConnThread:
    def __init__(self, socket):
        self.sock = socket

    def run(self):
        pass


class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args):
        BaseHTTPRequestHandler.__init__(self, *args)

    def do_GET(self):
        if len(self.path) < 3 or ".ts" not in self.path[-3:]:
            # Would really want to use header info
            headers = {}
            for header in self.headers.keys():
                # if header == "Host":
                #     headers["Host"] = "www.dadecountyschools.org"
                # elif header == "Referer":
                #     pass
                # else:
                headers[header] = self.headers.get(header)
            # print("Reqesting " + headers["Host"] + "  " + self.path)
            conn = HTTPConnection(headers["Host"], 80)
            conn.request('GET', self.path, None, headers)
            response = conn.getresponse()
            # print("*** " + self.path + " acquired")

            self.send_response(response.status)
            for header in response.headers.keys():
                # if header == "Host":
                #     self.send_header("Host", "www.dadecountyschools.org")
                # else:
                self.send_header(header, response.headers.get(header))
            self.end_headers()
            self.wfile.write(response.read())
            # print("*** " + self.path + " forwarded")
            return
        else:
            # print("Preparing " + self.client_address[0] + " for video file " + self.path)
            print("-----Received request for " + self.path + " from " + self.client_address[0])
            address_path = self.headers["Host"] + self.path
            file_thread = FileThread.get_thread(address_path, self)
            file_thread.lock.acquire()
            should_send = file_thread.add_host((self.client_address[0], self.client_address[1], 80), self)
            file_thread.lock.wait()
            file_thread.lock.release()
            return