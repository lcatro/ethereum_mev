
import copy
import os
import queue
import time
import traceback

from decimal import Decimal
from threading import Thread,Lock


#  交易选项
MIN_MEV_ETH_AMOUNT = float(os.getenv('min_mev_eth_amount',0.0001)) * 10 ** 18    #  最小获利利润
MAX_MEV_ETH_AMOUNT = float(os.getenv('max_mev_eth_amount',0.0001)) * 10 ** 18    #  最大获利利润
DEBUG_STRATEGY_WATCH = os.getenv('debug_strategy_watch',0)
DEBUG_STRATEGY_LOG = os.getenv('debug_strategy_log',0)

NULL_ADDRESS = '0x0000000000000000000000000000000000000000'
ETH_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
WETH_ADDRESS = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
##WETH_ADDRESS = '0xB4FBF271143F4FBf7B91A5ded31805e42b2208d6'


def is_similar_address(a,b):
    if a.lower() == b.lower():
        return True
    
    return False

def check_min_mev_amount(eth_amount):
    if MIN_MEV_ETH_AMOUNT <= eth_amount:
        return True

    return False


class strategy_command:

    BUY_TOKEN = 1
    SELL_TOKEN = 2

    def __init__(self,action,tx_hash,token,amount_in,amount_out,profit_amount,find_timetick):
        self.action = action
        self.tx_hash = tx_hash
        self.token = token
        self.amount_in = amount_in
        self.amount_out = amount_out
        self.tx_rawtransation = None
        self.gas_price = 0
        self.gas_limit = 0
        self.profit_amount = profit_amount
        self.find_timetick = find_timetick
        self.still_buy = False    #   确保绝对买入

    @staticmethod
    def factory(action,tx_hash,token,amount_in,amount_out,profit_amount,find_timetick):
        return strategy_command(action,tx_hash,token,amount_in,amount_out,profit_amount,find_timetick)

    def get_action(self):
        return self.action

    def get_tx_hash(self):
        return self.tx_hash

    def get_token(self):
        return self.token

    def get_tx_find_timetick(self):
        return self.find_timetick

    def get_amount_in(self):
        return self.amount_in

    def get_amount_out(self):
        return self.amount_out

    def get_profit_amount(self):
        return self.profit_amount

    def set_gas_price(self,gas_price):
        self.gas_price = gas_price

    def get_gas_price(self):
        return self.gas_price

    def set_gas_limit(self,gas_limit):
        self.gas_limit = gas_limit

    def get_gas_limit(self):
        return self.gas_limit

    def set_still_buy(self,state):
        self.still_buy = state

    def get_still_buy(self):
        return self.still_buy

    def set_tx_rawtransation(self,tx_rawtransation):
        self.tx_rawtransation = tx_rawtransation

    def get_tx_rawtransation(self):
        return self.tx_rawtransation

    def __str__(self):
        if self.action == strategy_command.BUY_TOKEN:
            return 'BuyToken %s Using %0.6f ETH -> %d Token' % (self.token,self.amount_in / 10 ** 18,self.amount_out)
        elif self.action == strategy_command.SELL_TOKEN:
            return 'SellToken %s Using %d Token -> %0.6f ETH' % (self.token,self.amount_in,self.amount_out / 10 ** 18)
        
        return 'Except Command'


class strategy_router:

    def strategy_router_background_thread(self):
        all_sub_thread_list = []

        self.console_log_imp.log('[Strategy_Router] Global Setting => MIN_MEV_ETH_AMOUNT = %0.4f' % (MIN_MEV_ETH_AMOUNT))
        self.console_log_imp.log('[Strategy_Router] Global Setting => MAX_MEV_ETH_AMOUNT = %0.4f' % (MAX_MEV_ETH_AMOUNT))

        for strategy_model_class in self.register_strategy_list:
            sub_model_tx_input_pipe = queue.Queue()
            strategy_model_imp = strategy_model_class(self.web3_api_imp,sub_model_tx_input_pipe,self.flash_bot_imp,self.console_log_imp)

            strategy_model_imp.start()
            all_sub_thread_list.append((strategy_model_imp,sub_model_tx_input_pipe))

            self.console_log_imp.log('[Strategy_Router] Boot Strategy %s' % (strategy_model_imp.get_strategy_name()))

        self.console_log_imp.log('[Strategy_Router] All Ready Boot')

        while True:
            tx_object = self.tx_receiver_pipe.get()
            
            for strategy_model_imp,sub_model_tx_input_pipe in all_sub_thread_list:
                new_tx_object = copy.deepcopy(tx_object)
                new_tx_object['find_tick'] = time.time()
                sub_model_tx_input_pipe.put(new_tx_object)
                
            self.console_log_imp.tick_add()

    def __init__(self,register_strategy_list,web3_api_imp,tx_receiver_pipe,flash_bot_imp,console_log_imp):
        self.register_strategy_list = register_strategy_list
        self.web3_api_imp = web3_api_imp
        self.tx_receiver_pipe = tx_receiver_pipe
        self.flash_bot_imp = flash_bot_imp
        self.console_log_imp = console_log_imp
        self.thread_imp = None

    def start(self):
        self.thread_imp = Thread(target=strategy_router.strategy_router_background_thread,args=(self,))

        self.thread_imp.daemon = True
        self.thread_imp.start()


class strategy_base:

    NAME = '__BASE__'
    SUBSCRIPT_ADDRESS_LIST = []

    def strategy_base_background_thread(self):
        while True:
            tx_object = self.tx_input_pipe.get()

            try:
                start_time = time.time()
                from_address = tx_object['from']
                to_address = tx_object['to']

                for subscript_address in self.SUBSCRIPT_ADDRESS_LIST:
                    if not is_similar_address(to_address,subscript_address):
                        continue

                    #if DEBUG_STRATEGY_WATCH:
                    #    self.log('[DEBUG_STRATEGY_WATCH] Bingo %s ==> %s' % (from_address,subscript_address))

                    mev_command = self.match_entry(tx_object)

                    if not mev_command:
                        continue

                    #self.log('Debug TXObject=> %s' % (tx_object))
                    self.log('Debug Using Time => %f' % (time.time() - start_time))

                    if mev_command.BUY_TOKEN == mev_command.get_action():
                    #    #  必须要满足最低买入金额才操作
                        if MIN_MEV_ETH_AMOUNT > mev_command.get_amount_in():# or \
                    #        MAX_MEV_ETH_AMOUNT < mev_command.get_amount_in():
                            continue

                    if 'maxFeePerGas' in tx_object:
                        #  如果是EIP-1559 TX,会有maxFeePerGas,它的单位是wei
                        mev_command.set_gas_price(int(tx_object['maxFeePerGas'],16))
                    else:
                        #  如果是旧版TX,就只有GasPrice这个字段.GasPrice字段此时就是gwei的值
                        mev_command.set_gas_price(int(tx_object['gasPrice'],16) * 10 ** 9)

                    mev_command.set_gas_limit(int(tx_object['gas'],16))

                    v = int(tx_object.get('v'),16)
                    r = int(tx_object.get('r'),16)
                    s = int(tx_object.get('s'),16)
                    tx_rawtransation = self.web3_api_imp.tx_object_to_rawtransation(tx_object,v,r,s)
                    mev_command.set_tx_rawtransation(tx_rawtransation)
                    self.send_tx(mev_command)
            except:
                self.warning('Except! Info %s  |  TxObject %s' % (traceback.format_exc(),str(tx_object)))
            finally:
                del tx_object

    def __init__(self,web3_api_imp,tx_input_pipe,flash_bot_imp,console_log_imp):
        self.web3_api_imp = web3_api_imp
        self.tx_input_pipe = tx_input_pipe
        self.flash_bot_imp = flash_bot_imp
        self.console_log_imp = console_log_imp

        try:
            self.strategy_init()
        except:
            pass

    def start(self):
        thread_imp = Thread(target=strategy_base.strategy_base_background_thread,args=(self,))

        thread_imp.daemon = True
        thread_imp.start()

    def get_strategy_name(self):
        return self.NAME

    def strategy_init(self):
        pass

    def match_entry(self,tx_object):
        pass
    
    def send_tx(self,mev_command):
        self.flash_bot_imp.add_mev_command_to_wait_list(mev_command)

    def log(self,info):
        self.console_log_imp.log('[StrategyRouter] %s == %s' % (self.NAME,info))

    def highlight_log(self,info):
        self.console_log_imp.log('%s[StrategyRouter] %s == %s %s' % (self.console_log_imp.LIGHTBLUE,self.NAME,info,self.console_log_imp.RESET))

    def warning(self,info):
        self.console_log_imp.warning('[StrategyRouter] %s == %s' % (self.NAME,info))



class uniswap_v2_calculator:

    uniswap_v2_factory_abi = [{"inputs":[{"internalType":"address","name":"_feeToSetter","type":"address"}],"payable":False,"stateMutability":"nonpayable","type":"constructor"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"token0","type":"address"},{"indexed":True,"internalType":"address","name":"token1","type":"address"},{"indexed":False,"internalType":"address","name":"pair","type":"address"},{"indexed":False,"internalType":"uint256","name":"","type":"uint256"}],"name":"PairCreated","type":"event"},{"constant":True,"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"allPairs","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"allPairsLength","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"createPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"feeTo","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"feeToSetter","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"_feeTo","type":"address"}],"name":"setFeeTo","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"_feeToSetter","type":"address"}],"name":"setFeeToSetter","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"}]
    uniswap_v2_factory_address = '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'

    uniswap_v2_pair_abi = [{"inputs":[],"payable":False,"stateMutability":"nonpayable","type":"constructor"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"owner","type":"address"},{"indexed":True,"internalType":"address","name":"spender","type":"address"},{"indexed":False,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"sender","type":"address"},{"indexed":False,"internalType":"uint256","name":"amount0","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"amount1","type":"uint256"},{"indexed":True,"internalType":"address","name":"to","type":"address"}],"name":"Burn","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"sender","type":"address"},{"indexed":False,"internalType":"uint256","name":"amount0","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"amount1","type":"uint256"}],"name":"Mint","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"sender","type":"address"},{"indexed":False,"internalType":"uint256","name":"amount0In","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"amount1In","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"amount0Out","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"amount1Out","type":"uint256"},{"indexed":True,"internalType":"address","name":"to","type":"address"}],"name":"Swap","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"uint112","name":"reserve0","type":"uint112"},{"indexed":False,"internalType":"uint112","name":"reserve1","type":"uint112"}],"name":"Sync","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"from","type":"address"},{"indexed":True,"internalType":"address","name":"to","type":"address"},{"indexed":False,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":True,"inputs":[],"name":"DOMAIN_SEPARATOR","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"MINIMUM_LIQUIDITY","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"PERMIT_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"to","type":"address"}],"name":"burn","outputs":[{"internalType":"uint256","name":"amount0","type":"uint256"},{"internalType":"uint256","name":"amount1","type":"uint256"}],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"factory","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"_token0","type":"address"},{"internalType":"address","name":"_token1","type":"address"}],"name":"initialize","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"kLast","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"to","type":"address"}],"name":"mint","outputs":[{"internalType":"uint256","name":"liquidity","type":"uint256"}],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"nonces","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"permit","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"price0CumulativeLast","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"price1CumulativeLast","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"to","type":"address"}],"name":"skim","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"internalType":"uint256","name":"amount0Out","type":"uint256"},{"internalType":"uint256","name":"amount1Out","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"bytes","name":"data","type":"bytes"}],"name":"swap","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[],"name":"sync","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"internalType":"address","name":"from","type":"address"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"}],"name":"transferFrom","outputs":[{"internalType":"bool","name":"","type":"bool"}],"payable":False,"stateMutability":"nonpayable","type":"function"}]


    def __init__(self,web3_imp):
        self.web3_imp = web3_imp
        self.uniswap_v2_factory_imp = web3_imp.make_contract_object_by_address(
                                            uniswap_v2_calculator.uniswap_v2_factory_abi,
                                            uniswap_v2_calculator.uniswap_v2_factory_address
                                        )
        self.uniswap_v2_pair_cache = {}
        self.thread_lock = Lock()
        self.test_reserve_a = 0
        self.test_reserve_b = 0

    @staticmethod
    def factory(web3_imp):
        return uniswap_v2_calculator(web3_imp)

    def get_pair(self,token_in,token_out):
        token_in_number = int(token_in,16)
        token_out_number = int(token_out,16)
        token_in = self.web3_imp.convert_address(token_in)
        token_out = self.web3_imp.convert_address(token_out)

        if token_in_number < token_out_number:
            hash_code = token_in + token_out
        else:
            hash_code = token_out + token_in

        self.thread_lock.acquire()

        if hash_code in self.uniswap_v2_pair_cache:
            pair_address = self.uniswap_v2_pair_cache[hash_code]
        else:
            pair_address = self.uniswap_v2_factory_imp.functions.getPair(token_in,token_out).call()
            self.uniswap_v2_pair_cache[hash_code] = pair_address

        self.thread_lock.release()

        return pair_address

    def set_test_reserve(self,token_a,token_b,reserve_a,reserve_b):
        address_a_number = Decimal(int(token_a,16))
        address_b_number = Decimal(int(token_b,16))

        if address_a_number < address_b_number:
            self.test_reserve_a = reserve_a
            self.test_reserve_b = reserve_b
        else:
            self.test_reserve_a = reserve_b
            self.test_reserve_b = reserve_a

    def calcu_getAmountOut(self,reserve_In,reserve_Out,input_amount):
        return ((input_amount * 997) * reserve_In) / (reserve_Out * 1000 + (input_amount * 997))

    def eth_buy_token_calculate_eth_profit_with_expect_min_token(self,
            weth_address,
            token_address,
            in_eth_amount,     #  被夹TX输入ETH
            token_min_amount,  #  被夹TX预计换出的最少Token
        ):
        weth_address_number = Decimal(int(weth_address,16))
        token_address_number = Decimal(int(token_address,16))
        pair_address = self.get_pair(weth_address,token_address)

        if is_similar_address(pair_address,NULL_ADDRESS):
            return 0,0,0

        pair_imp = self.web3_imp.make_contract_object_by_address(uniswap_v2_calculator.uniswap_v2_pair_abi,pair_address)

        if self.test_reserve_a or self.test_reserve_b:
            reserve_a,reserve_b = (self.test_reserve_a,self.test_reserve_b)
        else:
            reserve_a,reserve_b,_ = pair_imp.functions.getReserves().call()

        in_eth_amount = Decimal(in_eth_amount)
        token_min_amount = Decimal(token_min_amount)

        if 0 == token_min_amount:   #   有些情况是0
            token_min_amount = Decimal(1)

        if weth_address_number < token_address_number:
            reserve_ETH = reserve_a
            reserve_Token = reserve_b
        else:
            reserve_ETH = reserve_b
            reserve_Token = reserve_a

        step_eth_amount = Decimal(1.0 * 10 ** 18)   #  初始每次逼近模拟增加1 ETH
        minimum_accuracy = Decimal(0.001 * 10 ** 18)
        mev_bot_buy_eth = step_eth_amount
        last_mev_bot_get_token_amount = 0
        last_mev_bot_eth_profit = 0
        '''
        normal_output_token = int(self.calcu_getAmountOut(reserve_Token,reserve_ETH,in_eth_amount))
        try:
            slippage_rate = token_min_amount / normal_output_token
            #  decimal.DivisionByZero: [<class 'decimal.DivisionByZero'>]   不知道为什么
        except:
            return 0,0,0

        if slippage_rate < 0.09:  #  为什么不是0.1,是因为有计算误差
            #  对于delta_Token非常小的值,其实就是滑点非常大的情况
            #  这个时候去逼近最值是没有意义的,因为会死循环,所以只搞定90%滑点以下的所有交易
            return 0,0,0
        '''

        while step_eth_amount >= minimum_accuracy:  #  逼近的最小精度为0.001 ETH
            emulate_reserve_Token = reserve_Token
            emulate_reserve_ETH = reserve_ETH
            
            #  计算MEV顶上去之后的池子reserve值
            mev_bot_get_token_amount = int(self.calcu_getAmountOut(emulate_reserve_Token,emulate_reserve_ETH,mev_bot_buy_eth))
            emulate_reserve_Token -= mev_bot_get_token_amount
            emulate_reserve_ETH += mev_bot_buy_eth

            #  计算被夹用户正常被顶之后可以兑换出来的Token数量
            normal_tx_token_output = int(self.calcu_getAmountOut(emulate_reserve_Token,emulate_reserve_ETH,in_eth_amount))

            #  计算最终MEV利润率
            emulate_reserve_Token -= normal_tx_token_output
            emulate_reserve_ETH += in_eth_amount
            eth_profit = self.calcu_getAmountOut(emulate_reserve_ETH,emulate_reserve_Token,mev_bot_get_token_amount) - mev_bot_buy_eth

            if normal_tx_token_output > token_min_amount:  #  如果兑换出来的Token值多于正常交易预期输出Token,那就继续逼近
                mev_bot_buy_eth += step_eth_amount
                last_mev_bot_get_token_amount = mev_bot_get_token_amount
                last_mev_bot_eth_profit = eth_profit
            else:  #  如果兑换出来的Token小于正常交易的期望值
                mev_bot_buy_eth -= step_eth_amount  #  回退这次自增,下降一个数量级继续来
                step_eth_amount = step_eth_amount / 10  #  接下来逼近模拟的精度减小1/10

                if mev_bot_buy_eth <= 0:
                    mev_bot_buy_eth = step_eth_amount

                continue
        
        return int(last_mev_bot_get_token_amount),int(mev_bot_buy_eth),int(last_mev_bot_eth_profit)


class strategy_uniswap_v2_router(strategy_base):

    NAME = 'UniswapV2Router'

    uniswap_v2_router_abi = [{"inputs":[{"internalType":"address","name":"_factory","type":"address"},{"internalType":"address","name":"_WETH","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"WETH","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"amountADesired","type":"uint256"},{"internalType":"uint256","name":"amountBDesired","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amountTokenDesired","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"factory","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountIn","outputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountOut","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsIn","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"reserveA","type":"uint256"},{"internalType":"uint256","name":"reserveB","type":"uint256"}],"name":"quote","outputs":[{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETHSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermit","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermitSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityWithPermit","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapETHForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]
    uniswap_v2_router_address = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'

    SUBSCRIPT_ADDRESS_LIST = [ uniswap_v2_router_address ]

    def strategy_init(self):
        self.uniswap_v2_router_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                            strategy_uniswap_v2_router.uniswap_v2_router_abi,
                                            strategy_uniswap_v2_router.uniswap_v2_router_address
                                            )
        self.uniswap_v2_calculator_imp = uniswap_v2_calculator.factory(self.web3_api_imp)

    def uniswap_getAmountsOut(self,token_path,amount_in):
        return self.uniswap_v2_router_abi_imp.functions.getAmountsOut(amount_in,token_path).call()
        
    def uniswap_getAmountsIn(self,token_path,amount_out):
        return self.uniswap_v2_router_abi_imp.functions.getAmountsIn(amount_out,token_path).call()
        
    def match_entry(self,tx_object):
        tx_hash = tx_object['hash']
        from_address = tx_object['from']
        eth_value = int(tx_object.get('value',0),16)
        
        try:
            function_object,function_argments = self.uniswap_v2_router_abi_imp.decode_function_input(tx_object['input'])    #   这里有概率会找不到函数,不知道为什么
            function_name = function_object.fn_name
        except:
            return False

        ##  只尝试搞定买入
        if 'swapETHForExactTokens' == function_name:   #  常规买入
            amount_in = eth_value
            amount_out = function_argments['amountOut']
            swap_path = function_argments['path']
            
            if swap_path[0] == swap_path[-1]:
                return False
            elif not 2 == len(swap_path):
                return False

            token_address = swap_path[-1]
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,token_address,amount_in,amount_out)

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('swapETHForExactTokens | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | TXHash: %s' % (
                        from_address,
                        amount_in / 10 ** 18,
                        amount_out,
                        token_address,
                        acquisition_cost_eth_amount / 10 ** 18,
                        (profit_eth_amount) / 10 ** 18,
                        tx_hash,
                    ))

                return strategy_command.factory(strategy_command.BUY_TOKEN,
                                                tx_hash,
                                                token_address,
                                                acquisition_cost_eth_amount,
                                                delta_token_amount_with_fee,
                                                profit_eth_amount,
                                                tx_object['find_tick'])
        elif 'swapExactETHForTokensSupportingFeeOnTransferTokens' == function_name:    #   收税Token
            amount_in = eth_value
            amount_out = function_argments['amountOutMin']
            swap_path = function_argments['path']

            if swap_path[0] == swap_path[-1]:
                return False
            elif not 2 == len(swap_path):
                return False

            #  收税Token要非常小心,因为Token合约是会扣代币,但是reserve模拟是不知道Token会不会扣

            token_address = swap_path[-1]
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,token_address,amount_in,amount_out)

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('swapExactETHForTokensSupportingFeeOnTransferTokens | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | TXHash: %s' % (
                        from_address,
                        amount_in / 10 ** 18,
                        amount_out,
                        token_address,
                        acquisition_cost_eth_amount / 10 ** 18,
                        (profit_eth_amount) / 10 ** 18,
                        tx_hash,
                    ))
            else:
                return False
                
            return strategy_command.factory(strategy_command.BUY_TOKEN,
                                            tx_hash,
                                            token_address,
                                            acquisition_cost_eth_amount,
                                            delta_token_amount_with_fee,
                                            profit_eth_amount,
                                            tx_object['find_tick'])
        ##  swapTokensForExactTokens 这个也是买入,前提是你没有办法判断token和token之间的swap是买还是卖,只能判断是否是WETH去换Token
        elif 'swapTokensForExactTokens' == function_name:    #   Token换Token
            swap_path_input_token = function_argments['path'][0]
            swap_path_out_token = function_argments['path'][-1]

            if not is_similar_address(WETH_ADDRESS,swap_path_input_token):
                return False
            
            amount_in = function_argments['amountInMax']
            amount_out = function_argments['amountOut']
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,swap_path_out_token,amount_in,amount_out)

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('swapTokensForExactTokens | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | △Token = %d | TXHash: %s' % (
                            from_address,
                            eth_value / 10 ** 18,
                            amount_out,
                            function_argments['path'][1:],
                            (acquisition_cost_eth_amount) / 10 ** 18,
                            (profit_eth_amount) / 10 ** 18,
                            delta_token_amount_with_fee,
                            tx_hash
                        ))
                
                return strategy_command.factory(strategy_command.BUY_TOKEN,
                                                tx_hash,swap_path_out_token,
                                                acquisition_cost_eth_amount,
                                                delta_token_amount_with_fee,
                                                profit_eth_amount,
                                                tx_object['find_tick'])
        else:
            return False

        return False


class strategy_uniswap_v3_router(strategy_base):

    NAME = 'UniswapV3Router'

    uniswap_v3_router_abi = [{"inputs":[{"internalType":"address","name":"_factory","type":"address"},{"internalType":"address","name":"_WETH9","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"WETH9","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"components":[{"internalType":"bytes","name":"path","type":"bytes"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMinimum","type":"uint256"}],"internalType":"struct ISwapRouter.ExactInputParams","name":"params","type":"tuple"}],"name":"exactInput","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMinimum","type":"uint256"},{"internalType":"uint160","name":"sqrtPriceLimitX96","type":"uint160"}],"internalType":"struct ISwapRouter.ExactInputSingleParams","name":"params","type":"tuple"}],"name":"exactInputSingle","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"bytes","name":"path","type":"bytes"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMaximum","type":"uint256"}],"internalType":"struct ISwapRouter.ExactOutputParams","name":"params","type":"tuple"}],"name":"exactOutput","outputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMaximum","type":"uint256"},{"internalType":"uint160","name":"sqrtPriceLimitX96","type":"uint160"}],"internalType":"struct ISwapRouter.ExactOutputSingleParams","name":"params","type":"tuple"}],"name":"exactOutputSingle","outputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"factory","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes[]","name":"data","type":"bytes[]"}],"name":"multicall","outputs":[{"internalType":"bytes[]","name":"results","type":"bytes[]"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"refundETH","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"selfPermit","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"nonce","type":"uint256"},{"internalType":"uint256","name":"expiry","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"selfPermitAllowed","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"nonce","type":"uint256"},{"internalType":"uint256","name":"expiry","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"selfPermitAllowedIfNecessary","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"selfPermitIfNecessary","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amountMinimum","type":"uint256"},{"internalType":"address","name":"recipient","type":"address"}],"name":"sweepToken","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amountMinimum","type":"uint256"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"feeBips","type":"uint256"},{"internalType":"address","name":"feeRecipient","type":"address"}],"name":"sweepTokenWithFee","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"int256","name":"amount0Delta","type":"int256"},{"internalType":"int256","name":"amount1Delta","type":"int256"},{"internalType":"bytes","name":"_data","type":"bytes"}],"name":"uniswapV3SwapCallback","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountMinimum","type":"uint256"},{"internalType":"address","name":"recipient","type":"address"}],"name":"unwrapWETH9","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountMinimum","type":"uint256"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"feeBips","type":"uint256"},{"internalType":"address","name":"feeRecipient","type":"address"}],"name":"unwrapWETH9WithFee","outputs":[],"stateMutability":"payable","type":"function"},{"stateMutability":"payable","type":"receive"}]
    uniswap_v3_router_address = '0xE592427A0AEce92De3Edee1F18E0157C05861564'

    SUBSCRIPT_ADDRESS_LIST = [ uniswap_v3_router_address ]

    def strategy_init(self):
        self.uniswap_v3_router_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                            strategy_uniswap_v3_router.uniswap_v3_router_abi,
                                            strategy_uniswap_v3_router.uniswap_v3_router_address
                                            )

    def match_entry(self,tx_object):
        to_address = tx_object['to']

        try:
            #self.console_log_imp.log('strategy_uniswap_v3_router  %s' % (self.uniswap_v3_router_abi_imp.decode_function_input(tx_object['input'])))
            pass
        except:
            pass

        return False


class strategy_uniswap_universal_router(strategy_base):

    NAME = 'UniswapUniversalRouter'

    uniswap_v2_router_abi = [{"inputs":[{"internalType":"address","name":"_factory","type":"address"},{"internalType":"address","name":"_WETH","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"WETH","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"amountADesired","type":"uint256"},{"internalType":"uint256","name":"amountBDesired","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amountTokenDesired","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"factory","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountIn","outputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountOut","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsIn","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"reserveA","type":"uint256"},{"internalType":"uint256","name":"reserveB","type":"uint256"}],"name":"quote","outputs":[{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETHSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermit","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermitSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityWithPermit","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapETHForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]
    uniswap_v2_router_address = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    uniswap_universal_router_abi = [{"inputs":[{"components":[{"internalType":"address","name":"permit2","type":"address"},{"internalType":"address","name":"weth9","type":"address"},{"internalType":"address","name":"seaport","type":"address"},{"internalType":"address","name":"nftxZap","type":"address"},{"internalType":"address","name":"x2y2","type":"address"},{"internalType":"address","name":"foundation","type":"address"},{"internalType":"address","name":"sudoswap","type":"address"},{"internalType":"address","name":"nft20Zap","type":"address"},{"internalType":"address","name":"cryptopunks","type":"address"},{"internalType":"address","name":"looksRare","type":"address"},{"internalType":"address","name":"routerRewardsDistributor","type":"address"},{"internalType":"address","name":"looksRareRewardsDistributor","type":"address"},{"internalType":"address","name":"looksRareToken","type":"address"},{"internalType":"address","name":"v2Factory","type":"address"},{"internalType":"address","name":"v3Factory","type":"address"},{"internalType":"bytes32","name":"pairInitCodeHash","type":"bytes32"},{"internalType":"bytes32","name":"poolInitCodeHash","type":"bytes32"}],"internalType":"struct RouterParameters","name":"params","type":"tuple"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"ContractLocked","type":"error"},{"inputs":[],"name":"ETHNotAccepted","type":"error"},{"inputs":[{"internalType":"uint256","name":"commandIndex","type":"uint256"},{"internalType":"bytes","name":"message","type":"bytes"}],"name":"ExecutionFailed","type":"error"},{"inputs":[],"name":"FromAddressIsNotOwner","type":"error"},{"inputs":[],"name":"InsufficientETH","type":"error"},{"inputs":[],"name":"InsufficientToken","type":"error"},{"inputs":[],"name":"InvalidBips","type":"error"},{"inputs":[{"internalType":"uint256","name":"commandType","type":"uint256"}],"name":"InvalidCommandType","type":"error"},{"inputs":[],"name":"InvalidOwnerERC1155","type":"error"},{"inputs":[],"name":"InvalidOwnerERC721","type":"error"},{"inputs":[],"name":"InvalidPath","type":"error"},{"inputs":[],"name":"InvalidReserves","type":"error"},{"inputs":[],"name":"LengthMismatch","type":"error"},{"inputs":[],"name":"NoSlice","type":"error"},{"inputs":[],"name":"SliceOutOfBounds","type":"error"},{"inputs":[],"name":"SliceOverflow","type":"error"},{"inputs":[],"name":"ToAddressOutOfBounds","type":"error"},{"inputs":[],"name":"ToAddressOverflow","type":"error"},{"inputs":[],"name":"ToUint24OutOfBounds","type":"error"},{"inputs":[],"name":"ToUint24Overflow","type":"error"},{"inputs":[],"name":"TransactionDeadlinePassed","type":"error"},{"inputs":[],"name":"UnableToClaim","type":"error"},{"inputs":[],"name":"UnsafeCast","type":"error"},{"inputs":[],"name":"V2InvalidPath","type":"error"},{"inputs":[],"name":"V2TooLittleReceived","type":"error"},{"inputs":[],"name":"V2TooMuchRequested","type":"error"},{"inputs":[],"name":"V3InvalidAmountOut","type":"error"},{"inputs":[],"name":"V3InvalidCaller","type":"error"},{"inputs":[],"name":"V3InvalidSwap","type":"error"},{"inputs":[],"name":"V3TooLittleReceived","type":"error"},{"inputs":[],"name":"V3TooMuchRequested","type":"error"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"RewardsSent","type":"event"},{"inputs":[{"internalType":"bytes","name":"looksRareClaim","type":"bytes"}],"name":"collectRewards","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes","name":"commands","type":"bytes"},{"internalType":"bytes[]","name":"inputs","type":"bytes[]"}],"name":"execute","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"bytes","name":"commands","type":"bytes"},{"internalType":"bytes[]","name":"inputs","type":"bytes[]"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"execute","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"},{"internalType":"uint256[]","name":"","type":"uint256[]"},{"internalType":"uint256[]","name":"","type":"uint256[]"},{"internalType":"bytes","name":"","type":"bytes"}],"name":"onERC1155BatchReceived","outputs":[{"internalType":"bytes4","name":"","type":"bytes4"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"},{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"bytes","name":"","type":"bytes"}],"name":"onERC1155Received","outputs":[{"internalType":"bytes4","name":"","type":"bytes4"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"},{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"bytes","name":"","type":"bytes"}],"name":"onERC721Received","outputs":[{"internalType":"bytes4","name":"","type":"bytes4"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"bytes4","name":"interfaceId","type":"bytes4"}],"name":"supportsInterface","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"int256","name":"amount0Delta","type":"int256"},{"internalType":"int256","name":"amount1Delta","type":"int256"},{"internalType":"bytes","name":"data","type":"bytes"}],"name":"uniswapV3SwapCallback","outputs":[],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]
    uniswap_universal_router_address = '0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD'

    SUBSCRIPT_ADDRESS_LIST = [ uniswap_universal_router_address ]

    def strategy_init(self):
        self.uniswap_universal_router_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                            strategy_uniswap_universal_router.uniswap_universal_router_abi,
                                            strategy_uniswap_universal_router.uniswap_universal_router_address
                                            )
        self.uniswap_v2_router_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                            strategy_uniswap_universal_router.uniswap_v2_router_abi,
                                            strategy_uniswap_universal_router.uniswap_v2_router_address
                                            )
        self.uniswap_v2_calculator_imp = uniswap_v2_calculator.factory(self.web3_api_imp)

    def uniswap_v2_getAmountsOut(self,token_path,amount_in):
        token_path_temp = []

        for address in token_path:
            token_path_temp.append(self.web3_api_imp.convert_address(address))

        return self.uniswap_v2_router_abi_imp.functions.getAmountsOut(amount_in,token_path_temp).call()
        
    def uniswap_v2_getAmountsIn(self,token_path,amount_out):
        token_path_temp = []

        for address in token_path:
            token_path_temp.append(self.web3_api_imp.convert_address(address))

        return self.uniswap_v2_router_abi_imp.functions.getAmountsIn(amount_out,token_path_temp).call()
        
    def action_parse(self,tx_object,action_commands,action_input):
        tx_hash = tx_object['hash']
        from_address = tx_object['from']

        V3_SWAP_EXACT_IN = 0x00
        V3_SWAP_EXACT_OUT = 0x01
        V2_SWAP_EXACT_IN = 0x08
        V2_SWAP_EXACT_OUT = 0x09

        #self.log('%s %s' % (action_commands,action_input))

        #  注意,实际解码的逻辑是和合约给出来的代码是不一样的,不知道为什么会这样....
        if action_commands == V3_SWAP_EXACT_IN:
            recipient,amountIn,amountOutMin,path,payerIsUser = self.web3_api_imp.decode_abi_encode(['address','uint256','uint256','bytes','bool'],action_input)

            if DEBUG_STRATEGY_LOG:
                self.log('V3_SWAP_EXACT_IN %s %d %d %s' % (recipient,amountIn,amountOutMin,payerIsUser))
        elif action_commands == V3_SWAP_EXACT_OUT:
            recipient,amountOut,amountInMax,path,payerIsUser = self.web3_api_imp.decode_abi_encode(['address','uint256','uint256','bytes','bool'],action_input)

            if DEBUG_STRATEGY_LOG:
                self.log('V3_SWAP_EXACT_OUT %s %d %d %s' % (recipient,amountOut,amountInMax,payerIsUser))
        elif action_commands == V2_SWAP_EXACT_IN:
            _,amountIn,amountOutMin,swap_path = self.web3_api_imp.decode_abi_encode(['int','uint256','uint256','address[]'],action_input)

            if swap_path[0] == swap_path[-1]:   #  进出都是同一个币就说明这个是套利哥,可以夹他一下
                return False
            elif not 2 == len(swap_path):   #  多交易对兑换就先不管了
                return False

            if swap_path[0] == WETH_ADDRESS:   #  买入
                token_address = swap_path[-1]

                delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                    self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,token_address,amountIn,amountOutMin)

                if DEBUG_STRATEGY_LOG:
                    self.log('V2_SWAP_EXACT_IN %d %d PATH: %s Profit: %0.4f' % (amountIn,amountOutMin,swap_path,profit_eth_amount / 10 ** 18))

                if check_min_mev_amount(profit_eth_amount):
                    self.highlight_log('V2_SWAP_EXACT_IN | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | TXHash: %s' % (
                            from_address,
                            amountIn / 10 ** 18,
                            amountOutMin,
                            token_address,
                            acquisition_cost_eth_amount / 10 ** 18,
                            (profit_eth_amount) / 10 ** 18,
                            tx_hash,
                        ))

                    return strategy_command.factory(strategy_command.BUY_TOKEN,
                                                    tx_hash,
                                                    token_address,
                                                    acquisition_cost_eth_amount,
                                                    delta_token_amount_with_fee,
                                                    profit_eth_amount,
                                                    tx_object['find_tick'])
            elif swap_path[-1] == WETH_ADDRESS:   #  卖出
                pass
            else:  #  币换币,没有意义
                pass

        elif action_commands == V2_SWAP_EXACT_OUT:
            _,amountOut,amountInMax,swap_path = self.web3_api_imp.decode_abi_encode(['int','uint256','uint256','address[]'],action_input)

            #self.log('V2_SWAP_EXACT_OUT %d %d %s' % (amountOut,amountInMax,swap_path))
            #  后续优化
            '''
            if swap_path[0] == swap_path[-1]:   #  进出都是同一个币就说明这个是套利哥
                return False
            elif not 2 == len(swap_path):   #  多交易对兑换就先不管了
                return False

            if swap_path[0] == WETH_ADDRESS:   #  买入
                current_amount_out = self.uniswap_v2_getAmountsOut(swap_path,amountInMax)   #  计算最大输入amountInMax个ETH的期望换出代币有多少
                mev_token_amount = amountOut - current_amount_out[0]   #  期望的输出代币-amountOut就是可以套利多少代币的空间

                if mev_token_amount > 0:
                    token_amount_in_list = self.uniswap_v2_getAmountsIn(swap_path,mev_token_amount)
                    mev_eth_amount = token_amount_in_list[1]   #  用可套利数量的Token去计算就可以得出可以买入WETH空间

                    self.highlight_log('V2_SWAP_EXACT_OUT | %s Take %0.4f WETH Swap %0.4f Token %s | △AmountIn = %0.4f ETH  △Token = %d | TXHash: %s' % (
                            from_address,
                            amountInMax / 10 ** 18,
                            amountOut,
                            swap_path[1:],
                            (mev_eth_amount) / 10 ** 18,
                            mev_token_amount,
                            tx_hash,
                        ))
                        
                    return strategy_command.factory(strategy_command.BUY_TOKEN,tx_hash,swap_path[-1],mev_eth_amount,mev_token_amount,tx_object['find_tick'])
            elif swap_path[-1] == WETH_ADDRESS:   #  卖出
                pass
            else:  #  币换币,没有意义
                pass
            '''

        return False

    def match_entry(self,tx_object):
        try:
            function_object,function_argments = self.uniswap_universal_router_abi_imp.decode_function_input(tx_object['input'])    #   这里有概率会找不到函数,不知道为什么
            function_name = function_object.fn_name
        except:
            return False

        if 'execute' == function_name:
            if len(function_argments) > 3:
                return False

            #  function execute(bytes calldata commands, bytes[] calldata inputs) public payable override
            action_commands = function_argments['commands']
            action_inputs = function_argments['inputs']
            deadline = 0x0
            
            if not len(action_commands) == len(action_inputs):
                return False

            if len(function_argments) == 3:  #  function execute(bytes calldata commands, bytes[] calldata inputs, uint256 deadline) external payable
                deadline = function_argments['deadline']
            
            if len(action_commands) > 2:  #  因为有一些比较复杂的交换命令就先不考虑了,只做一个先
                return False

            #  0x08    =>  UniswapV2买入
            #  0x0b08  =>  添加WETH+V2买入
            if not action_commands in [b'\x0b\x08',b'\x08']:
                return False

            for action_index in range(len(action_inputs)):
                mev_command = self.action_parse(tx_object,action_commands[action_index],action_inputs[action_index].hex())
                #  Universal Router里面可以插入多笔交易,目前就只要一笔

                if mev_command:
                    return mev_command

        return False

#  0x: Exchange Proxy
#      https://etherscan.io/tx/0x1c9241c6bc11d9f6105b0ff20b58e80eaa03919c211fc2e2ae2408cffe5fc3ab

class strategy_0xExchangeProxy_router(strategy_base):

    NAME = '0xExchangeProxyRouter'

    #  ABI出处https://etherscan.io/address/0xf9b30557afcf76ea82c04015d80057fa2147dfa9#code
    xechange_proxy_router_abi = [{"inputs":[{"internalType":"contract IEtherTokenV06","name":"weth","type":"address"},{"internalType":"contract IAllowanceTarget","name":"allowanceTarget","type":"address"},{"internalType":"bytes32","name":"greedyTokensBloomFilter","type":"bytes32"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"FEATURE_NAME","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"FEATURE_VERSION","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"GREEDY_TOKENS_BLOOM_FILTER","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"migrate","outputs":[{"internalType":"bytes4","name":"success","type":"bytes4"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IERC20TokenV06[]","name":"tokens","type":"address[]"},{"internalType":"uint256","name":"sellAmount","type":"uint256"},{"internalType":"uint256","name":"minBuyAmount","type":"uint256"},{"internalType":"bool","name":"isSushi","type":"bool"}],"name":"sellToUniswap","outputs":[{"internalType":"uint256","name":"buyAmount","type":"uint256"}],"stateMutability":"payable","type":"function"}]
    xechange_proxy_router_address = '0xDef1C0ded9bec7F1a1670819833240f027b25EfF'

    SUBSCRIPT_ADDRESS_LIST = [ xechange_proxy_router_address ]


    def strategy_init(self):
        self.xechange_proxy_router_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                            strategy_0xExchangeProxy_router.xechange_proxy_router_abi,
                                            strategy_0xExchangeProxy_router.xechange_proxy_router_address
                                            )
        self.uniswap_v2_calculator_imp = uniswap_v2_calculator.factory(self.web3_api_imp)

    def match_entry(self,tx_object):
        tx_hash = tx_object['hash']
        from_address = tx_object['from']

        try:
            function_object,function_argments = self.xechange_proxy_router_abi_imp.decode_function_input(tx_object['input'])
            function_name = function_object.fn_name
        except:
            return False

        if 'sellToUniswap' == function_name:
            tokens_path = function_argments['tokens']

            if not len(tokens_path) == 2:  #  这个也会有多路径套利的,先不考虑了
                return False

            input_token = tokens_path[0]
            
            if not is_similar_address(input_token,ETH_ADDRESS):   #  只做ETH->Token
                return False

            token_address = tokens_path[-1]
            amountIn = function_argments['sellAmount']
            amountOutMin = function_argments['minBuyAmount']
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,token_address,amountIn,amountOutMin)

            if DEBUG_STRATEGY_LOG:
                self.log('SWAP_EXACT_IN %d %d PATH: %s Profit: %0.4f' % (amountIn,amountOutMin,tokens_path,profit_eth_amount / 10 ** 18))

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('0xExchange sellToUniswap | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | TXHash: %s' % (
                        from_address,
                        amountIn / 10 ** 18,
                        amountOutMin,
                        token_address,
                        acquisition_cost_eth_amount / 10 ** 18,
                        (profit_eth_amount) / 10 ** 18,
                        tx_hash,
                    ))

                return strategy_command.factory(strategy_command.BUY_TOKEN,
                                                tx_hash,
                                                token_address,
                                                acquisition_cost_eth_amount,
                                                delta_token_amount_with_fee,
                                                profit_eth_amount,
                                                tx_object['find_tick'])

        return False

#  Maestro: Router 2
#      https://etherscan.io/tx/0x4c886270421ed4bfab097b07af48be01fbce32fd944373d407f80a4f87b60685
#      https://etherscan.io/tx/0x7561037efda3055a46d81fedbd9b999c83af7e17d6eaa8351626d89f1301d9f1

class strategy_Maestro_router_2(strategy_base):

    NAME = 'Maestro: Router 2'

    #  ABI出处https://etherscan.io/address/0xf9b30557afcf76ea82c04015d80057fa2147dfa9#code
    #  注意,他是混合ABI的,思路是跟踪explorer.phalcon.xyz来逆向
    uniswap_v3_router_abi = [{"inputs":[{"internalType":"contract IEtherTokenV06","name":"weth","type":"address"},{"internalType":"contract IAllowanceTarget","name":"allowanceTarget","type":"address"},{"internalType":"bytes32","name":"greedyTokensBloomFilter","type":"bytes32"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"FEATURE_NAME","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"FEATURE_VERSION","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"GREEDY_TOKENS_BLOOM_FILTER","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"migrate","outputs":[{"internalType":"bytes4","name":"success","type":"bytes4"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IERC20TokenV06[]","name":"tokens","type":"address[]"},{"internalType":"uint256","name":"sellAmount","type":"uint256"},{"internalType":"uint256","name":"minBuyAmount","type":"uint256"},{"internalType":"bool","name":"isSushi","type":"bool"}],"name":"sellToUniswap","outputs":[{"internalType":"uint256","name":"buyAmount","type":"uint256"}],"stateMutability":"payable","type":"function"}]
    uniswap_v2_router_abi = [{"inputs":[{"internalType":"address","name":"_factory","type":"address"},{"internalType":"address","name":"_WETH","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"WETH","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"amountADesired","type":"uint256"},{"internalType":"uint256","name":"amountBDesired","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amountTokenDesired","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"factory","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountIn","outputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountOut","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsIn","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"reserveA","type":"uint256"},{"internalType":"uint256","name":"reserveB","type":"uint256"}],"name":"quote","outputs":[{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETHSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermit","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermitSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityWithPermit","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapETHForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]
    maestro_router_address = '0x80a64c6D7f12C47B7c66c5B4E20E72bc1FCd5d9e'

    SUBSCRIPT_ADDRESS_LIST = [ maestro_router_address ]


    def strategy_init(self):
        self.maestro_router_v2_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                        strategy_Maestro_router_2.uniswap_v2_router_abi,
                                        strategy_Maestro_router_2.maestro_router_address
                                        )
        self.maestro_router_v3_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                        strategy_Maestro_router_2.uniswap_v3_router_abi,
                                        strategy_Maestro_router_2.maestro_router_address
                                        )
        self.uniswap_v2_calculator_imp = uniswap_v2_calculator.factory(self.web3_api_imp)

    def match_entry(self,tx_object):
        tx_hash = tx_object['hash']
        from_address = tx_object['from']
        eth_value = int(tx_object.get('value',0),16)

        #  以下代码是复制Uniswap V2的逻辑
        try:
            function_object,function_argments = self.uniswap_v2_router_abi_imp.decode_function_input(tx_object['input'])    #   这里有概率会找不到函数,不知道为什么
            function_name = function_object.fn_name
        except:
            return False

        if 'swapETHForExactTokens' == function_name:
            amount_in = eth_value
            amount_out = function_argments['amountOut']
            swap_path = function_argments['path']
            
            if swap_path[0] == swap_path[-1]:
                return False
            elif not 2 == len(swap_path):
                return False

            token_address = swap_path[-1]
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,token_address,amount_in,amount_out)

            if DEBUG_STRATEGY_LOG:
                self.log('SWAP_EXACT_IN %d %d PATH: %s Profit: %0.4f' % (amount_in,amount_out,swap_path,profit_eth_amount / 10 ** 18))

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('swapETHForExactTokens | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | TXHash: %s' % (
                        from_address,
                        amount_in / 10 ** 18,
                        amount_out,
                        token_address,
                        acquisition_cost_eth_amount / 10 ** 18,
                        (profit_eth_amount) / 10 ** 18,
                        tx_hash,
                    ))

                return strategy_command.factory(strategy_command.BUY_TOKEN,
                                                tx_hash,
                                                token_address,
                                                acquisition_cost_eth_amount,
                                                delta_token_amount_with_fee,
                                                profit_eth_amount,
                                                tx_object['find_tick'])
        elif 'swapExactETHForTokensSupportingFeeOnTransferTokens' == function_name:
            amount_in = eth_value
            amount_out = function_argments['amountOutMin']
            swap_path = function_argments['path']

            if swap_path[0] == swap_path[-1]:
                return False
            elif not 2 == len(swap_path):
                return False

            token_address = swap_path[-1]
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,token_address,amount_in,amount_out)

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('swapExactETHForTokensSupportingFeeOnTransferTokens | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | TXHash: %s' % (
                        from_address,
                        amount_in / 10 ** 18,
                        amount_out,
                        token_address,
                        acquisition_cost_eth_amount / 10 ** 18,
                        (profit_eth_amount) / 10 ** 18,
                        tx_hash,
                    ))
            else:
                return False
                
            return strategy_command.factory(strategy_command.BUY_TOKEN,
                                            tx_hash,
                                            token_address,
                                            acquisition_cost_eth_amount,
                                            delta_token_amount_with_fee,
                                            profit_eth_amount,
                                            tx_object['find_tick'])
        elif 'swapTokensForExactTokens' == function_name:
            swap_path_input_token = function_argments['path'][0]
            swap_path_out_token = function_argments['path'][-1]

            if not is_similar_address(WETH_ADDRESS,swap_path_input_token):
                return False
            
            amount_in = function_argments['amountInMax']
            amount_out = function_argments['amountOut']
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,swap_path_out_token,amount_in,amount_out)

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('swapTokensForExactTokens | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | △Token = %d | TXHash: %s' % (
                            from_address,
                            eth_value / 10 ** 18,
                            amount_out,
                            function_argments['path'][1:],
                            (acquisition_cost_eth_amount) / 10 ** 18,
                            (profit_eth_amount) / 10 ** 18,
                            delta_token_amount_with_fee,
                            tx_hash
                        ))
                
                return strategy_command.factory(strategy_command.BUY_TOKEN,
                                                tx_hash,swap_path_out_token,
                                                acquisition_cost_eth_amount,
                                                delta_token_amount_with_fee,
                                                profit_eth_amount,
                                                tx_object['find_tick'])
        else:
            return False

        return False


#  TransitSwapRouterV5
#      https://etherscan.io/tx/0x43201ef561365d8c78901287890f348a62f6e03d02539caa31e2a8b441147284

class strategy_transitswap_router_v5(strategy_base):

    NAME = 'TransitSwap Router V5'

    #  ABI出处https://etherscan.io/address/0x4ff0dec5f9a763aa1e5c2a962aa6f4edfee4f9ea
    transitswap_router_abi = [{"anonymous":False,"inputs":[{"indexed":False,"internalType":"address","name":"newBridge","type":"address"}],"name":"ChangeAggregateBridge","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"address[]","name":"callers","type":"address[]"}],"name":"ChangeCrossCallerAllowed","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"bool","name":"isAggregate","type":"bool"},{"indexed":False,"internalType":"uint256","name":"newRate","type":"uint256"}],"name":"ChangeFeeRate","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"address","name":"preSigner","type":"address"},{"indexed":False,"internalType":"address","name":"newSigner","type":"address"}],"name":"ChangeSigner","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"uint256[]","name":"poolIndex","type":"uint256[]"},{"indexed":False,"internalType":"address[]","name":"factories","type":"address[]"},{"indexed":False,"internalType":"bytes[]","name":"initCodeHash","type":"bytes[]"}],"name":"ChangeV3FactoryAllowed","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"address[]","name":"wrappedTokens","type":"address[]"},{"indexed":False,"internalType":"bool[]","name":"newAllowed","type":"bool[]"}],"name":"ChangeWrappedAllowed","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"previousExecutor","type":"address"},{"indexed":True,"internalType":"address","name":"newExecutor","type":"address"}],"name":"ExecutorshipTransferStarted","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"previousExecutor","type":"address"},{"indexed":True,"internalType":"address","name":"newExecutor","type":"address"}],"name":"ExecutorshipTransferred","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"address","name":"account","type":"address"}],"name":"Paused","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"address","name":"from","type":"address"},{"indexed":False,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"Receipt","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"srcToken","type":"address"},{"indexed":True,"internalType":"address","name":"dstToken","type":"address"},{"indexed":True,"internalType":"address","name":"dstReceiver","type":"address"},{"indexed":False,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"returnAmount","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"toChainID","type":"uint256"},{"indexed":False,"internalType":"string","name":"channel","type":"string"}],"name":"TransitSwapped","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"address","name":"account","type":"address"}],"name":"Unpaused","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"token","type":"address"},{"indexed":True,"internalType":"address","name":"executor","type":"address"},{"indexed":True,"internalType":"address","name":"recipient","type":"address"},{"indexed":False,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"Withdraw","type":"event"},{"stateMutability":"nonpayable","type":"fallback"},{"inputs":[],"name":"CHECKFEE_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DOMAIN_SEPARATOR","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"acceptExecutorship","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"srcToken","type":"address"},{"internalType":"address","name":"dstToken","type":"address"},{"internalType":"address","name":"dstReceiver","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"minReturnAmount","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"string","name":"channel","type":"string"},{"internalType":"bytes","name":"signature","type":"bytes"}],"internalType":"struct BaseCore.TransitSwapDescription","name":"desc","type":"tuple"},{"components":[{"internalType":"address","name":"srcToken","type":"address"},{"internalType":"bytes","name":"calldatas","type":"bytes"}],"internalType":"struct BaseCore.CallbytesDescription","name":"callbytesDesc","type":"tuple"}],"name":"aggregate","outputs":[{"internalType":"uint256","name":"returnAmount","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"srcToken","type":"address"},{"internalType":"address","name":"dstToken","type":"address"},{"internalType":"address","name":"dstReceiver","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"minReturnAmount","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"string","name":"channel","type":"string"},{"internalType":"bytes","name":"signature","type":"bytes"}],"internalType":"struct BaseCore.TransitSwapDescription","name":"desc","type":"tuple"},{"components":[{"internalType":"address","name":"srcToken","type":"address"},{"internalType":"bytes","name":"calldatas","type":"bytes"}],"internalType":"struct BaseCore.CallbytesDescription","name":"callbytesDesc","type":"tuple"}],"name":"aggregateAndGasUsed","outputs":[{"internalType":"uint256","name":"returnAmount","type":"uint256"},{"internalType":"uint256","name":"gasUsed","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address[]","name":"crossCallers","type":"address[]"},{"internalType":"address[]","name":"wrappedTokens","type":"address[]"}],"name":"changeAllowed","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bool[]","name":"isAggregate","type":"bool[]"},{"internalType":"uint256[]","name":"newRate","type":"uint256[]"}],"name":"changeFee","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bool","name":"paused","type":"bool"}],"name":"changePause","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"aggregator","type":"address"},{"internalType":"address","name":"signer","type":"address"}],"name":"changeTransitProxy","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256[]","name":"poolIndex","type":"uint256[]"},{"internalType":"address[]","name":"factories","type":"address[]"},{"internalType":"bytes[]","name":"initCodeHash","type":"bytes[]"}],"name":"changeUniswapV3FactoryAllowed","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"srcToken","type":"address"},{"internalType":"address","name":"dstToken","type":"address"},{"internalType":"address","name":"caller","type":"address"},{"internalType":"address","name":"dstReceiver","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"uint256","name":"toChain","type":"uint256"},{"internalType":"string","name":"channel","type":"string"},{"internalType":"bytes","name":"calls","type":"bytes"},{"internalType":"bytes","name":"signature","type":"bytes"}],"internalType":"struct BaseCore.CrossDescription","name":"desc","type":"tuple"}],"name":"cross","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"dstReceiver","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"router","type":"uint256"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"minReturnAmount","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address[]","name":"pool","type":"address[]"},{"internalType":"bytes","name":"signature","type":"bytes"},{"internalType":"string","name":"channel","type":"string"}],"internalType":"struct BaseCore.ExactInputV2SwapParams","name":"exactInput","type":"tuple"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"exactInputV2Swap","outputs":[{"internalType":"uint256","name":"returnAmount","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"dstReceiver","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"router","type":"uint256"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"minReturnAmount","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address[]","name":"pool","type":"address[]"},{"internalType":"bytes","name":"signature","type":"bytes"},{"internalType":"string","name":"channel","type":"string"}],"internalType":"struct BaseCore.ExactInputV2SwapParams","name":"exactInput","type":"tuple"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"exactInputV2SwapAndGasUsed","outputs":[{"internalType":"uint256","name":"returnAmount","type":"uint256"},{"internalType":"uint256","name":"gasUsed","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"srcToken","type":"address"},{"internalType":"address","name":"dstToken","type":"address"},{"internalType":"address","name":"dstReceiver","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"minReturnAmount","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint256[]","name":"pools","type":"uint256[]"},{"internalType":"bytes","name":"signature","type":"bytes"},{"internalType":"string","name":"channel","type":"string"}],"internalType":"struct BaseCore.ExactInputV3SwapParams","name":"params","type":"tuple"}],"name":"exactInputV3Swap","outputs":[{"internalType":"uint256","name":"returnAmount","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"srcToken","type":"address"},{"internalType":"address","name":"dstToken","type":"address"},{"internalType":"address","name":"dstReceiver","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"minReturnAmount","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint256[]","name":"pools","type":"uint256[]"},{"internalType":"bytes","name":"signature","type":"bytes"},{"internalType":"string","name":"channel","type":"string"}],"internalType":"struct BaseCore.ExactInputV3SwapParams","name":"params","type":"tuple"}],"name":"exactInputV3SwapAndGasUsed","outputs":[{"internalType":"uint256","name":"returnAmount","type":"uint256"},{"internalType":"uint256","name":"gasUsed","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"executor","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"int256","name":"amount0Delta","type":"int256"},{"internalType":"int256","name":"amount1Delta","type":"int256"},{"internalType":"bytes","name":"_data","type":"bytes"}],"name":"pancakeV3SwapCallback","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"paused","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pendingExecutor","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"newExecutor","type":"address"}],"name":"transferExecutorship","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"crossCaller","type":"address"},{"internalType":"address","name":"wrappedToken","type":"address"},{"internalType":"uint256","name":"poolIndex","type":"uint256"}],"name":"transitAllowedQuery","outputs":[{"internalType":"bool","name":"isCrossCallerAllowed","type":"bool"},{"internalType":"bool","name":"isWrappedAllowed","type":"bool"},{"components":[{"internalType":"address","name":"factory","type":"address"},{"internalType":"bytes","name":"initCodeHash","type":"bytes"}],"internalType":"struct BaseCore.UniswapV3Pool","name":"pool","type":"tuple"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"transitFee","outputs":[{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"transitProxyAddress","outputs":[{"internalType":"address","name":"bridgeProxy","type":"address"},{"internalType":"address","name":"feeSigner","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"int256","name":"amount0Delta","type":"int256"},{"internalType":"int256","name":"amount1Delta","type":"int256"},{"internalType":"bytes","name":"_data","type":"bytes"}],"name":"uniswapV3SwapCallback","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address[]","name":"tokens","type":"address[]"},{"internalType":"address","name":"recipient","type":"address"}],"name":"withdrawTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]
    transitswap_router_address = '0x00000047bB99ea4D791bb749D970DE71EE0b1A34'

    SUBSCRIPT_ADDRESS_LIST = [ transitswap_router_address ]


    def strategy_init(self):
        self.transitswap_router_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                        strategy_transitswap_router_v5.transitswap_router_abi,
                                        strategy_transitswap_router_v5.transitswap_router_address
                                        )
        self.uniswap_v2_calculator_imp = uniswap_v2_calculator.factory(self.web3_api_imp)

    def match_entry(self,tx_object):
        tx_hash = tx_object['hash']
        from_address = tx_object['from']

        try:
            function_object,function_argments = self.uniswap_v2_router_abi_imp.decode_function_input(tx_object['input'])
            function_name = function_object.fn_name
        except:
            return False

        if 'exactInputV2Swap' == function_name:
            self.log('SWAP_EXACT_IN %s' % (function_argments))





#  Paraswap v5
#      https://etherscan.io/tx/0xc61a42935b825009f342da37c4216a553309587c08314c64ffc05ca9de9f613e

class strategy_paraswap_router_v5(strategy_base):

    NAME = 'Paraswap v5'

    #  ABI出处https://etherscan.io/address/0x4ff0dec5f9a763aa1e5c2a962aa6f4edfee4f9ea
    paraswap_router_abi = [{"anonymous":False,"inputs":[{"indexed":False,"internalType":"bytes16","name":"uuid","type":"bytes16"},{"indexed":False,"internalType":"address","name":"partner","type":"address"},{"indexed":False,"internalType":"uint256","name":"feePercent","type":"uint256"},{"indexed":False,"internalType":"address","name":"initiator","type":"address"},{"indexed":True,"internalType":"address","name":"beneficiary","type":"address"},{"indexed":True,"internalType":"address","name":"srcToken","type":"address"},{"indexed":True,"internalType":"address","name":"destToken","type":"address"},{"indexed":False,"internalType":"uint256","name":"srcAmount","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"receivedAmount","type":"uint256"}],"name":"Bought2","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"bytes16","name":"uuid","type":"bytes16"},{"indexed":False,"internalType":"address","name":"partner","type":"address"},{"indexed":False,"internalType":"uint256","name":"feePercent","type":"uint256"},{"indexed":False,"internalType":"address","name":"initiator","type":"address"},{"indexed":True,"internalType":"address","name":"beneficiary","type":"address"},{"indexed":True,"internalType":"address","name":"srcToken","type":"address"},{"indexed":True,"internalType":"address","name":"destToken","type":"address"},{"indexed":False,"internalType":"uint256","name":"srcAmount","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"receivedAmount","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"expectedAmount","type":"uint256"}],"name":"Swapped2","type":"event"},{"inputs":[],"name":"ROUTER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"WHITELISTED_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address","name":"weth","type":"address"},{"internalType":"uint256[]","name":"pools","type":"uint256[]"}],"name":"buyOnUniswapV2Fork","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address","name":"weth","type":"address"},{"internalType":"uint256[]","name":"pools","type":"uint256[]"},{"internalType":"bytes","name":"permit","type":"bytes"}],"name":"buyOnUniswapV2ForkWithPermit","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"getKey","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"bytes","name":"data","type":"bytes"}],"name":"initialize","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address","name":"weth","type":"address"},{"internalType":"uint256[]","name":"pools","type":"uint256[]"}],"name":"swapOnUniswapV2Fork","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address","name":"weth","type":"address"},{"internalType":"uint256[]","name":"pools","type":"uint256[]"},{"internalType":"bytes","name":"permit","type":"bytes"}],"name":"swapOnUniswapV2ForkWithPermit","outputs":[],"stateMutability":"payable","type":"function"}]
    paraswap_router_address = '0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57'

    SUBSCRIPT_ADDRESS_LIST = [ paraswap_router_address ]


    def strategy_init(self):
        self.paraswap_router_abi_imp = self.web3_api_imp.make_contract_object_by_address(
                                        strategy_paraswap_router_v5.paraswap_router_abi,
                                        strategy_paraswap_router_v5.paraswap_router_address
                                        )
        self.uniswap_v2_calculator_imp = uniswap_v2_calculator.factory(self.web3_api_imp)

    def match_entry(self,tx_object):
        tx_hash = tx_object['hash']
        from_address = tx_object['from']

        try:
            function_object,function_argments = self.paraswap_router_abi_imp.decode_function_input(tx_object['input'])
            function_name = function_object.fn_name
        except:
            return False

        if 'swapOnUniswapV2Fork' == function_name:
            token_in = function_argments['tokenIn']
            tokens_path = function_argments['pools']

            if not len(tokens_path) == 1:
                return False

            if not is_similar_address(token_in,ETH_ADDRESS):   #  只做ETH->Token
                return False

            output_token = '0x' + hex(tokens_path[0])[2:].rjust(40, '0')
            output_token = self.web3_api_imp.convert_address(output_token)
            token_address = tokens_path[-1]
            amountIn = function_argments['amountIn']
            amountOutMin = function_argments['amountOutMin']
            delta_token_amount_with_fee,acquisition_cost_eth_amount,profit_eth_amount = \
                self.uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(WETH_ADDRESS,output_token,amountIn,amountOutMin)

            if check_min_mev_amount(profit_eth_amount):
                self.highlight_log('MaestroRouter2 sellToUniswap | %s Take %0.4f WETH Swap %0.4f Token %s | CostETH %0.4f ProfitETH %0.4f | TXHash: %s' % (
                        from_address,
                        amountIn / 10 ** 18,
                        amountOutMin,
                        token_address,
                        acquisition_cost_eth_amount / 10 ** 18,
                        (profit_eth_amount) / 10 ** 18,
                        tx_hash,
                    ))

                return strategy_command.factory(strategy_command.BUY_TOKEN,
                                                tx_hash,
                                                token_address,
                                                acquisition_cost_eth_amount,
                                                delta_token_amount_with_fee,
                                                profit_eth_amount,
                                                tx_object['find_tick'])

        return False

#  1inch v5: Aggregation Router
#    https://etherscan.io/tx/0x6fddbbdc5e0cafbd60238df3b7a2ea2166ad092b27c8f0fd38833a7cde23f90b













ALL_SUPPORT_STRATEGY = [
    strategy_uniswap_v2_router,
    strategy_uniswap_v3_router,
    strategy_uniswap_universal_router,
    strategy_0xExchangeProxy_router,
    strategy_Maestro_router_2,
    strategy_paraswap_router_v5,
    strategy_transitswap_router_v5
]



if __name__ == '__main__':
    from web_rpc_api import *

    remote_rpc_url = 'https://burned-sly-dew.quiknode.pro//'
    remote_rpc_url = 'https://mainnet.infura.io/v3/'
    #remote_rpc_url = 'https://winter-necessary-county.ethereum-goerli.quiknode.pro//'
    remote_web3 = rpc_api(remote_rpc_url)
    uniswap_v2_calculator_imp = uniswap_v2_calculator.factory(remote_web3)

    #  forge test -vvvv --fork-url=https://rpc.ankr.com/eth_goerli --fork-block-number=9972095

    weth_address = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'  # '0xB4FBF271143F4FBf7B91A5ded31805e42b2208d6'
    token_address = '0xFD20E1B78C353877a25274C85Fb5566277e5F60E' # '0xd35CCeEAD182dcee0F148EbaC9447DA2c4D449c4'
    in_eth_amount = 0.5 * 10 ** 18  # 0.35 * 10 ** 18 # 10 * 10 ** 18
    token_min_amount = 298017194151370  #  31875332282290055924945 # 1000000000000000000000000000

    uniswap_v2_calculator_imp.set_test_reserve(token_address,weth_address,12083478094218415,19713803008625499227)

    #MAX_MEV_ETH_AMOUNT = 0.01 * 10 ** 18

    delta_token_amount,acquisition_cost_eth_amount,profit_eth_amount = \
        uniswap_v2_calculator_imp.eth_buy_token_calculate_eth_profit_with_expect_min_token(weth_address,token_address,in_eth_amount,token_min_amount)

    print(delta_token_amount,acquisition_cost_eth_amount / 10 ** 18,profit_eth_amount / 10 ** 18)
    print(check_min_mev_amount(profit_eth_amount))

