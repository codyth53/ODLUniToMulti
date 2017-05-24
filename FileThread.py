from threading import Condition
from FlowModifier import FlowModifier, VideoStream
from http.client import HTTPConnection
from time import sleep
from threading import Thread

file_threads = {}


class FileThread(Thread):
    @staticmethod
    def get_thread(address, sender):
        if address in file_threads.keys():
            return file_threads.get(address)
        else:
            thread = FileThread(address, sender)
            file_threads[address] = thread
            return thread

    def __init__(self, address, sender):
        # List of tuples of (host, hostport, destport)
        Thread.__init__(self)
        self.hosts = []
        self.lock = Condition()
        self.sender = sender
        self.address = address
        self.response = None
        self.response_data = None

    def run(self):
        # Get file
        headers = {}
        for header in self.sender.headers.keys():
            # if header == "Host":
            #     headers["Host"] = "www.dadecountyschools.org"
            # elif header == "Referer":
            #     pass
            # else:
            headers[header] = self.sender.headers.get(header)
        # print("Getting ready to request")
        # print(headers)
        # print("Prefetching " + headers["Host"] + "  " + self.sender.path)
        conn = HTTPConnection(headers["Host"], 80)
        conn.request('GET', self.sender.path, None, headers)
        self.response = conn.getresponse()
        self.response_data = self.response.read(self.response.length)
        # print("File " + self.sender.path + " fetched. Sleeping")
        # Set timer here
        sleep(2)
        # print("Preparing to deliver " + self.sender.path)
        self.send_file()
        print("Finished delivering " + self.sender.path)
        del file_threads[self.address]
        return

    def add_host(self, host, sender):
        self.hosts.append(host)
        # print("Host " + host[0] + " wants file " + sender.path)
        if self.sender is sender:
            # print("Host " + host[0] + " is the main sender for " + self.sender.path)
            self.start()
            return True
        else:
            return False

    def send_file(self):
        while self.sender is None:
            print("No sender yet")
            sleep(0.1)
        fl = FlowModifier.get_flow_modifier()
        vs = VideoStream(fake_src_ip=self.sender.client_address[0], fake_src_port=self.sender.client_address[1],
                         fake_dst_ip="10.0.0.10", fake_dst_port=80)
        print(self.sender.path + " has " + str(len(self.hosts)) + " viewers")
        for host in self.hosts:
            vs.add_ip(host[0], host[1], host[2])
        fl.upsert_stream(vs)
        fl.update_flows()
        #send file
        self.sender.send_response(self.response.status)
        for header in self.response.headers.keys():
            # if header == "Host":
            #     self.send_header("Host", "www.dadecountyschools.org")
            # else:
            self.sender.send_header(header, self.response.headers.get(header))
        self.sender.end_headers()
        self.sender.wfile.write(self.response_data)
        # notifyall
        self.lock.acquire()
        try:
            self.lock.notify_all()
        except:
            print("No one was waiting for the lock?")
        self.lock.release()

        vs.remove_stream()
        fl.remove_stream(vs.stream_id)
