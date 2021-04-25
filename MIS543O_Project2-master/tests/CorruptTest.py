import random
import BasicSender
import Checksum
from BasicSender import *
from BasicTest import *
DEBUG = 0

"""
This tests random packet corruption
"""

class CorruptTest(BasicTest):
    def handle_packet(self):
        for p in self.forwarder.in_queue:
            p_type = p.msg_type
            p_no = p.seqno
            if random.choice([True, False]):
                p.update_packet(msg_type=p_type, seqno=-1, data='corrupt', full_packet=None,  update_checksum=False)
                valid = Checksum.validate_checksum(p)
                self.forwarder.out_queue.append(p)
            else:
                self.forwarder.out_queue.append(p)
        #empty out in_queue
        self.forwarder.in_queue = []