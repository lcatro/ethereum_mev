"""
Minimal viable example of flashbots usage with dynamic fee transactions.
Sends a bundle of two transactions which transfer some ETH into a random account.

Environment Variables:
- ETH_SENDER_KEY: Private key of account which will send the ETH.
- ETH_SIGNER_KEY: Private key of account which will sign the bundle. 
    - This account is only used for reputation on flashbots and should be empty.
- PROVIDER_URL: HTTP JSON-RPC Ethereum provider URL.
"""

import os
import secrets
from uuid import uuid4
from eth_account.account import Account
from eth_account.signers.local import LocalAccount
from flashbot_api import flashbot
from web3 import Web3, HTTPProvider
from web3.exceptions import TransactionNotFound
from web3.types import TxParams

# change this to `False` if you want to use mainnet
USE_GOERLI = True
CHAIN_ID = 5 if USE_GOERLI else 1


def env(key: str) -> str:
    return os.environ.get(key)


def random_account() -> LocalAccount:
    key = "0x" + secrets.token_hex(32)
    return Account.from_key(key)


def main() -> None:
    # account to send the transfer and sign transactions
    sender: LocalAccount = Account.from_key(env("pk"))
    # account to receive the transfer
    receiverAddress: str = random_account().address
    # account to sign bundles & establish flashbots reputation
    # NOTE: this account should not store funds
    signer: LocalAccount = Account.from_key(env("singer_pk"))

    w3 = Web3(HTTPProvider("https://winter-necessary-county.ethereum-goerli.quiknode.pro//"))
    if USE_GOERLI:
        #flashbot(w3, signer, "https://relay-goerli.flashbots.net")
        flashbot(w3, signer, 'https://goerli.edennetwork.io/v1/rpc')
    else:
        flashbot(w3, signer)

    print(f"Sender address: {sender.address}")
    print(f"Receiver address: {receiverAddress}")
    print(
        f"Sender account balance: {Web3.fromWei(w3.eth.get_balance(sender.address), 'ether')} ETH"
    )
    print(
        f"Receiver account balance: {Web3.fromWei(w3.eth.get_balance(receiverAddress), 'ether')} ETH"
    )

    # bundle two EIP-1559 (type 2) transactions, pre-sign one of them
    # NOTE: chainId is necessary for all EIP-1559 txns
    # NOTE: nonce is required for signed txns

    nonce = w3.eth.get_transaction_count(sender.address)
    tx1: TxParams = {
        "to": receiverAddress,
        "value": Web3.toWei(0.001, "ether"),
        "gas": 21000,
        "maxFeePerGas": Web3.toWei(200, "gwei"),
        "maxPriorityFeePerGas": Web3.toWei(50, "gwei"),
        "nonce": nonce,
        "chainId": CHAIN_ID,
        "type": 2,
    }
    tx1_signed = sender.sign_transaction(tx1)

    tx2: TxParams = {
        "to": receiverAddress,
        "value": Web3.toWei(0.001, "ether"),
        "gas": 21000,
        "maxFeePerGas": Web3.toWei(200, "gwei"),
        "maxPriorityFeePerGas": Web3.toWei(50, "gwei"),
        "nonce": nonce + 1,
        "chainId": CHAIN_ID,
        "type": 2,
    }
    tx2_signed = sender.sign_transaction(tx2)

    bundle = [
        {"signed_transaction": tx1_signed.rawTransaction},
        {"signed_transaction": tx2_signed.rawTransaction},
        #{"signer": sender, "transaction": tx2},
    ]

    # keep trying to send bundle until it gets mined
    while True:
        block = w3.eth.block_number
        
        replacement_uuid = str(uuid4())
        print(block,f"replacementUuid {replacement_uuid}")
        send_result = w3.flashbots.send_bundle(
            bundle,
            target_block_number=block + 1,
            opts={"replacementUuid": replacement_uuid},
        )
        print("bundleHash", w3.toHex(send_result.bundle_hash()))

        send_result.wait()
        try:
            receipts = send_result.receipts()
            print(f"\nBundle was mined in block {receipts[0].blockNumber}\a")
            break
        except TransactionNotFound:
            pass

    print(
        f"Sender account balance: {Web3.fromWei(w3.eth.get_balance(sender.address), 'ether')} ETH"
    )
    print(
        f"Receiver account balance: {Web3.fromWei(w3.eth.get_balance(receiverAddress), 'ether')} ETH"
    )


if __name__ == "__main__":
    main()
