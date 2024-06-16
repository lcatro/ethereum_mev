
import os
import sys

from flashbot_api import *
from mev_bot_api import *
from web_rpc_api import *



if __name__ == '__main__':
    if not len(sys.argv) in [3,4]:
        print('python3 mev_bot_cli.py withdraw_eth amount')
        print('python3 mev_bot_cli.py withdraw_token amount token_address')
        exit()

    wallet_pk = os.getenv('pk')
    mevbot_address = os.getenv('mevbot')
    singer_pk = Account.from_key(os.getenv('singer_pk'))
    is_goerli_testnet = int(os.getenv('debug_in_goerli'))
    
    if is_goerli_testnet:
        remote_rpc_url = 'https://winter-necessary-county.ethereum-goerli.quiknode.pro//'
    else:
        remote_rpc_url = 'https://burned-sly-dew.quiknode.pro//'

    remote_web3 = rpc_api(remote_rpc_url)
    wallet_address = local_web3.get_wallet_address_from_private_key(wallet_pk)
    wallet_nonce = remote_web3.get_nonce(wallet_address)

    print('Wallet %s - %0.6f ETH' % (mevbot_address,remote_web3.get_wallet_balances(mevbot_address) / 10 ** 18))

    mev_bot_imp = mev_bot.factory(remote_web3,mevbot_address,wallet_pk)
    amount = float(sys.argv[2])


    if is_goerli_testnet:
        flashbot(remote_web3.web3_object, singer_pk, "https://relay-goerli.flashbots.net")
    else:
        flashbot(remote_web3.web3_object, singer_pk, "https://relay.flashbots.net")

    while True:
        if sys.argv[1] == 'withdraw_eth':
            tx_rawtransation = mev_bot_imp.WithdrawETH(amount * 10 ** 18,wallet_nonce)
            print(remote_web3.web3_object.eth.sendRawTransaction(tx_rawtransation).hex())
            exit()
        elif sys.argv[1] == 'withdraw_token':
            token_address = sys.argv[3]
            tx_rawtransation = mev_bot_imp.WithdrawToken(token_address,amount,wallet_nonce)
            print(remote_web3.web3_object.eth.sendRawTransaction(tx_rawtransation).hex())
            exit()
        elif sys.argv[1] == 'sell_token':
            token_address = sys.argv[3]
            tx_gasprice = int(remote_web3.get_gas_price() * 1.1)
            expectETHAmount = 1   #  先偷个懒
            tx_rawtransation,_ = mev_bot_imp.TokenSwapETH(int(amount),expectETHAmount,token_address,wallet_nonce,tx_gasprice)
        else:
            print('Error Command')
            exit()

        bundle = [
            {"signed_transaction": tx_rawtransation}
        ]
        block = remote_web3.rpc_newest_block_number() + 1
        print('BN->%d ' % (block))
        a = remote_web3.web3_object.flashbots.simulate(bundle,block_tag = block)
        print('Simulate Result:%s' % (remote_web3.web3_object.flashbots.simulate(bundle,block_tag = block)))
        send_result = remote_web3.web3_object.flashbots.send_bundle(
            bundle,
            target_block_number=block,
        )
        print("bundleHash",block,send_result.bundle_hash().hex())

        send_result.wait()
        try:
            receipts = send_result.receipts()
            print(f"\nBundle was mined in block {receipts[0].blockNumber}\a")
            break
        except:
            pass
