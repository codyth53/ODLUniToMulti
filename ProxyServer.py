import socket
import ConnThread
from http.server import HTTPServer
from socketserver import ThreadingMixIn
from ConnThread import RequestHandler


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass


class ProxyServer:
    def __init__(self):
        # server = HTTPServer(('', 80), RequestHandler)
        server = ThreadedHTTPServer(('', 80), RequestHandler)
        server.serve_forever()

    # def __init__(self, port=8080):
    #     self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     self.sock.bin((socket.gethostname(), port))
    #     self.sock.listen(5)
    #
    #     while True:
    #         (clientsocket, address) = self.sock.accept()
    #         ct = ConnThread(clientsocket)
    #         ct.run()
