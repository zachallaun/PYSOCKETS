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

class Server:
    """
    A server that uses select to handle multiple clients at a time.
    """

    def __init__(self, addr, port):
        self.sock = listening_socket(addr, port)
        self.sock.listen(BACKLOG)

        self.msgs = defaultdict(deque)         # complete messages per client
        self.buffers = defaultdict(lambda: "") # partial messages per client
        self.msgslen = defaultdict(lambda: -1) # message lengths per client [len, sent, recvd]
        self.msgsrecv = defaultdict(lambda: 0) # messages received from each client

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
                    if isDone is None:
                        # s disconnected
                        print "{} disconnected.".format(s.getsockname())
                        inputs.remove(s)
                        # remove its resources
                        del self.msgs[s.fileno()]
                        del self.buffers[s.fileno()]
                        del self.msgslen[s.fileno()]
                        del self.msgsrecv[s.fileno()]
                        if s in outputs:
                            # remove s from outputs (no need to respond to it anymore)
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
        dq = self.msgs[client_sock.fileno()]
        if dq:
            nextMSG = dq.popleft()
            if nextMSG != '':
                sent = client_sock.send(nextMSG)        # nextMSG is top element of dq (chars up to and including DELIMITER)
                print "Server sent {} bytes to {}".format(sent, client_sock.fileno())
                if sent == 0:
                    raise RuntimeError("socket connection broken")
                if sent < len(nextMSG):
                    self.msgs[client_sock.fileno()].appendleft(nextMSG[sent:])           # add part of msg not sent to front of deque
                # check if done writing
                # done reading and len(msgs deque) == 0
                if self.msgsrecv[client_sock.fileno()] == self.msgslen[client_sock.fileno()] + 1:
                    return len(self.msgs[client_sock.fileno()]) == 0
                else:
                    # server has not finished receiving all messages
                    return False
        if self.msgsrecv[client_sock.fileno()] == self.msgslen[client_sock.fileno()] + 1:
            return len(self.msgs[client_sock.fileno()]) == 0
        else:
            return False

    def readBufferMsg(self, client_sock):
        """"read characters from buffer"""
        buff = self.buffers[client_sock.fileno()]
        msgs_recv = self.msgsrecv[client_sock.fileno()]

        next_msg, sep, msgs_rest = buff.partition(DELIMITER)
        self.msgs[client_sock.fileno()].append(next_msg + DELIMITER)        # store complete msg on deque
        self.msgsrecv[client_sock.fileno()] = msgs_recv + 1
        self.buffers[client_sock.fileno()] = msgs_rest                  # store partial msg in buffer

        #return self.msgsrecv[client_sock.fileno()] == self.msgslen[client_sock.fileno()] + 1


    def read(self, client_sock):
        """
        read characters; build messages
        """
        buff = self.buffers[client_sock.fileno()]
        msgs_recv = self.msgsrecv[client_sock.fileno()]
        chunk = client_sock.recv(MAX_BUFFER_SIZE)
        # check that client_sock is still connected
        if chunk:
            next_msg, sep, msgs_rest = chunk.partition(DELIMITER)
            if sep == DELIMITER:
                # store number of messages from this client, if not yet stored
                if self.msgslen[client_sock.fileno()] < 0:
                    self.msgslen[client_sock.fileno()] = int(buff + next_msg)               # set total number of messages to follow
                    self.msgs[client_sock.fileno()].append(buff + next_msg + DELIMITER)     # store complete msg
                    self.buffers[client_sock.fileno()] = msgs_rest
                    self.msgsrecv[client_sock.fileno()] = msgs_recv + 1                     # first message received
                else:
                    self.msgs[client_sock.fileno()].append(buff + next_msg + DELIMITER)     # store complete msg
                    self.buffers[client_sock.fileno()] = msgs_rest                          # store partial msg
                    self.msgsrecv[client_sock.fileno()] = msgs_recv + 1                     # incr messages received
                while DELIMITER in self.buffers[client_sock.fileno()]:
                    self.readBufferMsg(client_sock)
            else:
                # delimiter not found
                # concatenate partial messages
                self.buffers[client_sock.fileno()] = buff + next_msg

            return self.msgsrecv[client_sock.fileno()] == self.msgslen[client_sock.fileno()] + 1

##################################################################################

if __name__ == "__main__":
    print 'Echo Server starting'
    s = Server(SERVER_ADDR, SERVER_PORT)
    s.serv()
