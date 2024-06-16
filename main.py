
import json
import os
import time
import queue

from threading import Thread,Lock
import multiprocessing

import requests

from tqdm import tqdm
from websocket import create_connection

from match_logic import *
from mev_bot_api import *
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

def load_websocket_list(file_path):
    file = open(file_path)
    data = file.read().split('\n')
    file.close()

    result = []

    for websocket_url in data:
        result.append(websocket_url)

    return result


class blocknumber_sync:

    def __init__(self):
        self.block_number = 0
        self.thread_lock = Lock()

    def set_blocknumber(self,block_number):
        self.thread_lock.acquire()
        if block_number > self.block_number:
            self.block_number = block_number
        self.thread_lock.release()
        
    def get_blocknumber(self):
        self.thread_lock.acquire()
        result = self.block_number
        self.thread_lock.release()
        return result
        

def websocket_miner_watch_thread(websocket_list,commit_to_block_tx_list,blocknumber_sync_imp,console_log_imp):
    while len(websocket_list):
        websocket_url = websocket_list[0]

        if len(websocket_list) > 1:
            websocket_list = websocket_list[1:]
        else:
            websocket_list = []

        console_log_imp.log('websocket_miner_watch_thread >>  Switch Websocket URL == %s' % (websocket_url))

        try:
            websocket_miner_watch_thread_logic(websocket_url,commit_to_block_tx_list,blocknumber_sync_imp,console_log_imp)
        except:
            pass

def websocket_miner_watch_thread_logic(websocket_url,commit_to_block_tx_list,blocknumber_sync_imp,console_log_imp):
    websocket = create_connection(websocket_url)
    json_data = json.dumps({"jsonrpc":"2.0","id": 2, "method": "eth_subscribe", "params": ["alchemy_minedTransactions"]})
    websocket.send(json_data)
    recv_text = websocket.recv()

    console_log_imp.log('websocket_pending_watch_logic >> Subscribe return %s ' % (recv_text))

    while True:
        recv_text = websocket.recv()
        json_data = json.loads(recv_text)
        block_number = int(json_data['params']['result']['transaction']['blockNumber'],16)
        tx_hash = json_data['params']['result']['transaction']['hash']
        
        blocknumber_sync_imp.set_blocknumber(block_number)

        commit_to_block_tx_list.append(tx_hash,block_number)
        console_log_imp.tick_add()

def websocket_pending_watch_thread(websocket_list,tx_input_pipe_object,console_log_imp):
    while len(websocket_list):
        websocket_url = websocket_list[0]

        if len(websocket_list) > 1:
            websocket_list = websocket_list[1:]
        else:
            websocket_list = []

        console_log_imp.log('websocket_pending_watch_thread >>  Switch Websocket URL == %s' % (websocket_url))

        try:
            websocket_pending_watch_logic(websocket_url,tx_input_pipe_object,console_log_imp)
        except:
            pass

def websocket_pending_watch_logic(websocket_url,tx_input_pipe_object,console_log_imp):
    websocket = create_connection(websocket_url)
    json_data = json.dumps({"jsonrpc":"2.0","id": 2, "method": "eth_subscribe", "params": ["alchemy_pendingTransactions"]})
    websocket.send(json_data)
    recv_text = websocket.recv()

    console_log_imp.log('websocket_pending_watch_logic >> Subscribe return %s ' % (recv_text))

    while True:
        recv_text = websocket.recv()
        json_data = json.loads(recv_text)
        tx_info = json_data['params']['result']
        tx_hash = tx_info['hash']

        if not tx_info['to']:
            continue
        
        tx_input_pipe_object.put(tx_info)

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
        tqdm.write('%s%s -- %s%s' % (console_log.RED,time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(time.time()))),info,console_log.RESET))


if __name__  == '__main__':
    wallet_pk = os.getenv('pk')
    mevbot_address = os.getenv('mevbot')
    singer_pk = os.getenv('singer_pk')
    debug_in_goerli = int(os.getenv('debug_in_goerli',0))

    if not wallet_pk:
        print('No Wallet PK')
        exit()
    elif not mevbot_address:
        print('No MEV-Bot Address')
        exit()

    mempool_console_log_imp  = console_log(0,f"{console_log.GREEN}Mempool TX Processing Count{console_log.RESET}",f" {console_log.BLUE}TXObject{console_log.RESET}")
    miner_console_log_imp    = console_log(1,f"{console_log.GREEN}Miner TX Processing Count{console_log.RESET}",f" {console_log.BLUE}TXObject{console_log.RESET}")
    flashbot_console_log_imp = console_log(2,f"{console_log.GREEN}FlashBot State{console_log.RESET}",'')

    if debug_in_goerli:
        websocket_list = load_websocket_list('./websock_api_goerli.txt')
    else:
        websocket_list = load_websocket_list('./websock_api.txt')

    mempool_console_log_imp.log('Load All Websocket API %d' % len(websocket_list))

    if debug_in_goerli:
        remote_rpc_url = 'https://winter-necessary-county.ethereum-goerli.quiknode.pro//'
    else:
        remote_rpc_url = 'https://sparkling-quiet-mountain.quiknode.pro//'

    remote_web3 = rpc_api(remote_rpc_url)

    mevbot_address = local_web3.convert_address(mevbot_address)
    wallet_address = local_web3.get_wallet_address_from_private_key(wallet_pk)

    mempool_console_log_imp.log('Wallet Address: %s   ETH Balance:%0.5f | MevBot Address: %s   ETH Balance:%0.5f' % (
                wallet_address,
                remote_web3.get_wallet_balances(wallet_address) / 10 ** 18,
                mevbot_address,
                remote_web3.get_wallet_balances(mevbot_address) / 10 ** 18
            ))
    
    blocknumber_sync_imp  = blocknumber_sync()
    tx_input_pipe_object = queue.Queue()
    tx_output_pipe_object = queue.Queue()
    commit_to_block_tx_list = share_dict()
    mev_bot_imp = mev_bot.factory(remote_web3,mevbot_address,wallet_pk)
    flash_bot_imp = flash_bot.factory(remote_rpc_url,wallet_address,mev_bot_imp,singer_pk,flashbot_console_log_imp,commit_to_block_tx_list,blocknumber_sync_imp,debug_in_goerli)

    mempool_console_log_imp.log(flash_bot_imp.get_reputation())

    strategy_router_imp = strategy_router(ALL_SUPPORT_STRATEGY,remote_web3,tx_input_pipe_object,flash_bot_imp,mempool_console_log_imp)
    websocket_pending_watch_thread_imp = Thread(target=websocket_pending_watch_thread,args=(websocket_list,tx_input_pipe_object,mempool_console_log_imp))
    websocket_miner_watch_thread_imp = Thread(target=websocket_miner_watch_thread,args=(websocket_list,commit_to_block_tx_list,blocknumber_sync_imp,miner_console_log_imp))

    strategy_router_imp.start()
    websocket_pending_watch_thread_imp.start()
    websocket_miner_watch_thread_imp.start()

    websocket_pending_watch_thread_imp.join()
    websocket_miner_watch_thread_imp.join()
