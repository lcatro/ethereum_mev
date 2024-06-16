
import copy
import time

from hexbytes import HexBytes
from web3 import Web3
from web3.middleware import geth_poa_middleware

import eth_account

from eth_account.messages import encode_defunct
from eth_account._utils.signing import (
    encode_transaction, serializable_unsigned_transaction_from_dict
)
from eth_abi import decode,encode
from eth_abi.packed import encode_packed

BLOCK_TX_TYPE_CREATE = '0x0'
BLOCK_TX_TYPE_FREE   = '0x1'
BLOCK_TX_TYPE_TRANS  = '0x2'

NULL_ADDRESS = '0x0000000000000000000000000000000000000000'


def remake_web3_object_by_rpc_url(rpc_url):
    global web3

    web3 = Web3(Web3.HTTPProvider(rpc_url))

    web3.middleware_onion.inject(geth_poa_middleware, layer=0)


socks5 = ''


class rpc_api:

    def __init__(self,rpc_url,chainid = 0):
        self.web3_object = Web3(Web3.HTTPProvider(rpc_url,request_kwargs={'timeout': 10}))#,'proxies':{'http': socks5,'https': socks5}}))
        self.chainid = chainid

        self.web3_object.middleware_onion.inject(geth_poa_middleware,layer = 0)

    def is_eth_address(self,address):
        return self.web3_object.isAddress(self.web3_object.toChecksumAddress(address))

    def is_contract_address(self,address):
        data = self.web3_object.eth.getCode(self.web3_object.toChecksumAddress(address))

        if len(data) > 2:
            return True

        return False

    def convert_address(self,address):
        return self.web3_object.toChecksumAddress(address)

    def rpc_newest_block_number(self):
        return self.web3_object.eth.block_number

    def rpc_get_block_info(self,block_number):
        return self.web3_object.eth.getBlock(block_number)

    def rpc_get_tx_count_by_block_number(self,block_number):
        return self.web3_object.eth.get_block_transaction_count(block_number)

    def rpc_get_all_tx_by_block_number(self,block_number):
        block_data = self.rpc_get_block_info(block_number)
        result = []

        for index in range(self.rpc_get_tx_count_by_block_number(block_number)):
            tx_data = self.web3_object.eth.getTransactionByBlock(block_number,index)
            to_address = tx_data.get('to')

            if to_address:
                to_address = to_address.lower()

            data = {
                'type': tx_data['type'],
                'input': tx_data['input'],
                'from': tx_data['from'].lower(),
                'to': to_address,  #  Maybe is None
                'price': str(tx_data['value']),
                'tx_hash': tx_data['hash'].hex(),
                'block_number': block_number,
                'timetick': block_data['timestamp']
            }
            
            result.append(data)

        return result

    def rpc_get_contract_create_address(self,tx_hash):
        data = self.web3_object.eth.getTransactionReceipt(tx_hash)

        if not data:
            return ''

        if not 'contractAddress' in data:
            return ''

        return data['contractAddress'].lower()

    def rpc_get_all_event_by_tx_hash(self,tx_hash):
        data = self.web3_object.eth.getTransactionReceipt(tx_hash)
        
        if not data:
            return []

        result = []

        for index in data['logs']:
            topics = []

            for topics_index in index['topics']:
                topics.append(topics_index.hex())

            result.append({
                'addres': index['address'].lower() ,
                'topics': topics ,
                'data': index['data'] ,
                'block_number': index['blockNumber'] ,
                'tx_hash': index['transactionHash'].hex() ,
                'log_index': index['logIndex'] ,
                'tx_index': index['transactionIndex'] ,
            })

        return result

    def rpc_get_contract_code(self,contract_address):
        #self.web3_object.eth.get
        pass


    def make_contract_object_by_address(self,contract_abi,contract_address):
        return self.web3_object.eth.contract(abi = contract_abi,address = contract_address)

    def make_contract_object_by_code(self,contract_abi,contract_code):
        return self.web3_object.eth.contract(abi = contract_abi,bytecode = contract_code)

    def sign_data_with_private_key(self,data,pk):
        pk_bytes = bytes(bytearray.fromhex(pk))
        message = encode_defunct(text = data)

        return self.web3_object.eth.account.sign_message(message,private_key = self.web3_object.toHex(pk_bytes))['signature'].hex()

    def sign_transation_with_private_key(self,tx_object,pk):
        return self.web3_object.eth.account.signTransaction(tx_object,private_key = pk)

    def make_tx_send_transation(self,send_wallet,to_wallet,balance_ether,nonce):
        #nonce = self.get_nonce(send_wallet)
        tx_object = {
            'chainId': self.get_chainid(),
            'nonce': nonce,
            'from': send_wallet,
            'to': to_wallet,
            'value': self.web3_object.toWei(balance_ether, 'ether'),
            'type': 2,
            "maxFeePerGas": self.web3_object.toWei(200, "gwei"),
            'maxPriorityFeePerGas': self.web3_object.toWei(50, 'gwei'),
        }
        
        tx_object['gas'] = self.get_estimate_gas(tx_object)

        return tx_object

    def send_transation(self,signed_tx_object):
        return self.web3_object.eth.sendRawTransaction(signed_tx_object.rawTransaction).hex()

    def get_web3_object(self):
        return self.web3_object

    def get_wallet_balances(self,wallet_address):
        return self.web3_object.eth.get_balance(self.convert_address(wallet_address))

    def get_chainid(self):
        return self.web3_object.eth.chainId

    def get_block_all_tx(self,block_number):
        return self.web3_object.eth.get_block(block_number,True)

    def get_storage_at(self,contract_address,location):
        return self.web3_object.eth.get_storage_at(contract_address,location)
        
    def get_nonce(self,wallet_address):
        return self.web3_object.eth.getTransactionCount(self.convert_address(wallet_address))

    def get_tx(self,tx_hash):
        return self.web3_object.eth.getTransactionReceipt(tx_hash)

    def create_wallet(self):
        wallet_object = self.web3_object.eth.account.create()

        return wallet_object.address,wallet_object.privateKey.hex()[2:]

    def get_wallet_address_from_private_key(self,pk):
        PA = self.web3_object.eth.account.from_key(pk)

        return PA.address

    def get_estimate_gas(self,tx_object):
        gas_estimate = self.web3_object.eth.estimateGas(tx_object)

        return gas_estimate

    def get_gas_price(self):

        #   https://ethereum.stackexchange.com/questions/123453/error-transactions-maxfeepergas-0-is-less-than-the-blocks-basefeepergas-52
        block = self.web3_object.eth.get_block('latest')
        return int(block.get('baseFeePerGas'))

        try:
            return self.web3_object.eth.gas_price + self.web3_object.eth.max_priority_fee
        except:
            return self.web3_object.eth.gas_price

    def get_abi_encode(self,abi_type,abi_data):
        '''
            Example:
                get_abi_encode('uint256', '2345675643')
                get_abi_encode('bytes32[]', ['0xdf3234', '0xfdfd'])
                get_abi_encode(
                    {
                        "ParentStruct": {
                            "propertyOne": 'uint256',
                            "propertyTwo": 'uint256',
                            "childStruct": {
                                "propertyOne": 'uint256',
                                "propertyTwo": 'uint256'
                            }
                        }
                    },
                    {
                        "propertyOne": 42,
                        "propertyTwo": 56,
                        "childStruct": {
                            "propertyOne": 45,
                            "propertyTwo": 78
                        }
                    })

        '''

        #return encode_packed(abi_type,abi_data)
        return encode(abi_type,abi_data)


    def decode_abi_encode(self,abi_type,abi_data):
        '''

            Example:
                decode_abi_encode(['uint256'], b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x0009'))

        '''

        if abi_data.startswith('0x'):
            abi_data = abi_data[2:]

        return decode(abi_type,bytes.fromhex(abi_data))

    def deserialize_contract_input(self,contract_imp,input_data):
        return contract_imp.decode_function_input(input_data)

    def waitting_tx(self,tx_hash):
        while True:
            try:
                self.get_tx(tx_hash)

                break
            except:
                time.sleep(0.2)

    def tx_object_to_rawtransation(self,tx_object,v,r,s):
        #print('1',tx_object)
        tx_object = copy.deepcopy(tx_object)
        
        try:
            tx_object.pop('from')
        except:
            pass
        try:
            tx_object.pop('hash')
        except:
            pass
        try:
            tx_object.pop('blockHash')
            tx_object.pop('blockNumber')
            tx_object.pop('transactionIndex')
        except:
            pass
        try:
            tx_object.pop('v')
            tx_object.pop('r')
            tx_object.pop('s')
        except:
            pass
        try:
            tx_object.pop('yParity')
        except:
            pass
        try:
            tx_object.pop('find_tick')
        except:
            pass
        if 'maxFeePerGas' in tx_object:
            try:
                tx_object.pop('gasPrice')
            except:
                pass

        tx_object['to'] = self.convert_address(tx_object['to'])

        if int(tx_object.get('type'),16) == 0:
            tx_object.pop('type')
        if 'input' in tx_object:
            tx_object['data'] = tx_object['input']
            tx_object.pop('input')
            
        unsigned_transaction = serializable_unsigned_transaction_from_dict(tx_object)
        signed_transaction = encode_transaction(unsigned_transaction, vrs=(v, r, s))
        raw_transaction_hex = signed_transaction.hex()
        
        return HexBytes('0x' + raw_transaction_hex)


class wallet:

    def __init__(self):
        self.wallet_list = {}

    def add_wallet_address_and_pk(self,wallet_address,pk):
        self.wallet_list[wallet_address.lower()] = pk

    def is_exist(self,wallet_address):
        if wallet_address.lower() in self.wallet_list:
            return True
        
        return False

    def get_pk(self,wallet_address):
        if self.is_exist(wallet_address):
            return self.wallet_list[wallet_address.lower()]
        
        return ''

    def get_wallets(self):
        return list(self.wallet_list.keys())

    def get_wallets_count(self):
        return len(self.wallet_list.keys())

    def factory(pk_file):
        file = open(pk_file)
        data = file.read().split('\n')
        wallet_imp = wallet()
        pk_index = 0

        for pk in data:
            pk = pk.strip()
            
            if pk:
                wallet_address = local_web3.get_wallet_address_from_private_key(pk)

                wallet_imp.add_wallet_address_and_pk(wallet_address,pk)

            pk_index += 1

        return wallet_imp


class erc20:

    ABI = [{"inputs":[{"internalType":"address","name":"aaa","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"a","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"a","type":"uint8"}],"stateMutability":"nonpayable","type":"function"}]

    def __init__(self,rpc_object,contract_address):
        self.contract_imp = rpc_object.make_contract_object_by_address(erc20.ABI,local_web3.convert_address(contract_address))

    def get_erc20_balance(self,wallet_address):
        return self.contract_imp.functions.balanceOf(local_web3.convert_address(wallet_address)).call()
    
    def get_erc20_decimals(self):
        return self.contract_imp.functions.decimals().call()


local_rpc_url = 'http://127.0.0.1:3334'
local_web3 = rpc_api(local_rpc_url)




if __name__ == '__main__':
    payerIsUser,amountIn,amountOutMin,path = local_web3.decode_abi_encode(['bool','uint256','uint256','address[]'],'0000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000011c37937e08000000000000000000000000000000000000000000000000000000055d2ac15ebc0700000000000000000000000000000000000000000000000000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc200000000000000000000000021f96cf878e61ee81c3c74241e48936c45419e4d')
    print(payerIsUser,amountIn,amountOutMin,path)
    exit()

    tx_object = { 'from': '0xfa074444b2881c82bb240ead43b114c2e8fdfc07', 'gas': '0x22704', 'gasPrice': '0x18', 'hash': '0x1408117c3f281b52ecdd831db1661bc52a14c54ea9db99d89fdb2ec4f5ed125b', 'data': '0xfb3bdb4100000000000000000000000000000000000000000000000000000000000003e80000000000000000000000000000000000000000000000000000000000000080000000000000000000000000fa074444b2881c82bb240ead43b114c2e8fdfc0700000000000000000000000000000000000000000000000000000000ffffffff0000000000000000000000000000000000000000000000000000000000000002000000000000000000000000b4fbf271143f4fbf7b91a5ded31805e42b2208d60000000000000000000000005549ac36769287be02a9c673bb9eaaca908e06fb', 'nonce': '0x5', 'to': local_web3.convert_address('0x7a250d5630b4cf539739df2c5dacb4c659f2488d'),'type': '0x00', 'value': '0x5af3107a4000',  'chainId': '0x5'}
    #tx_object = {'chainId': 5, 'nonce': 22,  'to': '', 'value': 100000000000000, 'type': 2, 'maxFeePerGas': 200000000000, 'maxPriorityFeePerGas': 50000000000, 'gas': 21055}
    v = 0x2d
    r = 0x8103cfb49d3cf17eeb64063031e6b6cd08e7224f9dfe071a65f39bbdf3c7efed
    s = 0x74e2121038c857a69f4d365022504bc8f6828ae21b194dccfd64db4e6cc27b6f
    #tx_object['type']= 1
    #  f9014b051883022704947a250d5630b4cf539739df2c5dacb4c659f2488d865af3107a4000b8e4fb3bdb4100000000000000000000000000000000000000000000000000000000000003e80000000000000000000000000000000000000000000000000000000000000080000000000000000000000000fa074444b2881c82bb240ead43b114c2e8fdfc0700000000000000000000000000000000000000000000000000000000ffffffff0000000000000000000000000000000000000000000000000000000000000002000000000000000000000000b4fbf271143f4fbf7b91a5ded31805e42b2208d60000000000000000000000005549ac36769287be02a9c673bb9eaaca908e06fb2da08103cfb49d3cf17eeb64063031e6b6cd08e7224f9dfe071a65f39bbdf3c7efeda074e2121038c857a69f4d365022504bc8f6828ae21b194dccfd64db4e6cc27b6f
    #  f9014b051883022704947a250d5630b4cf539739df2c5dacb4c659f2488d865af3107a4000b8e4fb3bdb4100000000000000000000000000000000000000000000000000000000000003e80000000000000000000000000000000000000000000000000000000000000080000000000000000000000000fa074444b2881c82bb240ead43b114c2e8fdfc0700000000000000000000000000000000000000000000000000000000ffffffff0000000000000000000000000000000000000000000000000000000000000002000000000000000000000000b4fbf271143f4fbf7b91a5ded31805e42b2208d60000000000000000000000005549ac36769287be02a9c673bb9eaaca908e06fb2da08103cfb49d3cf17eeb64063031e6b6cd08e7224f9dfe071a65f39bbdf3c7efeda074e2121038c857a69f4d365022504bc8f6828ae21b194dccfd64db4e6cc27b6f
    print(local_web3.tx_object_to_rawtransation(tx_object,v,r,s).hex())

    exit()
    infura_url = 'https://rpc.ankr.com/eth'
    remote_web3 = rpc_api(infura_url,1)


    contract_imp = erc20(remote_web3,'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2')
    print(contract_imp.get_erc20_decimals())
    print(contract_imp.get_erc20_balance('0x044F4cB7FC6cB4e4801b9b6927969d2d0258798D'))
    exit()

    import sys
    TEST_PK = sys.argv[1]
    file = open(TEST_PK)
    data = file.readlines()[1:]
    file.close()

    '''
    file = open('goerli_data','w')
    index = 0
    for pk in data:
        wallet_address = remote_web3.get_wallet_address_from_private_key(pk.strip())
        eth_balance = remote_web3.get_wallet_balances(wallet_address) / 10 ** 18
        print(index,wallet_address,eth_balance)
        index += 1
        file.write('%s,%f\n' % (wallet_address,eth_balance))

    file.close()
    '''

    import random
    import time

    file = open('goerli_trans','w')
    watch_address = '0x402D6dD892DA0b3FE7e4f2a6a0c30fee010E8864'
    contract_address = '0xCcf1dA47ACf0df3f91ccA58842ca4bde1D90EA96'
    contract_abi = [
        {"inputs":[],"name":"deposit","outputs":[],"stateMutability":"payable","type":"function"}
    ]
    contract_imp = remote_web3.make_contract_object_by_address(contract_abi,contract_address)

    random.shuffle(data)

    for wallet_pk in data:
        watch_address_balance = remote_web3.get_wallet_balances(watch_address)

        if watch_address_balance / (10 ** 18) >= 950000:
            print('Watch Address Balance is Full',watch_address,watch_address_balance)
            exit()

        print('Watch Address Balance',watch_address,watch_address_balance / (10 ** 18))
        
        wallet_pk = wallet_pk.strip()
        wallet_address = remote_web3.get_wallet_address_from_private_key(wallet_pk)
        wallet_balance = remote_web3.get_wallet_balances(wallet_address)

        value = round(random.uniform(1.1,2.9),1) * 10 ** 18
        
        if wallet_balance < 1 * 10 ** 18:
            print('Low balance',wallet_address,wallet_balance)
            time.sleep(random.randint(5,10))
            continue
        elif value > wallet_balance:
            value = wallet_balance - 0.3 * 10 ** 18

        print('Transe balance',wallet_address,value)

        try:
            nonce = remote_web3.get_nonce(wallet_address)
            gas_price = remote_web3.get_gas_price()
            tx_object = contract_imp.functions.deposit().buildTransaction({
                'gasPrice': gas_price,
                'value': int(value),
                'from': remote_web3.convert_address(wallet_address),
                'nonce': nonce,
            })
            tx_object['gas'] = remote_web3.get_estimate_gas(tx_object)
            signed_tx_object = remote_web3.sign_transation_with_private_key(tx_object,wallet_pk)
            tx_hash = remote_web3.send_transation(signed_tx_object)
            print(wallet_address,tx_hash,value)
            file.write('%s,%f,%s\n' % (watch_address,value,tx_hash))
        except:
            print('Except',wallet_address)

        time.sleep(random.randint(5,10))

    #wallet_address = remote_web3.get_wallet_address_from_private_key(TEST_PK)
    #gas_price = remote_web3.get_gas_price()
    #tx_object = remote_web3.make_tx_send_transation(wallet_address,wallet_address,0.0,gas_price)

    #print(tx_object)
    #exit()
    #signed_tx_object = remote_web3.sign_transation_with_private_key(tx_object,TEST_PK)
    #print(remote_web3.send_transation(signed_tx_object))
    #print(web3.toChecksumAddress(('0x430781f7fbc4efd160f8453338da5393ff341639')))
    #print(is_eth_address('0xa5Acc472597C1e1651270da9081Cc5a0b38258E3'))
    #print(is_eth_address('0xe0b7927c4af23765cb51314a0e0521a9645f0e2a'))
    #print(is_contract_address('0xa5Acc472597C1e1651270da9081Cc5a0b38258E3'))
    #print(is_contract_address('0xe0b7927c4af23765cb51314a0e0521a9645f0e2a'))
    #print(rpc_newest_block_number())
    #print(rpc_get_tx_count_by_block_number(rpc_newest_block_number()))
    #print(rpc_get_all_tx_by_block_number(rpc_newest_block_number()))
    #print(rpc_get_all_event_by_tx_hash(''))
    #print(rpc_get_contract_create_address(''))
    
