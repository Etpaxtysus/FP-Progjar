from socket import *
import socket
import threading
import logging
import select
from http_chess import HttpServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

httpserver = HttpServer()

class ProcessTheClient(threading.Thread):
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        threading.Thread.__init__(self)

    def run(self):
        rcv = ""
        self.connection.settimeout(1)
        while True:
            try:
                data = self.connection.recv(2048)
                if data:
                    d = data.decode('utf-8')
                    rcv = rcv + d
                    if rcv.endswith('\r\n\r\n'):
                        break
                else:
                    break
            except (OSError, socket.timeout):
                break
        
        if rcv:
            hasil = httpserver.proses(rcv)
            self.connection.sendall(hasil)
        
        self.connection.close()


class Server(threading.Thread):
    def __init__(self, port):
        self.the_clients = []
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.port = port
        self.shutdown_flag = threading.Event()
        threading.Thread.__init__(self)

    def run(self):
        self.my_socket.bind(('0.0.0.0', self.port))
        self.my_socket.listen(5)
        logging.info(f"HTTP Chess Server started on port {self.port}...")

        while not self.shutdown_flag.is_set():
            readable, _, _ = select.select([self.my_socket], [], [], 1.0)
            if self.my_socket in readable:
                connection, client_address = self.my_socket.accept()
                logging.info(f"Connection accepted from {client_address}")

                clt = ProcessTheClient(connection, client_address)
                clt.start()
                self.the_clients.append(clt)
        
        logging.info("Shuting down all client threads...")
        for clt in self.the_clients:
            clt.join()
        self.my_socket.close()
        logging.info("Server socket closed.")

def main():
    port = 8889
    svr = Server(port)
    svr.start()

    try:
        while svr.is_alive():
            svr.join(0.5)
    except KeyboardInterrupt:
        logging.info("Shutting down server...")
        svr.shutdown_flag.set()
        svr.join()
    
    logging.info("Server has shut down.")

if __name__ == "__main__":
    main()