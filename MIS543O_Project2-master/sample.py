
#server.py

import socket

s = socket.socket()
host = socketi.gethostname()
port = 8080
s.bind((host, port))
s.listen(1)
print(host)
print("Waiting for an incoming connection")
conn, addr = s.accept()
print(addr, "Has connected to the server")

filename = input(str("Please enter the filename of the file: "))
file = open(filename , 'rb')
file_data = file.read(1024)
conn.send(file_data)
print("Data has been transmitted successfully.")

#client.py
import socket

s = socket.socket()
host = input(str("Please enter the host address of the sender: "))
port = 8080
s.connect((host,port))
print("Connected...")

filename = input(str(" Please enter a filename for the incoming file"))
file = open(filename, 'wb')
file_data = s.recv(1024)
file.write(file_data)
file.close
print("File has been received successfully.")


#Basic Sender 
import sys
import socket
import random

import Checksum

'''
This is the basic sender class. Your sender will extend this class and will
implement the start() method.
'''
class BasicSender(object):
    def __init__(self,dest,port,filename,debug=False):
        self.debug = debug
        self.dest = dest
        self.dport = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(None) # blocking
        self.sock.bind(('',random.randint(10000,40000)))
        if filename == None:
            self.infile = sys.stdin
        else:
            self.infile = open(filename,"r")

    # Waits until packet is received to return.
    def receive(self, timeout=None):
        self.sock.settimeout(timeout)
        try:
            return self.sock.recv(4096)
        except (socket.timeout, socket.error):
            return None

    # Sends a packet to the destination address.
    def send(self, message, address=None):
        if address is None:
            address = (self.dest,self.dport)
        self.sock.sendto(message, address)

    # Prepares a packet
    def make_packet(self,msg_type,seqno,msg):
        body = "%s|%d|%s|" % (msg_type,seqno,msg)
        checksum = Checksum.generate_checksum(body)
        packet = "%s%s" % (body,checksum)
        return packet

    def split_packet(self, message):
        pieces = message.split('|')
        msg_type, seqno = pieces[0:2] # first two elements always treated as msg type and seqno
        checksum = pieces[-1] # last is always treated as checksum
        data = '|'.join(pieces[2:-1]) # everything in between is considered data
        return msg_type, seqno, data, checksum

    # Main sending loop.
    def start(self):
        raise NotImplementedError

#Receiver
import socket
import getopt
import sys
import time

import Checksum

class Connection():
    def __init__(self,host,port,start_seq,debug=False):
        self.debug = debug
        self.updated = time.time()
        self.current_seqno = start_seq - 1 # expect to ack from the start_seqno
        self.host = host
        self.port = port
        self.max_buf_size = 5
        self.outfile = open("%s.%d" % (host,port),"w")
        self.seqnums = {} # enforce single instance of each seqno

    def ack(self,seqno, data):
        res_data = []
        self.updated = time.time()
        if seqno > self.current_seqno and seqno <= self.current_seqno + self.max_buf_size:
            self.seqnums[seqno] = data
            for n in sorted(self.seqnums.keys()):
                if n == self.current_seqno + 1:
                    self.current_seqno += 1
                    res_data.append(self.seqnums[n])
                    del self.seqnums[n]
                else:
                    break # when we find out of order seqno, quit and move on

        if self.debug:
            print "next seqno should be %d" % (self.current_seqno+1)

        # note: we return the /next/ sequence number we're expecting
        return self.current_seqno+1, res_data

    def record(self,data):
        self.outfile.write(data)
        self.outfile.flush()

    def end(self):
        self.outfile.close()

class Receiver():
    def __init__(self,listenport=33122,debug=False,timeout=10):
        self.debug = debug
        self.timeout = timeout
        self.last_cleanup = time.time()
        self.port = listenport
        self.host = ''
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.settimeout(timeout)
        self.s.bind((self.host,self.port))
        self.connections = {} # schema is {(address, port) : Connection}
        self.MESSAGE_HANDLER = {
            'start' : self._handle_start,
            'data' : self._handle_data,
            'end' : self._handle_end,
            'ack' : self._handle_ack
        }

    def start(self):
        print "===== Welcome to AUTP Receiver v1.3! ====="
        print "* Listening on port %d..." % self.port
        while True:
            try:
                message, address = self.receive()
                msg_type, seqno, data, checksum = self._split_message(message)
                try:
                    seqno = int(seqno)
                except:
                    raise ValueError
                if debug:
                    print "%s %d %s %s" % (msg_type, seqno, data, checksum)
                if Checksum.validate_checksum(message):
                    print message
                    self.MESSAGE_HANDLER.get(msg_type,self._handle_other)(seqno, data, address)
                elif self.debug:
                    print "checksum failed: %s" % message

                if time.time() - self.last_cleanup > self.timeout:
                    self._cleanup()
            except socket.timeout:
                self._cleanup()
            except (KeyboardInterrupt, SystemExit):
                exit()
            except ValueError, e:
                if self.debug:
                    print e
                pass # ignore

    # waits until packet is received to return
    def receive(self):
        return self.s.recvfrom(4096)

    # sends a message to the specified address. Addresses are in the format:
    #   (IP address, port number)
    def send(self, message, address):
        self.s.sendto(message, address)

    # this sends an ack message to address with specified seqno
    def _send_ack(self, seqno, address):
        m = "ack|%d|" % seqno
        checksum = Checksum.generate_checksum(m)
        message = "%s%s" % (m, checksum)
        self.send(message, address)

    def _handle_start(self, seqno, data, address):
        if not address in self.connections:
            self.connections[address] = Connection(address[0],address[1],seqno,self.debug)
            if self.debug:
                print "Accepted new connection %s" % str(address)
        self._handle_data(seqno, data, address)

    # ignore packets from uninitiated connections
    def _handle_data(self, seqno, data, address):
        if address in self.connections:
            conn = self.connections[address]
            ackno,res_data = conn.ack(seqno,data)
            for l in res_data:
                if self.debug:
                    print l
                conn.record(l)
            self._send_ack(ackno, address)

    # handle end packets
    def _handle_end(self, seqno, data, address):
        self._handle_data(seqno, data, address)
        # Do not actually terminate connection, since Sender does not send ACKs to FINACKs

    # I'll do the ack-ing here, buddy
    def _handle_ack(self, seqno, data, address):
        pass

    # handler for packets with unrecognized type
    def _handle_other(self, seqno, data, address):
        pass

    def _split_message(self, message):
        pieces = message.split('|')
        msg_type, seqno = pieces[0:2] # first two elements always treated as msg type and seqno
        checksum = pieces[-1] # last is always treated as checksum
        data = '|'.join(pieces[2:-1]) # everything in between is considered data
        return msg_type, seqno, data, checksum

    def _cleanup(self):
        if self.debug:
            print "clean up time"
        now = time.time()
        for address in self.connections.keys():
            conn = self.connections[address]
            if now - conn.updated > self.timeout:
                if self.debug:
                    print "killed connection to %s (%.2f old)" % (address, now - conn.updated)
                conn.end()
                del self.connections[address]
        self.last_cleanup = now

if __name__ == "__main__":
    def usage():
        print "AUTP Receiver"
        print "-p PORT | --port=PORT The listen port, defaults to 33122"
        print "-t TIMEOUT | --timeout=TIMEOUT Receiver timeout in seconds"
        print "-d | --debug Print debug messages"
        print "-h | --help Print this usage message"

    try:
        opts, args = getopt.getopt(sys.argv[1:],
                               "p:dt:", ["port=", "debug=", "timeout="])
    except:
        usage()
        exit()

    port = 33122
    debug = False
    timeout = 10

    for o,a in opts:
        if o in ("-p", "--port="):
            port = int(a)
        elif o in ("-t", "--timeout="):
            timeout = int(a)
        elif o in ("-d", "--debug="):
            debug = True
        else:
            print usage()
            exit()
    r = Receiver(port, debug, timeout)
    r.start()

    #Test HArness
    #!/usr/bin/python
import os
import socket
import subprocess
import time

import Checksum
from tests import BasicTest

"""
Add the tests you want to run here. Don't modify anything outside this function!
You'll need to import the tests here and then create an instance of each one
you want to run. The tests automatically register themselves with the
forwarder, so they will magically be run.
"""
def tests_to_run(forwarder):
    from tests import BasicTest, RandomDropTest
    BasicTest.BasicTest(forwarder, "README")
    RandomDropTest.RandomDropTest(forwarder, "README")

"""
Testing is divided into two pieces: this forwarder and a set of test cases in
the tests directory.
This forwarder literally forwards packets between a sender and a receiver. The
forwarder accepts two files -- a sender and a receiver implementation and a
port to use. Test cases must then be registered with the forwarder. Once test
cases are registered, the forwarder executes each one. Execution involves
starting the specified sender and receiver implementation, and then sending
whatever file the test case specifies, and then calling the test case's
result() method to get a test result back.
The forwarder maintains two queues of packets, the in_queue and the out_queue.
Every packet that arrives is added to the in_queue (after having its
destination re-written appropriately), and every packet that is meant to be
sent is put into the out_queue. The forwarder never moves packets between these
two queues on its own -- that is the responsibility of the test case. Inside
the forwarder and test cases, it's safe to assume all connections start with
sequence number 0: the forwarder rewrites sequence numbers appropriate before
sending packets onward.
The forwarder's main loop (in start()) first checks for any inbound packets. If
a packet is received, the forwarder adds it to the in_queue, then calls the
current test case's handle_packet() method. If no packet is available it checks
whether or not its "tick" interval has expired.  If the tick interval has
expired, we execute a tick event, which calls the test case's handle_tick()
method and then sends over the wire any packets in the out_queue.
Once the sender has terminated, we kill the receiver and call the test case's
result() method, which should do something sensible to determine whether or not
the test case passed.
"""
class Forwarder(object):
    """
    The packet forwarder for testing
    """
    def __init__(self, sender_path, receiver_path, port):
        if not os.path.exists(sender_path):
            raise ValueError("Could not find sender path: %s" % sender_path)
        self.sender_path = sender_path

        if not os.path.exists(receiver_path):
            raise ValueError("Could not find receiver path: %s" % receiver_path)
        self.receiver_path = receiver_path

        # book keeping for tests
        # [(test object1, input file1), (test object2, input file2), ...]
        self.tests = []
        self.current_test = None
        self.out_queue = []
        self.in_queue = []
        self.test_state = "INIT"
        self.tick_interval = 0.001 # 1ms
        self.last_tick = time.time()
        self.timeout = 600. # seconds

        # network stuff
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.01) # make this a very short timeout, por que no?
        self.sock.bind(('', self.port))

        self.receiver_port = self.port + 1
        self.sender_addr = None
        self.receiver_addr = None

    def _tick(self):
        """
        Every tick, we call the tick handler for the current test, then we
        flush the out_queue.
        """
        self.current_test.handle_tick(self.tick_interval)
        for p in self.out_queue:
            self._send(p)
        self.out_queue = []

    def _send(self, packet):
        """ Send a packet. """
        packet.update_packet(seqno=packet.seqno + self.start_seqno_base, update_checksum=False)
        self.sock.sendto(packet.full_packet, packet.address)

    def register_test(self, testcase, input_file):
        assert isinstance(testcase, BasicTest.BasicTest)
        self.tests.append((testcase, input_file))

    def execute_tests(self):
        for (t, input_file) in self.tests:
            self.current_test = t
            self.start(input_file)

    def handle_receive(self, message, address):
        """
        Every time we receive a new packet, this is called. We first check if
        this is the first packet we've seen -- if so, we need to learn the
        starting sequence number.
        Otherwise, we add every packet we get to the in_queue.
        """

        # Handle new senders.
        # We need to learn the sender and receiver ports, then learn the
        # initial sequence number so we can just assume every sequence number
        # starts from zero in the test.
        if self.test_state == "NEW":
            if not address[1] == self.receiver_port:
                start_packet = Packet(message, (None, None), 0)
                if not start_packet.bogon:
                    self.start_seqno_base = start_packet.seqno
                    self.sender_addr = address
                    self.test_state = "READY"

        if self.test_state == "READY":
            if address == self.receiver_addr:
                p = Packet(message, self.sender_addr, self.start_seqno_base)
            elif address == self.sender_addr:
                p = Packet(message, self.receiver_addr, self.start_seqno_base)
            else:
                # Ignore packets from unknown sources
                return
            self.in_queue.append(p)
            self.current_test.handle_packet()

    def start(self, input_file):
        self.test_state = "NEW"
        self.sender_addr = None
        self.receiver_addr = ('127.0.0.1', self.receiver_port)
        self.recv_outfile = "127.0.0.1.%d" % self.port

        self.in_queue = []
        self.out_queue = []

        receiver = subprocess.Popen(["python", self.receiver_path,
                                     "-p", str(self.receiver_port)])
        time.sleep(0.2) # make sure the receiver is started first
        sender = subprocess.Popen(["python", self.sender_path,
                                   "-f", input_file,
                                   "-p", str(self.port)])
        try:
            start_time = time.time()
            while sender.poll() is None:
                try:
                    message, address = self.sock.recvfrom(4096)
                    self.handle_receive(message, address)
                except socket.timeout:
                    pass
                if time.time() - self.last_tick > self.tick_interval:
                    self.last_tick = time.time()
                    self._tick()
                if time.time() - start_time > self.timeout:
                    raise Exception("Test timed out!")
            self._tick()
        except (KeyboardInterrupt, SystemExit):
            exit()
        finally:
            if sender.poll() is None:
                sender.kill()
            receiver.kill()

            # clear out everything else in the socket buffer before we end
            timeout = self.sock.gettimeout()
            try:
                self.sock.settimeout(0)
                while True:
                    m, a = self.sock.recvfrom(4096)
            except socket.error:
                pass
            finally:
                self.sock.settimeout(timeout)

        if not os.path.exists(self.recv_outfile):
          raise RuntimeError("No data received by receiver!")
        self.current_test.result(self.recv_outfile)

class Packet(object):
    def __init__(self, packet, address, start_seqno_base):
        self.full_packet = packet
        self.address = address # where the packet is destined to

        # this is for making sure we have 0-indexed seq numbers throughout the
        # test.
        self.start_seqno_base = start_seqno_base
        try:
            pieces = packet.split('|')
            self.msg_type, self.seqno = pieces[0:2] # first two elements always treated as msg type and seqno
            self.checksum = pieces[-1] # last is always treated as checksum
            self.data = '|'.join(pieces[2:-1]) # everything in between is considered data
            self.seqno = int(self.seqno) - self.start_seqno_base
            assert(self.msg_type in ["start","data","ack","end"])
            int(self.checksum)
            self.bogon = False
        except Exception as e:
            # If a packet is invalid, this is set to true. We don't do anything
            # special otherwise, and it's passed along like every other packet.
            # However, since invalid packets may have undefined contents, it's
            # recommended to just pass these along and do no further processing
            # on them.
            self.bogon = True

    def update_packet(self, msg_type=None, seqno=None, data=None, full_packet=None, update_checksum=True):
        """
        This function handles safely changing the contents of a packet. By
        default, we re-compute the checksum every time the packet is updated.
        However, you can disable this if you intend to create a corrupted
        packet.
        Note that the checksum is calculated over the NON-0-indexed sequence number.
        """
        if not self.bogon:
            if msg_type == None:
                msg_type = self.msg_type
            if seqno == None:
                seqno = self.seqno
            if data == None:
                data = self.data

            if msg_type == "ack": # doesn't have a data field, so handle separately
                body = "%s|%d|" % (msg_type, seqno)
                checksum_body = "%s|%d|" % (msg_type, seqno + self.start_seqno_base)
            else:
                body = "%s|%d|%s|" % (msg_type,seqno,data)
                checksum_body = "%s|%d|%s|" % (msg_type, seqno + self.start_seqno_base, data)
            if update_checksum:
                checksum = Checksum.generate_checksum(checksum_body)
            else:
                checksum = self.checksum
            self.msg_type = msg_type
            self.seqno = seqno
            self.data = data
            self.checksum = checksum
            if full_packet:
                self.full_packet = full_packet
            else:
                self.full_packet = "%s%s" % (body,checksum)

    def __repr__(self):
        return "%s|%s|...|%s" % (self.msg_type, self.seqno, self.checksum)

if __name__ == "__main__":
    # Don't modify anything below this line!
    import getopt
    import sys

    def usage():
        print "Forwarder/Test harness for AUTP"
        print "-p PORT | --port PORT Base port value (default: 33123)"
        print "-s SENDER | --sender SENDER The path to Sender implementation (default: Sender.py)"
        print "-r RECEIVER | --receiver RECEIVER The path to the Receiver implementation (default: Receiver.py)"
        print "-h | --help Print this usage message"

    try:
        opts, args = getopt.getopt(sys.argv[1:],
                                "p:s:r:", ["port=", "sender=", "receiver="])
    except:
        usage()
        exit()

    port = 33123
    sender = "Sender.py"
    receiver = "Receiver.py"

    for o,a in opts:
        if o in ("-p", "--port"):
            port = int(a)
        elif o in ("-s", "--sender"):
            sender = a
        elif o in ("-r", "--receiver"):
            receiver = a

    f = Forwarder(sender, receiver, port)
    tests_to_run(f)
    f.execute_tests()


#Checksum
import binascii

# Assumes last field is the checksum!
def validate_checksum(message):
    try:
        msg,reported_checksum = message.rsplit('|',1)
        msg += '|'
        return generate_checksum(msg) == reported_checksum
    except:
        return False

# Assumes message does NOT contain final checksum field. Message MUST end
# with a trailing '|' character.
def generate_checksum(message):
    return str(binascii.crc32(message) & 0xffffffff)


#unreliable sender
import sys
import socket
import getopt

import Checksum
import BasicSender

'''
This is an unreliable sender class that reads from a file or STDIN.
'''
class UnreliableSender(BasicSender.BasicSender):
    # Handles a response from the receiver.
    def handle_response(self,response_packet):
        if Checksum.validate_checksum(response_packet):
            print "recv: %s" % response_packet
        else:
            print "recv: %s <--- CHECKSUM FAILED" % response_packet

    # Main sending loop.
    def start(self):
        seqno = 0
        msg = self.infile.read(500)
        msg_type = None
        while not msg_type == 'end':
            next_msg = self.infile.read(500)

            msg_type = 'data'
            if seqno == 0:
                msg_type = 'start'
            elif next_msg == "":
                msg_type = 'end'

            packet = self.make_packet(msg_type,seqno,msg)
            self.send(packet)
            print "sent: %s" % packet

            response = self.receive()
            self.handle_response(response)

            msg = next_msg
            seqno += 1

        self.infile.close()

'''
This will be run if you run this script from the command line. You should not
need to change any of this.
'''
if __name__ == "__main__":
    def usage():
        print "BEARS-TP Unreliable Sender"
        print "Sends data unreliably from a file or STDIN."
        print "-f FILE | --file=FILE The file to transfer; if empty reads from STDIN"
        print "-p PORT | --port=PORT The destination port, defaults to 33122"
        print "-a ADDRESS | --address=ADDRESS The receiver address or hostname, defaults to localhost"
        print "-h | --help Print this usage message"

    try:
        opts, args = getopt.getopt(sys.argv[1:],
                               "f:p:a:", ["file=", "port=", "address="])
    except:
        usage()
        exit()

    port = 33122
    dest = "localhost"
    filename = None

    for o,a in opts:
        if o in ("-f", "--file="):
            filename = a
        elif o in ("-p", "--port="):
            port = int(a)
        elif o in ("-a", "--address="):
            dest = a

    s = UnreliableSender(dest,port,filename)
    try:
        s.start()
    except (KeyboardInterrupt, SystemExit):
        exit()

# option 2 for server.py (Receiver)
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((socket.gethostname(), 1234))
s.listen(5) #will set a queue of 5 

while True:
    clientsocket, address = s.accept()
    print(f"Connection from {address} has been established")
    clientsocket.send(bytes("Welcome to the server!"))


#option 2 for client.py (Sender)
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((socket.gethostname(), 1234))

while True:
    msg = s.recv(8)
    print(msg.decode("utf-8"))
