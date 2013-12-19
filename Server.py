import socket
import select
from collections import defaultdict, deque

# SERVER

SERVER_PORT = 8765
SERVER_ADDR = 'localhost'
MAX_BUFFER_SIZE = 1024
BACKLOG = 5
DELIMITER = "\0"

def listening_socket(addr, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow reuse of local addresses (why is this not the default?)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((addr, port))
    return sock

def client():
    return {'msgs': deque(),
            'buffer': '',
            'msgslen': None,
            'msgsrecv': 0}

class Server:
    """
    A server that uses select to handle multiple clients at a time.
    """

    def __init__(self, addr, port):
        self.sock = listening_socket(addr, port)
        self.sock.listen(BACKLOG)

        # dict of socket.fileno() to client dictionaries
        self.clients = defaultdict(client)

        # self.msgs = defaultdict(deque)         # complete messages per client
        # self.buffers = defaultdict(lambda: "") # partial messages per client
        # self.msgslen = defaultdict(lambda: -1) # message lengths per client [len, sent, recvd]
        # self.msgsrecv = defaultdict(lambda: 0) # messages received from each client

    def serv(self, inputs=None, msgs=None):
        if inputs is None:
            inputs = [self.sock]
        else:
            inputs.append(self.sock)

        outputs = []
        while True:
            readready, writeready, _ = select.select(inputs, outputs, [])
            for s in readready:
                if s == self.sock:
                    # handle the server socket
                    try:
                        print "Waiting for client to connect"
                        client, addr = self.sock.accept()
                        print "Server accepted {}".format(client.getsockname())
                        client.setblocking(False)
                        inputs.append(client)
                    except socket.error as e:
                        if e.errno == 10054:
                            print e
                        continue
                else:
                    # read from an already established client socket
                    isDone = self.read(s)
                    if isDone is None: # disconnected
                        print "{} disconnected.".format(s.getsockname())
                        inputs.remove(s)
                        # remove its resources
                        del self.clients[s.fileno()]
                        if s in outputs:
                            outputs.remove(s)
                        s.close()
                    elif isDone:
                        print "Server is done reading from client {}".format(s.fileno())
                        inputs.remove(s)
                        if s not in outputs:
                            outputs.append(s)
                    else:
                        # add s to outputs so server can send a response
                        if s not in outputs:
                            outputs.append(s)
            for s in writeready:
                    # write to client socket
                    # print "writing to {}".format(s.getsockname()[1])
                    isDone = self.write(s)
                    if isDone:
                        print "Server is done writing to client {}".format(s.fileno())
                        if s in outputs:
                            outputs.remove(s)
                        #print "closed {}".format(client.getsockname())
                        s.close()

    def write(self, client_sock):
        """write characters"""
        #fileno = client_sock.fileno()
        client = self.clients[client_sock.fileno()]
        dq = client['msgs']
        if dq:
            nextMSG = dq.popleft()
            if nextMSG != '':
                sent = client_sock.send(nextMSG)        # nextMSG is top element of dq (chars up to and including DELIMITER)
                print "Server sent {} bytes to {}".format(sent, client_sock.fileno())
                if sent == 0:
                    raise RuntimeError("socket connection broken")
                if sent < len(nextMSG):
                    client['msgs'].appendleft(nextMSG[sent:]) # add part of msg not sent to front of deque
                # check if done writing
                # done reading and len(msgs deque) == 0
                if client['msgsrecv'] == client['msgslen'] + 1:
                    return len(client['msgs']) == 0
                else:
                    # server has not finished receiving all messages
                    return False
        if client['msgsrecv'] == client['msgslen'] + 1:
            return len(client['msgs']) == 0
        else:
            return False

    def readBufferMsg(self, client_sock):
        """"read characters from buffer"""
        client = self.clients[client_sock.fileno()]

        next_msg, sep, msgs_rest = client['buffer'].partition(DELIMITER)
        client['msgs'].append(next_msg + DELIMITER)
        client['msgsrecv'] += 1
        client['buffer'] = msgs_rest

    def read(self, client_sock):
        """
        Read from client_sock, parsing and storing messages in related client.

        Returns:
          True  -> all messages received from client
          False -> more messages to come
          None  -> client disconnected
        """
        client = self.clients[client_sock.fileno()]
        chunk = client_sock.recv(MAX_BUFFER_SIZE)
        # check that client_sock is still connected
        if chunk:
            next_msg, sep, msgs_rest = chunk.partition(DELIMITER)
            if sep == DELIMITER:
                # store number of messages from this client, if not yet stored
                if client['msgslen'] is None:
                    client['msgslen'] = int(client['buffer'] + next_msg)
                client['msgs'].append(client['buffer'] + next_msg + DELIMITER)
                client['buffer'] = msgs_rest
                client['msgsrecv'] += 1
                while DELIMITER in client['buffer']:
                    self.readBufferMsg(client_sock)
            else:
                # delimiter not found
                # concatenate partial messages
                client['buffer'] += next_msg

            return client['msgsrecv'] == client['msgslen'] + 1

##################################################################################

if __name__ == "__main__":
    print 'Echo Server starting'
    s = Server(SERVER_ADDR, SERVER_PORT)
    s.serv()
