
import json
import os
import socket
import time
import queue

from threading import Thread,Lock
from urllib.parse import urlparse

import requests

from tqdm import tqdm
from websocket import create_connection

from web_rpc_api import *


class share_dict:

    def __init__(self):
        self.thread_lock = Lock()
        self.data_dict = dict()

    def append(self,key,value):
        self.thread_lock.acquire()
        self.data_dict[key] = value
        self.thread_lock.release()

    def is_exist_key(self,key):
        self.thread_lock.acquire()
        result = key in self.data_dict
        self.thread_lock.release()

        return result

    def is_exist_key_list(self,key_list):
        self.thread_lock.acquire()
        result = []
        for key in key_list:
            if not key in self.data_dict:
                continue
            result.append(key)
        self.thread_lock.release()

        return result

    def is_exist_value(self,value):
        self.thread_lock.acquire()
        _,data_value_list = self.data_dict.items()
        result = value in data_value_list
        self.thread_lock.release()

        return result

    def get_key(self,key):
        self.thread_lock.acquire()
        if key in self.data_dict:
            result = self.data_dict[key]
        else:
            result = None
        self.thread_lock.release()

        return result

    def remove_key(self,key):
        self.thread_lock.acquire()
        self.data_dict.pop(key)
        self.thread_lock.release()

    def get_size(self):
        self.thread_lock.acquire()
        result = len(self.data_dict)
        self.thread_lock.release()

        return result

def websocket_miner_watch_thread(websocket_list,find_tx_list,console_log_imp):
    while len(websocket_list):
        websocket_url = websocket_list[0]

        if len(websocket_list) > 1:
            websocket_list = websocket_list[1:]
        else:
            websocket_list = []

        try:
            websocket_miner_watch_thread_logic(websocket_url,find_tx_list,console_log_imp)
        except:
            pass

def websocket_miner_watch_thread_logic(websocket_url,find_tx_list,console_log_imp):
    websocket = create_connection(websocket_url)
    json_data = json.dumps({"jsonrpc":"2.0","id": 2, "method": "eth_subscribe", "params": ["alchemy_minedTransactions"]})
    websocket.send(json_data)
    recv_text = websocket.recv()

    console_log_imp.log('websocket_miner_watch_thread_logic Running!')
    total_time = 0.0
    total_tx = 0

    while True:
        recv_text = websocket.recv()
        json_data = json.loads(recv_text)
        block_number = int(json_data['params']['result']['transaction']['blockNumber'],16)
        tx_hash = json_data['params']['result']['transaction']['hash']
        
        mempool_find_timetick = find_tx_list.get_key(tx_hash)

        if not mempool_find_timetick:
            continue

        using_time = time.time() - mempool_find_timetick
        total_time += using_time
        total_tx += 1

        console_log_imp.log('TX hash %s  Using:%0.4fs AVG:%0.4fs' % (tx_hash,using_time,total_time / total_tx))

def websocket_pending_watch_thread(websocket_list,find_tx_list,console_log_imp):
    while len(websocket_list):
        websocket_url = websocket_list[0]

        if len(websocket_list) > 1:
            websocket_list = websocket_list[1:]
        else:
            websocket_list = []

        try:
            websocket_pending_watch_logic(websocket_url,find_tx_list,console_log_imp)
        except:
            pass

def websocket_pending_watch_logic(websocket_url,find_tx_list,console_log_imp):
    websocket = create_connection(websocket_url)
    json_data = json.dumps({"jsonrpc":"2.0","id": 2, "method": "eth_subscribe", "params": ["alchemy_pendingTransactions"]})
    websocket.send(json_data)
    recv_text = websocket.recv()

    console_log_imp.log('websocket_pending_watch_logic Running!')

    while True:
        recv_text = websocket.recv()
        json_data = json.loads(recv_text)
        tx_info = json_data['params']['result']
        tx_hash = tx_info['hash']

        if not tx_info['to']:
            continue
        
        if not tx_info['to'].lower() in [
                '0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD'.lower(),
                '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'.lower(),
                '0xE592427A0AEce92De3Edee1F18E0157C05861564'.lower()
        ]:
            continue

        find_tx_list.append(tx_hash,time.time())

def load_websocket_list(file_path):
    file = open(file_path)
    data = file.read().split('\n')
    file.close()

    result = []

    for websocket_url in data:
        result.append(websocket_url)

    return result

class console_log:

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    LIGHTBLUE = "\033[94m"
    RESET = "\033[0m"

    def __init__(self,position,bar_desc,unit):
        self.pbar = tqdm(total=None,position=position, dynamic_ncols=True, desc=bar_desc, unit=unit)
        
    def tick_add(self):
        self.pbar.update(1)

    def output_to_state_bar(self,info):
        self.pbar.set_description(info)

    def log(self,info):
        tqdm.write('%s -- %s' % (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(time.time()))),info))

    def warning(self,info):
        tqdm.write('%s%s -- %s%s' % (console_log.YELLOW,time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(time.time()))),info,console_log.RESET))

def ping_rpc(url):
    start_time = time.time()
    requests.get(url)
    return time.time() - start_time

def ping_mempool(url):
    start_time = time.time()
    requests.get(url)
    return time.time() - start_time

def ping_flashbot(url_list):
    result_list = {}

    for url in url_list:
        start_time = time.time()
        requests.get(url)
        result_list[url] = time.time() - start_time

    return result_list

def get_ip_location(ip):
    url = f"https://ipinfo.io/{ip}/json"
    response = requests.get(url)
    data = response.json()

    return data.get("city"),data.get("region"),data.get("country")

def ping_thread(rpc_url,mempool_url,flashbot_url_list,console_log_imp):
    rpc_urlparse_imp = urlparse(rpc_url)
    rpc_address = socket.gethostbyname(rpc_urlparse_imp.netloc)
    console_log_imp.log('%s (%s) = %s' % (rpc_url,rpc_address,get_ip_location(rpc_address)))
    
    mempool_urlparse_imp = urlparse(mempool_url)
    mempool_address = socket.gethostbyname(mempool_urlparse_imp.netloc)
    console_log_imp.log('%s (%s) = %s' % (mempool_url,mempool_address,get_ip_location(mempool_address)))
    
    for flashbot_url in flashbot_url_list:
        flashbot_urlparse_imp = urlparse(flashbot_url)
        flashbot_address = socket.gethostbyname(flashbot_urlparse_imp.netloc)
        console_log_imp.log('%s (%s) = %s' % (flashbot_url,flashbot_address,get_ip_location(flashbot_address)))
    
    while True:
        ping_rpc_time = ping_rpc(rpc_url)
        ping_mempool_time = ping_mempool(mempool_url)
        ping_flashbot_time = ping_flashbot(flashbot_url_list)

        output_rpc_and_mempool = '[RPC=%0.4fs /Mempool=%0.4fs]' % (ping_rpc_time,ping_mempool_time)
        output_flashbot_list = ''

        for url,ping_time in ping_flashbot_time.items():
            output_flashbot_list += '[URL=%s %0.4fs]   ' % (url,ping_time)

        console_log_imp.warning(output_rpc_and_mempool)
        console_log_imp.warning(output_flashbot_list)
        time.sleep(5)

'''

    测试结论:
        服务器对比: HK和硅谷服务器

        1.硅谷服务器连RPC/Mempool比HK快,但是从最终的发现MempoolTX到上链的时间来看其实没有差别(指两者延时时差范围为+[0.01s,0.25s])
        2.硅谷服务器Flahbot广播比HK快
        3.测试了30分钟,TX从发现到上链的平均时间是9-11.5s这个区间浮动

'''


if __name__  == '__main__':
    websocket_list = ['wss://eth-mainnet.g.alchemy.com/v2/c0jcUP3zEPmUWR2efDA0rnaQ-01Rbvol'] # load_websocket_list('./websock_api.txt')
    remote_rpc_url = 'https://burned-sly-dew.quiknode.pro//'
    mempool_rpc_url = 'https://eth-mainnet.g.alchemy.com/v2/BENiXN77iNOhl7Y14wBYBUoUNLYifXI3'
    flashbot_rpc_list = [
        'https://relay.flashbots.net/',
        'https://rpc.beaverbuild.org/',
        'https://rsync-builder.xyz/',
        'https://builder0x69.io/',
        'https://rpc.titanbuilder.xyz/',
        'https://builder.gmbit.co/rpc'
    ]
    remote_web3 = rpc_api(remote_rpc_url)

    find_tx_list = share_dict()
    console_log_imp = console_log(0,'','')

    websocket_pending_watch_thread_imp = Thread(target=websocket_pending_watch_thread,args=(websocket_list,find_tx_list,console_log_imp))
    websocket_miner_watch_thread_imp = Thread(target=websocket_miner_watch_thread,args=(websocket_list,find_tx_list,console_log_imp))
    ping_thread_imp = Thread(target=ping_thread,args=(remote_rpc_url,mempool_rpc_url,flashbot_rpc_list,console_log_imp))
    websocket_pending_watch_thread_imp.daemon = True
    websocket_miner_watch_thread_imp.daemon = True
    ping_thread_imp.daemon = True

    websocket_pending_watch_thread_imp.start()
    websocket_miner_watch_thread_imp.start()
    ping_thread_imp.start()

    websocket_pending_watch_thread_imp.join()
    websocket_miner_watch_thread_imp.join()




