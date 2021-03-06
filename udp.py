import socket, sys, time, os, struct, timeit, random, threading, select
from typing import List
from utils import rbt, network
from collections import deque
from pathlib import Path
from matplotlib import pyplot as plt
import statistics as stat

# class based implementation: https://stackoverflow.com/questions/67931356/getting-connection-reset-error-on-closing-a-client-in-udp-sockets

# no frills (mass send): Done, measure and visualize
# blind resending & reodering: Do a full blast send, randomly drop, ask for resend, measure
# varying mtu: done, have to measure
# compression: done, have to measure

# reliability: GoBackN & LL based, left selective partial
#       the purpose of this is to illustrate with resending so we need compare it in scenarios with high packet drop

# (randomly drop some): 
# congestion: very slow
# custom alt to reliability: LL

def no_frills_udp_client():

    PORT = 55681
    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.file')
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((serverIP, PORT))
    # s = struct.Struct('!IHH')
    # a = struct.Struct('!II')
    no_frills_buffer = list()
    
    with open(input_path, 'rb') as f:
        size = Path(input_path).stat().st_size
        total_packets = int(size/1472) + 1
        for i in range(0, total_packets):
            payload = f.read(1472)
            no_frills_buffer.append(payload)

    timer = list()
    for k in range(10):
        start = time.time()
        for i in range(0, len(no_frills_buffer)):
            sock.send(no_frills_buffer[i])
        
        end = time.time() - start
        # print(len(timer))
        timer.append(end)
        time.sleep(1)

    print("Time taken:",stat.mean(timer))

# measure additional time taken for packet resending
# this will just mass resend

# send all those remain in rbt, by getting smallest and resending
# need a iterator that loops from smallest to largest
# then re order the packet and re assemble
to_send = True
start = 0
threshold = 20
EXIT = False

def rbt_sender(sock, total_packets, buffer):
    global SEND_LIST_seq, SEND_LIST_time
    global to_send, start, threshold, var_lock, EXIT
    
    while (True):
        if (threshold > 0 and to_send):
            #print("wdf2")
            var_lock.acquire()
            for i in range(start, start+threshold):
                try:
                    sock.send(buffer[i])
                    # print("SEND:",i)
                    SEND_LIST_seq.append(i)
                    SEND_LIST_time.append(time.time())

                    threshold -= 1
                except Exception as e:
                    #print("ERROR in sender:",e)
                    continue
            var_lock.release()  
            to_send = False
            # print("SENDING DONE")

        if (EXIT): break
    print("Sent all packets")

def rbt_receiver(sock, total_packets, a, tree, pos):
    global start, to_send, var_lock, threshold, EXIT
    global SEND_LIST_time, SEND_LIST_seq, ACK_LIST_seq, ACK_list_time
    counter = 2

    while (tree.size > 0):
        #print("wdf")
        data, addr = sock.recvfrom(1472)
        data = a.unpack(data)
        ack, seq = data[0], data[1]
        if (ack == 3):
            break

        if (ack == 1 and pos[seq]):
            #print("wdf4")
            node = pos[seq]
            tree.delete_obj(node)
            start = tree.minimum()
            if (start):
                start = start.item
            # print("Received:",seq)
            
            ACK_LIST_seq.append(seq)
            ACK_list_time.append(time.time())

            var_lock.acquire()
            to_send = True
            if (threshold < 20): threshold += counter
            counter += 1
            var_lock.release()
            
        elif (ack == 2): # resend
            #print("wdf5")
            var_lock.acquire()
            start = seq
            threshold = 20
            to_send = True
            counter = 2
            var_lock.release()
    
    print("Received all packets ack")
    EXIT = True

def packet_resending_udp_client(MTU=1472):
    global EXIT, SEND_LIST_seq, SEND_LIST_time, ACK_list_time, ACK_LIST_seq

    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.file')
    
    buffer = list()
    s = struct.Struct('!IHH')
    a = struct.Struct('!II')

    for i in range(100):
        EXIT = False
        pos = dict() # get pointer of seq to node
        tree = rbt.RedBlackTree()
        timer = list()
        
        # caching packets to send
        with open(input_path, 'rb') as f:
            size = Path(input_path).stat().st_size
            total_packets = int(size/MTU) + 1
            total_packets = 1000
            1472
            arr = [None]*(total_packets+1)
            # sequencing, this will be done on receiving side
            for i in range(total_packets):
                payload = f.read(1472)
                packet = network.create_packet(s, i, payload, total_packets)
                buffer.append(packet)

                node = tree.insert(i)
                pos[i] = node

        # identify route
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((serverIP, 6789))

        print("Experiment Sending initial")
        sock.send(a.pack(1, total_packets))
        print("Experiment awaiting reply for flood to begin")
        
        # get reply to start
        while True:
            data = sock.recvfrom(1472)
            break
        
        print("Experiment rbt udp received acknowledgement, experiment started")
        sender_thread = threading.Thread(
            target=rbt_sender, args=(sock, total_packets, buffer))
        receiver_thread = threading.Thread(
                target=rbt_receiver, args=(sock, total_packets, a, tree, pos))
        
        try:
            start = time.time()
            receiver_thread.start()
            sender_thread.start()
            receiver_thread.join()
            sender_thread.join()
            end = time.time()
        except Exception as e:
            print("Error in main")
            print(e)
            sock.close()
        
        end = time.time() - start
        timer.append(end)
        avg_time = stat.mean(timer)
        print("AVG Time taken:", avg_time)
        print("Experiment  complete")

        old_min = SEND_LIST_time[0]
        old_max = SEND_LIST_time[-1]

        old_min_ack = ACK_list_time[0]
        old_max_ack = ACK_list_time[-1]

        new_min = 0
        new_max = 100
        
        for i in range(0,len(SEND_LIST_time)):
            old_value = SEND_LIST_time[i]
            new_value = ( (old_value - old_min) / (old_max - old_min) ) * (new_max - new_min) + new_min
            SEND_LIST_time[i] = new_value

            try:
                old_value = ACK_list_time[i]
                new_value = ( (old_value - old_min_ack) / (old_max_ack - old_min_ack) ) * (new_max - new_min) + new_min
                ACK_list_time[i] = new_value


            except:
                continue
        
        plt.plot(SEND_LIST_seq, SEND_LIST_time, label='Send time')
        plt.plot(ACK_LIST_seq, ACK_list_time, label='rcv time')
        plt.xlabel('Packet number')
        plt.ylabel('Packet rcv/send time')
        plt.title('Packet number VS rcv/send time')
        plt.legend(loc="upper left")

        plt.savefig("./plots/rbt.png")
        # plt.plot(SEND_LIST_time, SEND_LIST_seq)

        # plt.plot(ACK_list_time, ACK_LIST_seq)
        # plt.xlabel('x - axis')
        # plt.ylabel('y - axis')
        # plt.savefig("./plots/rbt.png")

        time.sleep(2)

def varying_mtu_udp_client():
    PORT = 7890
    MTUS = [128, 256, 512, 1024, 1472, 2048, 4096, 6144, 8192, 10240]
    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.file')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((serverIP, PORT))
    s = struct.Struct('!II')
    a = struct.Struct('!dd')

    size = Path(input_path).stat().st_size
    for mtu in MTUS:  # loop mtus
        timer = list()
        lost = list()

        for i in range(10):
            with open(input_path, 'rb') as f:
                total_packets = int(size/mtu) + 1
                print("Experiment -", mtu, ": new experiment started")

                # we have to send a prior packet to inform mtu
                print("Experiment -", mtu, ": Sending initial")

                init_packet = s.pack(mtu, total_packets)
                sock.send(init_packet)

                # sock.sendto(mtu, (serverIP, PORT))
                print("Experiment -", mtu, ": awaiting reply for flood to begin")
                # wait for acknowledgement before start
                flag = False

                while not flag:
                    data = sock.recv(mtu, socket.MSG_PEEK)
                    if (data):
                        flag = True
                    print("Experiment -", mtu,
                        ": received acknowledgement, beginning flood")

                time.sleep(2)
                for i in range(0, total_packets):
                    # print("send",i)
                    payload = f.read(mtu)
                    sock.send(payload)

                print("Experiment -", mtu, ": finished transmission, awaiting results")
                results = []
                while True:
                    data, addr = sock.recvfrom(mtu)
                    results.append(data)
                    if (len(results) == 2):
                        break
                
                time_taken, percent_received = a.unpack(results[-1])
                # print(time_taken, percent_received)
                timer.append(time_taken)
                lost.append(percent_received)

                # while not flag:
                #     data = sock.recvfrom(mtu)
                #     if (data):
                #         print(data)
                #         flag = True

                print("Experiment -", mtu, ": received results")

            print("Experiment -", mtu, ": reset for 15s")
            time.sleep(2)
        print("AVG TIME:",stat.mean(timer))
        print("AVG TIME:",stat.mean(lost))

buffer = list()
time_stamp = list()
last_ack_sent = -1
in_transit = 0
var_lock = threading.Lock()

# send line: 
# ack line
# on start, mark the time
# on receive we will mark the time, and sequence number as y and x axis
# get end time
# get diff between start and end, divide into timestamps, fit each packet time into 

def go_back_N_sender(sock, total_packets, window_size, retransmission_time):
    global buffer
    global last_ack_sent
    global in_transit
    global time_stamp
    global SEND_LIST_seq, SEND_LIST_time

    time_stamp = [None]*total_packets
    try:
        while (last_ack_sent + 1 < total_packets):
            var_lock.acquire()
            packetCount = last_ack_sent + in_transit + 1  # get current index of packet to send
            # if packets sent is less than window and index within range
            if (in_transit < window_size and packetCount < total_packets):
                sock.send(buffer[packetCount])  # send packet in current index
                starter = time.time()
                time_stamp[packetCount] = starter  # start timer
                in_transit += 1  # increment num packets sent
                SEND_LIST_seq.append(packetCount)
                SEND_LIST_time.append(starter)

            # check for timeout in earliest sent packet
            if (in_transit > 0 and time.time() - time_stamp[last_ack_sent + 1] > retransmission_time):
                # print("Sequence Number:", last_ack_sent + 1, "timed out")
                in_transit = 0  # if timed out, resend all in window

            var_lock.release()

        print("Experiment -", window_size, ": Sent all packets")
    except Exception as e:
        print("error in sender")
        print(e)

def go_back_N_receiver(sock, total_packets, a):
    global buffer
    global last_ack_sent
    global in_transit
    global time_stamp
    global SEND_LIST_time, SEND_LIST_seq, ACK_LIST_seq, ACK_list_time

    while (last_ack_sent + 1 < total_packets):
        if (in_transit > 0):  # if packets have been sent
            data, addr = sock.recvfrom(1472)
            data = a.unpack(data)
            ack, seq = data[0], data[1]

            var_lock.acquire()
            if (ack):  # if it is an acknowledgement for receipt of packet
                if (last_ack_sent + 1 == seq):
                    last_ack_sent += 1
                    in_transit -= 1
                    ACK_LIST_seq.append(seq)
                    ACK_list_time.append(time.time())

                else:
                    in_transit = 0
            else:  # faulty packet
                in_transit = 0
            var_lock.release()

def go_back_N_udp_client():
    global buffer
    global time_stamp
    global last_ack_sent
    global in_transit

    PORT = 8000
    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.file')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((serverIP, PORT))
    s = struct.Struct('!IHH')
    a = struct.Struct('!II')
    timer = list()

    for i in range(1):
        k = 20
        print("Experiment -", k, ": new experiment started")
        with open(input_path, 'rb') as f:
            size = Path(input_path).stat().st_size
            total_packets = int(size/1472) + 1
            total_packets = 1000

            for i in range(0, total_packets + 1):
                payload = f.read(1472)
                buffer.append(network.create_packet(
                    s, i, payload, total_packets))

            print("Experiment -", k, ": Sending initial")
            init_rtt = time.time()
            sock.send(a.pack(1, total_packets))
            print("Experiment -", k, ": awaiting reply for flood to begin")

            TIMEOUT = 0
            while True:
                data = sock.recvfrom(1472)
                init_rtt = time.time() - init_rtt
                TIMEOUT = max(init_rtt+init_rtt+0.05, TIMEOUT)
                break
            # timeout heuristic: 2*RTT + 1*processing_time

            print("Experiment -", k,
                  ": received acknowledgement, experiment started")
            receiver_thread = threading.Thread(
                target=go_back_N_receiver, args=(sock, total_packets, a))
            sender_thread = threading.Thread(
                target=go_back_N_sender, args=(sock, total_packets, k, (0.2)))

            try:
                start = time.time()
                receiver_thread.start()
                sender_thread.start()
                receiver_thread.join()
                sender_thread.join()
            except Exception as e:
                print("Error in main")
                print(e)
                sock.close()

            end = time.time() - start
            print("Experiment -", k, ": complete")
            timer.append(end)
            print("AVG:",stat.mean(timer))

            buffer = list()
            time_stamp = list()
            last_ack_sent = -1
            in_transit = 0


            old_min = SEND_LIST_time[0]
            old_max = SEND_LIST_time[-1]

            old_min_ack = ACK_list_time[0]
            old_max_ack = ACK_list_time[-1]

            new_min = 0
            new_max = 100
            
            for i in range(0,len(SEND_LIST_time)):
                old_value = SEND_LIST_time[i]
                new_value = ( (old_value - old_min) / (old_max - old_min) ) * (new_max - new_min) + new_min
                SEND_LIST_time[i] = new_value

                try:
                    old_value = ACK_list_time[i]
                    new_value = ( (old_value - old_min_ack) / (old_max_ack - old_min_ack) ) * (new_max - new_min) + new_min
                    ACK_list_time[i] = new_value


                except:
                    continue
            
            plt.plot(SEND_LIST_seq, SEND_LIST_time, label='Send time')
            plt.plot(ACK_LIST_seq, ACK_list_time, label='rcv time')
            plt.xlabel('Packet number')
            plt.ylabel('Packet rcv/send time')
            plt.title('Packet number VS rcv/send time')
            plt.legend(loc="upper left")

            plt.savefig("./plots/gobackn.png")

        time.sleep(3)

    sock.close()



slidingWindow = {}
isPacketTransferred = True
windowLock = threading.Lock()
STOP = False
def ack_receiver(clientSocket, a):
    global isPacketTransferred
    global slidingWindow
    global windowLock
    
    try:
        while len(slidingWindow) > 0 or isPacketTransferred:
            if len(slidingWindow) > 0:
                data, addr = clientSocket.recvfrom(1472)
                data = a.unpack(data)
                ack, seq = data[0], data[1]

                if (ack):
                    if seq in slidingWindow:
                        # print(seq)
                        windowLock.acquire()
                        del (slidingWindow[seq])
                        if len(dataPackets) == seq + 1:
                            print("Last acknowledgement received!!")

                        windowLock.release()
                        if (seq == 999): 
                            STOP = True
                            break
    except:
        clientSocket.close()

def rdt_send(clientSocket, N, retransmissionTime, total_packets, dataPackets):
    global slidingWindow
    global windowLock
    global isPacketTransferred

    sentPacketNum = 0
    while sentPacketNum < total_packets:
        if (STOP): break
        if N > len(slidingWindow):
            windowLock.acquire()
            slidingWindow[sentPacketNum] = time.time()

            clientSocket.send(dataPackets[sentPacketNum])
            if sentPacketNum == total_packets: isPacketTransferred = False
            windowLock.release()

            while sentPacketNum in slidingWindow:
                windowLock.acquire()
                if sentPacketNum in slidingWindow:
                    if(time.time() - slidingWindow[sentPacketNum]) > retransmissionTime:
                        # print("Time out, Sequence Number = {}".format(str(sentPacketNum)))
                        slidingWindow[sentPacketNum] = time.time()
                        clientSocket.send(dataPackets[sentPacketNum])
                windowLock.release()
            sentPacketNum += 1

# this is wrong, there are two windows
# https://www.geeksforgeeks.org/sliding-window-protocol-set-3-selective-repeat/
def selective_repeat_udp_client():
    global selective_buffer, dataPackets
    global window
    global packet_transferred

    PORT = 7890
    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.file')
    dataPackets = list()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((serverIP, PORT))
    s = struct.Struct('!IHH')
    a = struct.Struct('!II')

    for i in range(10):
        k = 20
        print("Experiment -", k, ": new experiment started")
        with open(input_path, 'rb') as f:
            size = Path(input_path).stat().st_size
            total_packets = int(size/1472) + 1
            total_packets = 1000

            for i in range(0, total_packets + 1):
                payload = f.read(1472)
                dataPackets.append(network.create_packet(
                    s, i, payload, total_packets))

            print("Experiment -", k, ": Sending initial")
            init_rtt = time.time()
            sock.send(a.pack(1, total_packets))
            print("Experiment -", k, ": awaiting reply for flood to begin")

            TIMEOUT = 0
            while True:
                data = sock.recvfrom(1472)
                init_rtt = time.time() - init_rtt
                TIMEOUT = max(init_rtt+init_rtt+0.05, TIMEOUT)
                break
            # timeout heuristic: 2*RTT + 1*processing_time

            print("Experiment -", k,
                  ": received acknowledgement, experiment started")
            receiver_thread = threading.Thread(
                target=ack_receiver, args=(sock, a))
            sender_thread = threading.Thread(
                target=rdt_send, args=(sock, k, TIMEOUT, total_packets, dataPackets))

            try:
                start = time.time()
                receiver_thread.start()
                sender_thread.start()
                receiver_thread.join()
                sender_thread.join()
            except Exception as e:
                print("Error in main")
                print(e)
                sock.close()

            print("Experiment -", k, ":", time.time()-start)
            print("Experiment -", k, ": complete")
            print("Resetting for 20 secs")
        time.sleep(20)
        # break

import zlib
def compress_text():
    PORT = 55681
    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.txt')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((serverIP, PORT))
    z = zlib.compressobj(-1,zlib.DEFLATED,31)
    s = struct.Struct('i')
    a = struct.Struct('!II')
    send_buffer = list()
    sock.settimeout(5.0)
    
    with open(input_path, 'rb') as f:
        size = Path(input_path).stat().st_size
        total_packets = int(size/1472) + 1

        for i in range(0, total_packets + 1):
            payload = f.read(1472)
            gzip_compressed_data = zlib.compress(payload, 1)
            send_buffer.append(gzip_compressed_data)

        print("Experiment sending initial")
        sock.send(a.pack(1, total_packets))
        print("Experiment awaiting reply for flood to begin")

        while True:
            data = sock.recvfrom(1472)
            break
        print("Received acknowledgement, experiment started")
        print(total_packets)

        count = 0
        start = time.time()
        while count <= total_packets:
            sock.send(send_buffer[0])
            count += 1
        
        sock.settimeout(3600)
        while True:
            data = sock.recvfrom(1472)
            break
        end = time.time() - start
        
    print(end)
    print("Experiment complete")

    sock.close()

import utils.ll as linkedlist
POINTER_ARR = list()
LL_NUM_ACK = 0
SLIDING_WINDOW = {}
LL_LOCK = threading.Lock()
LL_BUFFER = linkedlist.dLinkedList()
WAITED = 0
STOP_THREAD = False
SEND_LIST_seq = list()
SEND_LIST_time = list()
ACK_LIST_seq = list()
ACK_list_time = list()

def ll_sender(sock, total_packets, threshold, timeout, a):
    global SLIDING_WINDOW
    global LL_LOCK
    global LL_NUM_ACK
    global WAITED
    global LL_BUFFER
    global POINTER_ARR
    global STOP_THREAD
    global SEND_LIST
    
    print("Total packets to send:",total_packets)
    while (LL_BUFFER.length > 0):
        LL_LOCK.acquire()
        for k, v in SLIDING_WINDOW.items():
            if ((time.time() - v[0]) > 0.05):
                try:
                    sock.send(v[2].get_data())
                    sent_time = time.time()
                    SLIDING_WINDOW[k][0] = sent_time
                    SEND_LIST_seq.append(k)
                    SEND_LIST_time.append(sent_time)
                except:
                    continue
        LL_LOCK.release()

        if (len(SLIDING_WINDOW) < threshold):
            LL_LOCK.acquire()
            node = LL_BUFFER.get_start()
            for i in range(LL_NUM_ACK, LL_NUM_ACK+threshold+1):
                if (not node.was_sent()):
                    try:
                        node.set_sent()
                        sent_time = time.time()
                        SLIDING_WINDOW[node.get_idx()] = [sent_time, 0, node] # start time, rtt, pointer
                        sock.send(node.get_data())
                        SEND_LIST_seq.append(node.get_idx())
                        SEND_LIST_time.append(sent_time)
                        node = node.get_next()
                    except Exception as e:
                        #STOP_THREAD = True
                        break
            LL_LOCK.release()
            
            if (STOP_THREAD): break
        if (STOP_THREAD): break                  

    print("All packets sent")

def ll_receiver(sock, a):
    global SLIDING_WINDOW
    global LL_LOCK
    global LL_BUFFER
    global POINTER_ARR
    global LL_NUM_ACK
    global WAITED
    global STOP_THREAD
    global ACK_LIST
    global SEND_LIST_time, SEND_LIST_seq, ACK_LIST_seq, ACK_list_time
    
    while (LL_BUFFER.length > 0):
        while (len(SLIDING_WINDOW) > 0):
            r, _, _ = select.select([sock],[],[],0)
            if (r):
                data, addr = sock.recvfrom(1500)
                data = a.unpack(data)
                ack, seq = data[0], data[1]

                if (seq in SLIDING_WINDOW):
                    ACK_LIST_seq.append(seq)
                    ACK_list_time.append(time.time())

                    LL_LOCK.acquire()
                    if (seq == (LL_NUM_ACK + 1)): 
                        if (WAITED > 0):
                            LL_NUM_ACK += WAITED
                            WAITED = 0
                        else:
                            LL_NUM_ACK += 1
                    else: 
                        WAITED += 1
                    del (SLIDING_WINDOW[seq])
                    LL_BUFFER.remove(POINTER_ARR[seq]) # remove pointer
                    
                    # print(LL_BUFFER.length)
                    LL_LOCK.release()
            else:
                break
            
            if (STOP_THREAD): break
        if (STOP_THREAD): break
    
    print("Received all packets")

def ll_udp_client():
    global POINTER_ARR
    global LL_BUFFER
    global SEND_LIST_time, SEND_LIST_seq, ACK_LIST_seq, ACK_list_time
    
    PORT = 7890
    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.file')
    timer = list()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((serverIP, PORT))
    s = struct.Struct('!IHH')
    a = struct.Struct('!IIf')

    window_threshold = 20
    
    for i in range(1):
        print("Experiment ll based window control started")
        with open(input_path, 'rb') as f:
            size = Path(input_path).stat().st_size

            total_packets = int(size/1472) + 1
            total_packets = 1000
            POINTER_ARR = [None]*(total_packets + 1)
            loss = 0.1

            for i in range(0, total_packets):
                payload = f.read(1472)
                payload = network.create_packet(s, i, payload, total_packets)
                if (isinstance(payload, (bytes))):
                    node = LL_BUFFER.insert(value=payload, idx=i)
                    POINTER_ARR[i] = node
                else:
                    print("WDF")

            print("Experiment Sending initial")
            init_rtt = time.time()
            sock.send(a.pack(1, total_packets+1, loss))
            print("Experiment awaiting reply for flood to begin")

            TIMEOUT = 0
            while True:
                data = sock.recvfrom(1472)
                init_rtt = time.time() - init_rtt
                TIMEOUT = max(init_rtt+init_rtt, TIMEOUT)
                break
                
            print("Experiment ll udp received acknowledgement, experiment started")

            sender_thread = threading.Thread(
                target=ll_sender, args=(sock, total_packets, 20, TIMEOUT, a))
            receiver_thread = threading.Thread(
                    target=ll_receiver, args=(sock, a))
            try:
                start = time.time()
                receiver_thread.start()
                sender_thread.start()

                receiver_thread.join()
                sender_thread.join()
                print("Ending thread")
            except Exception as e:
                print("Error in main")
                print(e)
                sock.close()
            
            end = time.time()
            diff = end-start
            timer.append(diff)
            print("AVG:",stat.mean(timer))

            old_min = SEND_LIST_time[0]
            old_max = SEND_LIST_time[-1]

            old_min_ack = ACK_list_time[0]
            old_max_ack = ACK_list_time[-1]

            new_min = 0
            new_max = 100
            
            for i in range(0,len(SEND_LIST_time)):
                old_value = SEND_LIST_time[i]
                new_value = ( (old_value - old_min) / (old_max - old_min) ) * (new_max - new_min) + new_min
                SEND_LIST_time[i] = new_value

                try:
                    old_value = ACK_list_time[i]
                    new_value = ( (old_value - old_min_ack) / (old_max_ack - old_min_ack) ) * (new_max - new_min) + new_min
                    ACK_list_time[i] = new_value


                except:
                    continue
            
            plt.plot(SEND_LIST_seq, SEND_LIST_time, label='Send time')
            plt.plot(ACK_LIST_seq, ACK_list_time, label='rcv time')
            plt.xlabel('Packet number')
            plt.ylabel('Packet rcv/send time')
            plt.title('Packet number VS rcv/send time')
            plt.legend(loc="upper left")

            plt.savefig("./plots/ll.png")



# https://granulate.io/understanding-congestion-control/
WINDOW_SIZE = 8
SSTHRESH = 0

LAST_ACK = 0
TIME_STAMP_ARR = []

CONGESTION_AVOIDANCE = False
LOSS_EVENT = False
AVG_RTT = 0

ACKS_ARR = []
IN_TRANSIT = 0

RANDOM_ERROR = 0
Counter = 2

WINDOW_SIZE_LIST = list()
WINDOW_SIZE_TIME = list()

SENT_TICK = False
RECEIVED_SET = set()

RESEND = None
RESEND_COUNTER = 0
curr_min_congestion = 0

congestion_lock = threading.Lock()
# https://www.cs.cmu.edu/~srini/15-441/F07/project3/project3.pdf
def congestion_receiver(sock, total_packets, a, congestion_buffer):
    global WINDOW_SIZE, SSTHRESH, IN_TRANSIT, LAST_ACK, AVG_RTT, STOP_THREAD
    global ACKS_ARR, LOSS_EVENT, MAX_RTT, TIME_STAMP_ARR, CONGESTION_AVOIDANCE # arr
    global WINDOW_SIZE_LIST, SENT_TICK, congestion_lock, RECEIVED_SET, RESEND, RESEND_COUNTER, curr_min_congestion
    waited = 0

    ACKS_ARR = [0]*(total_packets+1)
    while (len(RECEIVED_SET) < total_packets and not STOP_THREAD): # there are still packets yet to be 
        #if (IN_TRANSIT > 0):  # if there are packets in transit
                data, addr = sock.recvfrom(1500)
                data = a.unpack(data)
                ack, seq, curr_min_congestion = data[0], data[1], int(data[2])
                ACKS_ARR[seq] += 1

                if (ack == 3):
                    STOP_THREAD = True
                    break
                if (ACKS_ARR[seq] >= 3): # latest packet received had 3 acks
                    LOSS_EVENT = True # assume all packets after seq is lost
                    congestion_lock.acquire()
                    IN_TRANSIT = 0
                    congestion_lock.release()
                    continue
                if (ack == 1  and ACKS_ARR[seq] == 1): # valid ack
                    SENT_TICK = True
                    TIME_STAMP_ARR[seq][1] = time.time() - TIME_STAMP_ARR[seq][0] # record RTT
                    congestion_lock.acquire()
                    AVG_RTT = (AVG_RTT+TIME_STAMP_ARR[seq][1])/(LAST_ACK+1)
                    congestion_lock.release()
                    heur = AVG_RTT+AVG_RTT+0.01
                    
                    if (TIME_STAMP_ARR[seq][1] > heur): CONGESTION_AVOIDANCE = True
                    else: CONGESTION_AVOIDANCE = False
                    congestion_lock.acquire()
                    IN_TRANSIT -= 1
                    congestion_lock.release()
                    RECEIVED_SET.add(seq)

                    print ("ACK:",LAST_ACK)
                    congestion_lock.acquire()
                    if ((LAST_ACK + 1) == seq):
                        LAST_ACK += 1
                        LAST_ACK += waited
                        waited = 0
                    else: 
                        waited += 1
                        IN_TRANSIT = 0

                    if (curr_min_congestion):
                        sock.send(congestion_buffer[curr_min_congestion])  # resend packet in current index

                    congestion_lock.release()
                if (ack == 0):
                    starter = time.time()
                    sock.send(congestion_buffer[seq])  # resend packet in current index
                    TIME_STAMP_ARR[seq][0] = starter
                    SENT_TICK = True
                    LOSS_EVENT = True
                    WINDOW_SIZE_LIST.append(WINDOW_SIZE)
                    WINDOW_SIZE_TIME.append(starter) 
    
    print("All packets received")
    STOP_THREAD = True

def congestion_sender(sock, total_packets, retransmission_time, congestion_buffer):
    global WINDOW_SIZE, LAST_ACK, TIME_STAMP_ARR, RANDOM_ERROR, CONGESTION_AVOIDANCE
    global IN_TRANSIT, AVG_RTT, STOP_THREAD, SENT_TICK, RECEIVED_SET, curr_min_congestion

    TIME_STAMP_ARR = [[None,None] for i in range(0,total_packets)]
    
    while (len(RECEIVED_SET) < total_packets and not STOP_THREAD): # still have packets to send
        congestion_lock.acquire()
        packetCount = LAST_ACK + IN_TRANSIT + 1
        local_in_transit = IN_TRANSIT
        local_window = WINDOW_SIZE
        congestion_lock.release()

        while (local_in_transit < local_window and packetCount < total_packets and not STOP_THREAD):
            if (packetCount < curr_min_congestion): 
                packetCount += 1
                continue
            sock.send(congestion_buffer[packetCount])  # send packet in current index
            starter = time.time()
            TIME_STAMP_ARR[packetCount][0] = starter  # start timer

            congestion_lock.acquire()
            IN_TRANSIT += 1  # increment num packets sent
            congestion_lock.release()
            
            packetCount += 1
            WINDOW_SIZE_LIST.append(WINDOW_SIZE)
            WINDOW_SIZE_TIME.append(starter) 
            SENT_TICK = True

        if (IN_TRANSIT > 0):
            found = False
            heur = AVG_RTT+AVG_RTT+0.01
            count = 0
            
            congestion_lock.acquire()
            start = LAST_ACK+1
            end = start + IN_TRANSIT
            congestion_lock.release()
            stopper = int((end-start)/2)
            
            if (not TIME_STAMP_ARR[start][1] and len(RECEIVED_SET) > (start)*2):
                sock.send(congestion_buffer[start])
                TIME_STAMP_ARR[start][0] = time.time()

            for idx in range(start+1, end):
                # if (STOP_THREAD): break
                try:
                    if (not TIME_STAMP_ARR[idx][1] and (time.time() - TIME_STAMP_ARR[idx][0]) > min(0.05, heur)): # not ack and timed out
                        print("RESEND:",idx)
                        sock.send(congestion_buffer[idx])

                        TIME_STAMP_ARR[idx][0] = time.time()
                        CONGESTION_AVOIDANCE = True
                        found = True
                    # else:
                    #     count += 1
                    #     if (count == max(stopper,5)): 
                    #         break
                except Exception as e:
                    print(TIME_STAMP_ARR[idx][0])
                    print(e)
                    pass
            
            if (not found):
                congestion_lock.acquire()
                LAST_ACK += stopper
                congestion_lock.release()

    print("Experiment congestion control sent all packets")
    # STOP_THREAD = True

    
def handler():
    global CONGESTION_AVOIDANCE, LOSS_EVENT, WINDOW_SIZE, AVG_RTT, LAST_ACK
    global Counter, STOP_THREAD, SENT_TICK

    while True and not STOP_THREAD:
        if (WINDOW_SIZE > SSTHRESH): CONGESTION_AVOIDANCE = True
        
        if (CONGESTION_AVOIDANCE):
            if (SENT_TICK and WINDOW_SIZE < SSTHRESH):
                WINDOW_SIZE = min(50, WINDOW_SIZE + 1)
                Counter = 1
            SENT_TICK = False
        else:
            if SENT_TICK and WINDOW_SIZE < SSTHRESH:
                WINDOW_SIZE = min(50, WINDOW_SIZE + Counter)
                Counter += 1
                SENT_TICK = False
            
        if (LOSS_EVENT):
            WINDOW_SIZE = max(int(0.5*WINDOW_SIZE), 10)
            SENT_TICK = False
            LOSS_EVENT = False
            Counter = 1
        
def congestion_control():
    global SSTHRESH, RANDOM_ERROR, WINDOW_SIZE_LIST, WINDOW_SIZE_TIME
    global SEND_LIST_time, SEND_LIST_seq, ACK_LIST_seq, ACK_list_time
    
    PORT = 7890
    serverIP = socket.gethostbyname(socket.gethostname())
    input_path = os.path.join('./data/', 'test.file')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((serverIP, PORT))
    s = struct.Struct('!IHH')
    a = struct.Struct('!IIf')
    congestion_buffer = list()
    
    print("Experiment congestion control started")
    with open(input_path, 'rb') as f:
        size = Path(input_path).stat().st_size
        SSTHRESH = 50

        total_packets = int(size/1472) + 1
        total_packets = 1000
        for i in range(0, total_packets + 1):
            payload = f.read(1472)
            congestion_buffer.append(network.create_packet(
                s, i, payload, total_packets))

        print("Experiment Sending initial")
        init_rtt = time.time()
        sock.send(a.pack(1, total_packets, RANDOM_ERROR))
        print("Experiment awaiting reply for flood to begin")

        TIMEOUT = 0
        while True:
            data = sock.recvfrom(1472)
            init_rtt = time.time() - init_rtt
            TIMEOUT = max(init_rtt+init_rtt+0.05, TIMEOUT)
            break
        # timeout heuristic: 2*RTT + 1*processing_time

        print("Experiment received acknowledgement, experiment started")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF,total_packets*1500)

        receiver_thread = threading.Thread(
            target=congestion_receiver, args=(sock, total_packets, a, congestion_buffer))
        sender_thread = threading.Thread(
            target=congestion_sender, args=(sock, total_packets, TIMEOUT, congestion_buffer))
        handler_thread = threading.Thread(target=handler, args=())
        #resender_thread = threading.Thread(target=resender, args=(sock, congestion_buffer, total_packets))

        try:
            start = time.time()
            receiver_thread.start()
            sender_thread.start()
            handler_thread.start()
            #resender_thread.start()

            receiver_thread.join()
            sender_thread.join()
            handler_thread.join()
            #resender_thread.join()   

            end = time.time() - start
            print(end)
        except Exception as e:
            print("Error in main")
            print(e)
            sock.close()
        end = time.time() - start

        old_min = WINDOW_SIZE_TIME[0]
        old_max = WINDOW_SIZE_TIME[-1]
        new_min = 0
        new_max = 1000
        
        for i in range(0,len(WINDOW_SIZE_TIME)):
            old_value = WINDOW_SIZE_TIME[i]
            new_value = ( (old_value - old_min) / (old_max - old_min) ) * (new_max - new_min) + new_min
            WINDOW_SIZE_TIME[i] = new_value

        plt.plot(WINDOW_SIZE_TIME, WINDOW_SIZE_LIST, label='Window size')
        # plt.plot(ACK_LIST_seq, ACK_list_time, label='rcv time')
        plt.xlabel('Time')
        plt.ylabel('Window size')
        plt.title('Window size VS time')
        plt.legend(loc="upper left")

        plt.savefig("./plots/congestion_window.png")
    
    print("Experiment over")
    time.sleep(20)

if __name__ == "__main__":
    no_frills_udp_client()
    # varying_mtu_udp_client()
    # packet_resending_udp_client(1472)
    # compress_text()
    # ll_udp_client()
    # selective_repeat_udp_client()
    # go_back_N_udp_client()
    # congestion_control()