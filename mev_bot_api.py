
import json
import os
import queue
import re
import sys
import time
import traceback
import uuid

from threading import Thread

from eth_account.account import Account

from flashbot_api import *
from match_logic import *
from web_rpc_api import *


#  调试选项
disable_flashbot_commit = int(os.getenv('disable_flashbot_commit',0))  #  关闭flashbot bundle交易发送
disable_flashbot_simulate = int(os.getenv('disable_flashbot_simulate',0))  #  关闭flashbot simulate交易模拟
debug_simulate_output = int(os.getenv('debug_simulate_output',0))  #  显示flashbot simulate的结果,用来调试bundle交易异常

class mev_bot:

    mev_bot_abi = [{"inputs":[],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[{"internalType":"uint256","name":"buyETHAmount","type":"uint256"},{"internalType":"uint256","name":"expectTokenAmount","type":"uint256"},{"internalType":"address","name":"buyTokenAddress","type":"address"}],"name":"ETHSwapToken","outputs":[{"internalType":"uint256","name":"getTokenAmount","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"sellTokenAmount","type":"uint256"},{"internalType":"uint256","name":"expectETHAmount","type":"uint256"},{"internalType":"address","name":"sellTokenAddress","type":"address"}],"name":"TokenSwapETH","outputs":[{"internalType":"uint256","name":"getETHAmount","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"UniswapV2Router","outputs":[{"internalType":"contract IUniswapV2Router02","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"WithdrawETH","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"address","name":"tokenAddress","type":"address"}],"name":"WithdrawToken","outputs":[],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]

    def __init__(self,web3_imp,mev_bot_address,mev_bot_imp,caller_wallet_pk):
        self.web3_imp = web3_imp
        self.mev_bot_address = self.web3_imp.convert_address(mev_bot_address)
        self.mev_bot_imp = mev_bot_imp
        self.caller_wallet_pk = caller_wallet_pk
        self.caller_wallet_address = web3_imp.get_wallet_address_from_private_key(caller_wallet_pk)

    @staticmethod
    def factory(web3_imp,mev_bot_address,caller_wallet_pk):
        mev_bot_imp = web3_imp.make_contract_object_by_address(mev_bot.mev_bot_abi,mev_bot_address)

        return mev_bot(web3_imp,mev_bot_address,mev_bot_imp,caller_wallet_pk)

    def ETHSwapToken(self,buyETHAmount,expectTokenAmount,buyTokenAddress,tx_nonce,tx_gasprice,for_builder):
        adjust_gas_price = tx_gasprice # + self.web3_imp.get_web3_object().toWei(2,'gwei')
        set_gas = 250000

        #  function ETHSwapToken(uint256 buyETHAmount,address buyTokenAddress) external returns (uint getTokenAmount)
        tx_object = self.mev_bot_imp.functions.ETHSwapToken(buyETHAmount,expectTokenAmount,buyTokenAddress).buildTransaction({
                'gas': set_gas,    #  Gas用Forge来测试
                'maxFeePerGas': int(adjust_gas_price),  #  多一个Gas抢先交易
                'maxPriorityFeePerGas': int(adjust_gas_price),
                'from': self.caller_wallet_address,
                'nonce': tx_nonce,
                'value': int(for_builder)
            })

        signed_tx_object = self.web3_imp.sign_transation_with_private_key(tx_object,self.caller_wallet_pk)
        raw_transaction_info = signed_tx_object.rawTransaction
        calcu_gas_price = adjust_gas_price * set_gas

        return raw_transaction_info,calcu_gas_price

    def TokenSwapETH(self,sellTokenAmount,expectETHAmount,sellTokenAddress,tx_nonce,tx_gasprice):
        adjust_gas_price = tx_gasprice + self.web3_imp.get_web3_object().toWei(2,'gwei')
        set_gas = 250000

        #  function TokenSwapETH(uint256 sellTokenAmount,address sellTokenAddress) external returns (uint getETHAmount)
        tx_object = self.mev_bot_imp.functions.TokenSwapETH(sellTokenAmount,expectETHAmount,sellTokenAddress).buildTransaction({
                'gas': set_gas,
                'maxFeePerGas': int(adjust_gas_price),
                'maxPriorityFeePerGas': int(adjust_gas_price),
                'from': self.caller_wallet_address,
                'nonce': tx_nonce,
                'value': int(tx_gasprice)
            })

        signed_tx_object = self.web3_imp.sign_transation_with_private_key(tx_object,self.caller_wallet_pk)
        raw_transaction_info = signed_tx_object.rawTransaction
        calcu_gas_price = adjust_gas_price * set_gas

        return raw_transaction_info,calcu_gas_price

    def WithdrawETH(self,amount,tx_nonce):
        gas_price = int(self.web3_imp.get_gas_price() * 1.1)
        tx_object = self.mev_bot_imp.functions.WithdrawETH(int(amount)).buildTransaction({
                'gasPrice': gas_price,
                'from': self.caller_wallet_address,
                'nonce': tx_nonce
            })
        tx_object['gas'] = self.web3_imp.get_estimate_gas(tx_object)

        signed_tx_object = self.web3_imp.sign_transation_with_private_key(tx_object,self.caller_wallet_pk)
        raw_transaction_info = signed_tx_object.rawTransaction

        return raw_transaction_info

    def WithdrawToken(self,token_address,amount,tx_nonce):
        gas_price = int(self.web3_imp.get_gas_price() * 1.1)
        tx_object = self.mev_bot_imp.functions.WithdrawToken(int(amount),token_address).buildTransaction({
                'gasPrice': gas_price,
                'from': self.caller_wallet_address,
                'nonce': tx_nonce
            })
        tx_object['gas'] = self.web3_imp.get_estimate_gas(tx_object)

        signed_tx_object = self.web3_imp.sign_transation_with_private_key(tx_object,self.caller_wallet_pk)
        raw_transaction_info = signed_tx_object.rawTransaction

        return raw_transaction_info



class flash_bundle:

    def __init__(self):
        self.bundle_list = []
        self.push_bundle_tx_to_blocknumber = 0

    def append_tx(self,tx_object):
        self.bundle_list.append(tx_object)

    def set_bundle_tx_commit_into_blocknumber(self,push_bundle_tx_to_blocknumber):
        self.push_bundle_tx_to_blocknumber = push_bundle_tx_to_blocknumber

    def get_bundle_tx_commit_into_blocknumber(self):
        return self.push_bundle_tx_to_blocknumber

    def build_bundle(self):
        result = []

        for tx_object in self.bundle_list:
            result.append({
                'signed_transaction': tx_object
            })

        return result

class flash_bot:

    #  Flashbot重要参考:
    #    https://blocks.flashbots.net/v1/blocks
    #    https://raw.githubusercontent.com/flashbots/flashbots-docs/8645f98f519e0e18747f65071cd16dc312beb3d3/docs/flashbots-auction/advanced/troubleshooting.mdx



    #  Bundle RPC 广播交易
    def bundle_send_thread(self,flashbot_bundle_rpc_url,flashbot_bundle_rpc_imp,bundle_object,current_blocknumber,target_mev_blocknumber,result_pipe):
        send_result = flashbot_bundle_rpc_imp.send_bundle(
            bundle_object,
            target_block_number = target_mev_blocknumber,
            opts={'replacementUuid': str(uuid.uuid4())},
        )
        
        #self.log('BN:%d FlashBotRPC[%s] - SendBundle Hash %s' % (current_blocknumber,flashbot_bundle_rpc_url,send_result.bundle_hash().hex()))

        try:
            receipts = send_result.receipts()
            result_pipe.put(True)
        except Exception as e:
            result_pipe.put(False)

    #  TX广播线程
    def tx_broadcast(self,flash_bundle_imp,strategy_command_imp,current_blocknumber,target_mev_blocknumber):
        tx_hash = strategy_command_imp.get_tx_hash()
        using_time = time.time() - strategy_command_imp.get_tx_find_timetick()
        self.log('Get Pending Bundle List. CurrentBlock=%d -> PushToBlock=%d TX %s [Using:%0.4f]' % (current_blocknumber,target_mev_blocknumber,tx_hash,using_time))

        bundle_object = flash_bundle_imp.build_bundle()
        
        if not disable_flashbot_simulate:
            try:
                simulate_result = self.web3_imp.get_web3_object().flashbots.simulate(bundle_object,block_tag = target_mev_blocknumber)
                
                using_time = time.time() - strategy_command_imp.get_tx_find_timetick()

                if debug_simulate_output:
                    self.log('BN:%d - Simulate Result:%s  [Using:%0.4f]' % (current_blocknumber,simulate_result,using_time))
            except Exception as e:  #  如果直接报错,有可能是nonce too low,这就意味着人家的tx已经上链了.此时websocket_miner_watch_thread就能捕获到tx
                exc_type, exc_value, exc_traceback = sys.exc_info()

                #try:  #  处理flashbot发交易的异常信息
                self.log('Except:%s' % (exc_value))
                #self.log('%s' % (type(exc_value)))
                rpc_exception_info = exc_value.args[0]
                rpc_exception_code = rpc_exception_info['code']
                rpc_exception_message = rpc_exception_info['message']
                self.log('RPC Fail %d = %s' % (rpc_exception_code,rpc_exception_message))
                
                if -32000 == rpc_exception_code:
                    if 'nonce too low' in rpc_exception_message:   #  被夹的tx已经上链了,nonce就不对
                        match = re.search(r'txhash\s+([0-9a-fA-FxX]+)', rpc_exception_message)
                        tx_hash_in_message = match.group(1)
                    elif 'max fee per gas less than block bas' in rpc_exception_message:   #  发送上链的Gas不够,这个原因是被夹的TX Gas太低造成的
                        match = re.search(r'address\s+([0-9a-fA-FxX]+)', rpc_exception_message)
                        fail_address = match.group(1)

                        if self.mev_caller_wallet_address == fail_address:   #  MEVBot发出去的TX Gas太低了,那就保留TX,调整Gas继续发
                            return
                        
                    elif 'insufficient funds for gas * price + value' in rpc_exception_message:   #  转账Gas不够,很有可能是异常的转账
                        #match = re.search(r'txhash\s+([0-9a-fA-FxX]+)', rpc_exception_message)
                        #tx_hash_in_message = match.group(1)
                        #pending_command_imp_list.pop(tx_hash_in_message)
                        #self.log('Gas Price %d' % ())
                        pass
                #except:
                #    pass
                
                #   有些发交易的命令需要确保上链,即使出了异常也要继续发
                if strategy_command_imp.get_still_buy():
                    self.tx_launchpad_thread_queue.put(strategy_command_imp)

                return
            
            using_time = time.time() - strategy_command_imp.get_tx_find_timetick()

            try:
                for simulate_result_tx in simulate_result['results']:
                    if 'error' in simulate_result_tx:  #  FlashBot执行出错,比如Gas不足或者合约调用失败(合约调用失败不会在合约buildTransation中报错的)
                        if 'revert' in simulate_result_tx:
                            self.warning('BN:%d - Simulate %s Execute Fail' % (current_blocknumber,simulate_result_tx['revert']))
                        else:
                            self.warning('BN:%d - Simulate Unknow Execute Fail => %s' % (current_blocknumber,simulate_result_tx))
                        
                        #   有些发交易的命令需要确保上链,即使出了异常也要继续发
                        if strategy_command_imp.get_still_buy():
                            self.tx_launchpad_thread_queue.put(strategy_command_imp)

                        return
            except:
                self.log('BN:%d - Simulate Result:%s  [Using:%0.4f]' % (current_blocknumber,simulate_result,using_time))

        #  发出交易
        if disable_flashbot_commit:  #  调试选项 - 不发出交易
            return

        pending_bundle_thread_list = []
        pending_bundle_thread_result_queue = queue.Queue()

        using_time = time.time() - strategy_command_imp.get_tx_find_timetick()
        self.log('BN:%d FlashBotRPC Broadcast MEV Tx-Hash %s  [Using:%0.4f]' % (current_blocknumber,tx_hash,using_time))

        for flashbot_bundle_rpc_url,flashbot_bundle_rpc_imp in self.flashbot_bundle_imp_list.items():
            thread_imp = Thread(target = self.bundle_send_thread,args = \
                                    (flashbot_bundle_rpc_url,flashbot_bundle_rpc_imp,bundle_object,current_blocknumber,target_mev_blocknumber,pending_bundle_thread_result_queue))
            thread_imp.daemon = True
            thread_imp.start()
            pending_bundle_thread_list.append(thread_imp)

        #  等待广播交易出结果
        for bundle_thread in pending_bundle_thread_list:
            bundle_thread.join()

        is_commit_mev_tx = False

        for _ in range(pending_bundle_thread_result_queue.qsize()):
            if pending_bundle_thread_result_queue.get():
                is_commit_mev_tx = True

        using_time = time.time() - strategy_command_imp.get_tx_find_timetick()

        if is_commit_mev_tx:
            self.log_success('BN:%d - FlashBot Commit Success --> MEV In %d  Profit ETH %0.4f  [Using:%0.4f]' % \
                        (current_blocknumber,target_mev_blocknumber,strategy_command_imp.get_profit_amount() / 10 ** 18,using_time))
            self.console_log_imp.tick_add()
        else:
            self.log('BN:%d - FlashBot Commit Fail TX: %s  [Using:%0.4f]' % (current_blocknumber,tx_hash,using_time))
            self.tx_launchpad_thread_queue.put(strategy_command_imp)

        #except:
        #    self.console_log_imp.log('Except! Info %s' % (traceback.format_exc()))

    #  TX发射线程
    def tx_launchpad(self):
        while True:
            #try:
            pending_command_imp_list = {
                # tx_hash: strategy_command_imp
            }
            
            strategy_command_imp = self.tx_launchpad_thread_queue.get()  #  经过策略分析之后,来了新的夹子命令
            tx_hash = strategy_command_imp.get_tx_hash()  #  要夹的那一笔TX

            self.log('Add New Pending Command %s -- tx_hash: %s' % (strategy_command_imp,tx_hash))
            
            commit_tx_blocknumber = self.commit_to_block_tx_list.get_key(tx_hash)

            if commit_tx_blocknumber:   #  过滤已经上链的TX
                self.log('<> Remove Commited TX %s [Commit BN:%d]' % (tx_hash,commit_tx_blocknumber))
                continue

            if not None == self.blocknumber_sync_imp:
                current_blocknumber = self.blocknumber_sync_imp.get_blocknumber()
            else:
                current_blocknumber = self.web3_imp.rpc_newest_block_number()

            target_mev_blocknumber = current_blocknumber + 1
            profit_amount = strategy_command_imp.get_profit_amount()

            #   先忽略下单指令合并调用MEV
            if strategy_command_imp.get_action() == strategy_command.BUY_TOKEN:
                flash_bundle_imp = flash_bundle()

                buyETHAmount = strategy_command_imp.get_amount_in()
                sellTokenAmount = strategy_command_imp.get_amount_out()

                #  Debug
                #buyETHAmount = 1000
                #sellTokenAmount = buyETHAmount

                buyTokenAddress = self.web3_imp.convert_address(strategy_command_imp.get_token())
                tx_nonce = self.web3_imp.get_nonce(self.mev_caller_wallet_address)
                #tx_gasprice = strategy_command_imp.get_gas_price()    #   被夹TX的GasPrice,注意这里不能这样用,是因为有可能这个Gas太低
                #  不能满足进入TX Pool的BaseFee门槛,所以就需要通过之前块的GasPrice计算操作发出去
                base_tx_price = self.web3_imp.get_gas_price() * 1.2      #   调整为直接读上一个链的GasPrice
                tx_rawtransation = strategy_command_imp.get_tx_rawtransation()
                self.log('Buy %0.4f ETH Token %s .BaseGasPrice %0.2f GWei' % (buyETHAmount / 10 ** 18,buyTokenAddress,base_tx_price / 10 ** 9))
                tx_raw_transation_buy,use_gas_buy = self.mev_bot_imp.ETHSwapToken(buyETHAmount,1,buyTokenAddress,tx_nonce,base_tx_price,base_tx_price) #  int(0.01 * 10 ** 18))
                tx_raw_transation_sell,use_gas_sell = self.mev_bot_imp.TokenSwapETH(sellTokenAmount,1,buyTokenAddress,tx_nonce + 1,base_tx_price * 3)
                total_tx_gas_using = use_gas_buy + use_gas_sell
                source_tx_gas_price = strategy_command_imp.get_gas_price() * strategy_command_imp.get_gas_limit()

                if total_tx_gas_using > profit_amount:  #  Gas成本高于利润
                    self.log('GasPrice > Profit %0.4f ETH -- TX: %s' % ((total_tx_gas_using - profit_amount) / 10 ** 18,tx_hash))
                    continue

                self.log('Calcu Earn %0.4f ETH (BundlePrice:%0.4f ETH)-- TX: %s' % ((profit_amount - total_tx_gas_using) / 10 ** 18,(source_tx_gas_price + total_tx_gas_using)/ 10 ** 18,tx_hash))

                flash_bundle_imp.append_tx(tx_raw_transation_buy)
                flash_bundle_imp.append_tx(tx_rawtransation)
                flash_bundle_imp.append_tx(tx_raw_transation_sell)

                flashbot_broadcast_thread_imp = Thread(target = self.tx_broadcast,args = (flash_bundle_imp,strategy_command_imp,current_blocknumber,target_mev_blocknumber))
                flashbot_broadcast_thread_imp.daemon = True
                flashbot_broadcast_thread_imp.start()
            elif strategy_command_imp.get_action() == strategy_command.SELL_TOKEN:
                pass
                
            #except:  #  并发起来的时候,RPC请求会很猛,节点返回了429
            #    time.sleep(0.001)
            #    continue


    def __init__(self,web3_rpc_url,mev_caller_wallet_address,mev_bot_imp,singer_pk,flashbot_rpc_list,flashbot_simulate_rpc,console_log_imp,blocknumber_sync_imp,commit_to_block_tx_list):
        self.web3_imp = rpc_api(web3_rpc_url)
        self.flashbot_simulate_imp = flashbot(self.web3_imp.get_web3_object(),singer_pk,flashbot_simulate_rpc)
        self.flashbot_bundle_imp_list = {}

        for flashbot_rpc_url in flashbot_rpc_list:
            console_log_imp.log('%s[FlashBot] Add Bundle RPC %s %s' % (console_log_imp.YELLOW,flashbot_rpc_url,console_log_imp.RESET))

            new_rpc_object = rpc_api(web3_rpc_url).get_web3_object()
            new_flashbot_provider = flashbot(new_rpc_object,singer_pk,flashbot_rpc_url)
            self.flashbot_bundle_imp_list[flashbot_rpc_url] = new_rpc_object.flashbots
        
        self.console_log_imp = console_log_imp
        self.mev_caller_wallet_address = mev_caller_wallet_address
        self.mev_bot_imp = mev_bot_imp
        self.commit_to_block_tx_list = commit_to_block_tx_list
        self.blocknumber_sync_imp = blocknumber_sync_imp
        self.tx_launchpad_thread_queue = queue.Queue()
        self.tx_launchpad_thread = Thread(target=flash_bot.tx_launchpad,args=(self,))
        self.tx_launchpad_thread.daemon = True
        self.tx_launchpad_thread.start()

    @staticmethod
    def factory(web3_rpc_url,mev_caller_wallet_address,mev_bot_imp,singer_pk,console_log_imp,commit_to_block_tx_list,blocknumber_sync_imp,is_testnet):
        if is_testnet:
            flashbot_bundle_rpc_list = ['https://relay-goerli.flashbots.net']
            flashbot_simulate_rpc = 'https://relay-goerli.flashbots.net'
        else:
            flashbot_rpc_list = [
                'https://relay.flashbots.net/',
                'https://rpc.beaverbuild.org/',
                'https://rsync-builder.xyz/',
                'https://builder0x69.io/',
                'https://rpc.titanbuilder.xyz/',
                'https://builder.gmbit.co/rpc',
                'https://rpc.jetbldr.xyz/',
            ]
            flashbot_simulate_rpc = 'https://relay.flashbots.net'

        singer_pk = Account.from_key(singer_pk)

        return flash_bot(web3_rpc_url,mev_caller_wallet_address,mev_bot_imp,singer_pk,flashbot_rpc_list,flashbot_simulate_rpc,console_log_imp,blocknumber_sync_imp,commit_to_block_tx_list)

    def add_mev_command_to_wait_list(self,flash_bundle_imp):
        self.tx_launchpad_thread_queue.put(flash_bundle_imp)

    def get_reputation(self):
        return self.web3_imp.get_web3_object().flashbots.getUserStatsV2()

    def log(self,info):
        self.console_log_imp.log('%s[FlashBot] %s %s' % (self.console_log_imp.YELLOW,info,self.console_log_imp.RESET))

    def warning(self,info):
        self.console_log_imp.warning('[FlashBot] %s' % (info))
        
    def log_success(self,info):
        self.console_log_imp.log('%s[FlashBot] %s %s' % (self.console_log_imp.GREEN,info,self.console_log_imp.RESET))

#  https://docs.flashbots.net/flashbots-auction/overview
#  https://docs.flashbots.net/flashbots-auction/advanced/troubleshooting
#  https://eips.ethereum.org/EIPS/eip-1559
#  https://hackmd.io/@flashbots/MEV-1559
#  https://github.com/jackqack/lido-mev/blob/main/src/send.ts


if __name__ == '__main__':
    import os
    from tqdm import tqdm

    from mempool import *
    from match_logic import *
    from web_rpc_api import *

    remote_rpc_url = 'https://burned-sly-dew.quiknode.pro//'
    remote_web3 = rpc_api(remote_rpc_url)

    wallet_pk = os.getenv('pk')
    mevbot_address = os.getenv('mevbot')
    singer_pk = os.getenv('singer_pk')

    wallet_address = local_web3.get_wallet_address_from_private_key(wallet_pk)
    wallet_nonce = remote_web3.get_nonce(wallet_address)
    mev_bot_imp = mev_bot.factory(remote_web3,mevbot_address,wallet_pk)
    
    flashbot_console_log_imp = console_log(0,f"{console_log.GREEN}FlashBot State{console_log.RESET}",'')

    flash_bot_imp = flash_bot.factory(remote_rpc_url,wallet_address,mev_bot_imp,singer_pk,flashbot_console_log_imp,share_dict(),None,False)

    while True:
        flash_bot_imp.add_mev_command_to_wait_list(
            strategy_command.factory(strategy_command.BUY_TOKEN,
                                            '',
                                            '0xbe6bE64e9E5042B6e84E4c27956cCE6353efa5f5',  
                                            #  '0xdAC17F958D2ee523a2206206994597C13D831ec7',
                                            int(3 * 10 ** 18),
                                            #  int(0.0001 * 10 ** 18),
                                            0,
                                            0,
                                            time.time()))
        time.sleep(1)

    input()
    exit()


    print(tx_raw)
    '''
    class console_log:
    
        def log(self,out):
            print(out)

    console_log_imp = console_log()
    fb = new_flash_bot(remote_web3,singer_pk,console_log_imp,True)

    flash_bundle_imp = flash_bundle.append_tx
    '''
    #tx_object_1 = remote_web3.make_tx_send_transation(wallet_address,mevbot_address,0.0001,wallet_nonce)
    #print(tx_object_1)
    #tx_object_1 = remote_web3.sign_transation_with_private_key(tx_object_1,wallet_pk)
    #tx_object_2 = remote_web3.make_tx_send_transation(wallet_address,mevbot_address,0.0002,wallet_nonce+1)
    #tx_object_2 = remote_web3.sign_transation_with_private_key(tx_object_2,wallet_pk)


    #exit()

    bundle = [
        #{"signed_transaction": tx_object_1.rawTransaction},
        #{"signed_transaction": tx_object_2.rawTransaction},

        {"signed_transaction": tx_raw}
    ]

    flashbot(remote_web3.web3_object, singer_pk, "https://relay-goerli.flashbots.net")
    while True:
        block = remote_web3.rpc_newest_block_number()
        gas_price = remote_web3.get_gas_price()
        print('BN->%d  %d' % (block,gas_price))
        a = remote_web3.web3_object.flashbots.simulate(bundle,block_tag = block)
        print('Simulate Result:%s' % (remote_web3.web3_object.flashbots.simulate(bundle,block_tag = block)))
        send_result = remote_web3.web3_object.flashbots.send_bundle(
            bundle,
            target_block_number=block + 1,
        )
        print( a['results'][0]['revert'])
        print("bundleHash",block,send_result.bundle_hash().hex())

        send_result.wait()
        try:
            receipts = send_result.receipts()
            print(f"\nBundle was mined in block {receipts[0].blockNumber}\a")
            break
        except:
            pass

    #{'blockHash': None, 'blockNumber': None, 'from': '0x407fde45cb6b7fcd5e8266ba434d9fc0c79277c2', 'gas': '0x61a80', 'gasPrice': '0x77359415', 'hash': '0x1eb7c610625d901153fe1cdf2f3fc39ab8a9c639debb2099af2270c7ca19b70c', 'input': '0xb6f9de9500000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000080000000000000000000000000407fde45cb6b7fcd5e8266ba434d9fc0c79277c200000000000000000000000000000000000000000000000000000000653b701d0000000000000000000000000000000000000000000000000000000000000002000000000000000000000000b4fbf271143f4fbf7b91a5ded31805e42b2208d6000000000000000000000000cffea2702035d93876d3edb33e695bc6db5cc926', 'nonce': '0xbb', 'to': '0x7a250d5630b4cf539739df2c5dacb4c659f2488d', 'transactionIndex': None, 'value': '0x470de4df820000', 'type': '0x0', 'chainId': '0x5', 'v': '0x2e', 'r': '0x3626d6b0ec975f9ad50600590247137e3042c146e270f8fefbb264efde7eeece', 's': '0x246f660c43e0b21b049e5ba8e7045a4567af434210903106f9027057524bebc2'}
