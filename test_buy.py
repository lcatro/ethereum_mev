
import math
import time

from decimal import Decimal

#  https://etherscan.io/tx/0xd1ced9c8f6434e73350087750acefd8ea86f656d2b53fe2d010f25d10c1524b8
#    >  https://etherscan.io/tx/0x8b6f318e79959512c3e31255b75c363c1888e367d15db71bd5e8008fa2488ab9
#         Rt = 41898624244955793
#         Re = 35550997132740573981
#         delta_ETH = 1 * 10 ** 18
#         delta_Token = 1101945872808331
#    >  https://etherscan.io/tx/0x8b6f318e79959512c3e31255b75c363c1888e367d15db71bd5e8008fa2488ab9
#         Rt = 140530857421511
#         Re = 7285594271363143603
#         delta_ETH = 0.1 * 10 ** 18
#         delta_Token = 1757506671675
#  https://etherscan.io/tx/0x5ce51de2a35310d2362e1cb4913ffee40daba630d267941d3bebbb155e6da5aa

Rt = 140530857421511
Re = 7285594271363143603
delta_ETH = 0.1 * 10 ** 18
delta_Token = int(1757506671675 * 0.1)


def calcu_getAmountOut(reserve_In,reserve_Out,input_amount):
    return ((input_amount * 997) * reserve_In) / (reserve_Out * 1000 + (input_amount * 997))

def find_maximum_profit(reserve_Token,reserve_ETH,expect_input_ETH,except_output_Token):  #  万次执行的性能是0.5s
    step_eth_amount = 1.0 * 10 ** 18   #  初始每次逼近模拟增加1 ETH
    minimum_accuracy = 0.001 * 10 ** 18
    mev_bot_buy_eth = step_eth_amount
    last_mev_bot_get_token_amount = 0
    last_mev_bot_eth_profit = 0
    normal_output_token = int(calcu_getAmountOut(reserve_Token,reserve_ETH,expect_input_ETH))
    slippage_rate = except_output_Token / normal_output_token

    if slippage_rate < 0.09:  #  为什么不是0.1,是因为有计算误差
        #  对于delta_Token非常小的值,其实就是滑点非常大的情况
        #  这个时候去逼近最值是没有意义的,因为会死循环,所以只搞定90%滑点以下的所有交易
        return 0,0,0

    while step_eth_amount >= minimum_accuracy:  #  逼近的最小精度为0.001 ETH
        emulate_reserve_Token = reserve_Token
        emulate_reserve_ETH = reserve_ETH
        
        #  计算MEV顶上去之后的池子reserve值
        mev_bot_get_token_amount = int(calcu_getAmountOut(emulate_reserve_Token,emulate_reserve_ETH,mev_bot_buy_eth))
        emulate_reserve_Token -= mev_bot_get_token_amount
        emulate_reserve_ETH += mev_bot_buy_eth

        #  计算被夹用户正常被顶之后可以兑换出来的Token数量
        normal_tx_token_output = int(calcu_getAmountOut(emulate_reserve_Token,emulate_reserve_ETH,expect_input_ETH))

        #  计算最终MEV利润率
        emulate_reserve_Token -= normal_tx_token_output
        emulate_reserve_ETH += expect_input_ETH
        eth_profit = calcu_getAmountOut(emulate_reserve_ETH,emulate_reserve_Token,mev_bot_get_token_amount) - mev_bot_buy_eth

        if normal_tx_token_output > except_output_Token:  #  如果兑换出来的Token值多于正常交易预期输出Token,那就继续逼近
            mev_bot_buy_eth += step_eth_amount
            last_mev_bot_get_token_amount = mev_bot_get_token_amount
            last_mev_bot_eth_profit = eth_profit
        else:  #  如果兑换出来的Token小于正常交易的期望值
            mev_bot_buy_eth -= step_eth_amount  #  回退这次自增,下降一个数量级继续来
            step_eth_amount = step_eth_amount / 10  #  接下来逼近模拟的精度减小1/10

            if mev_bot_buy_eth <= 0:
                mev_bot_buy_eth = step_eth_amount

            continue

    return int(mev_bot_buy_eth),int(last_mev_bot_get_token_amount),int(last_mev_bot_eth_profit)

start_time = time.time()

for index in range(10000):
    mev_bot_buy_eth,mev_bot_get_token_amount,eth_profit = find_maximum_profit(Rt,Re,delta_ETH,delta_Token)

print(mev_bot_buy_eth / 10 ** 18,mev_bot_get_token_amount , eth_profit / 10 ** 18)
print('Using',time.time() - start_time)

exit()









import web_rpc_api


PK = '99aed8678f8747d700c1ab89e55e905092a53deb88f91d0b193877111514f540'

abi = [{"inputs":[{"internalType":"address","name":"_factory","type":"address"},{"internalType":"address","name":"_WETH","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[],"name":"WETH","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"amountADesired","type":"uint256"},{"internalType":"uint256","name":"amountBDesired","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amountTokenDesired","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"addLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"},{"internalType":"uint256","name":"liquidity","type":"uint256"}],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"factory","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountIn","outputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"reserveIn","type":"uint256"},{"internalType":"uint256","name":"reserveOut","type":"uint256"}],"name":"getAmountOut","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsIn","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"reserveA","type":"uint256"},{"internalType":"uint256","name":"reserveB","type":"uint256"}],"name":"quote","outputs":[{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"pure","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidity","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETH","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"removeLiquidityETHSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermit","outputs":[{"internalType":"uint256","name":"amountToken","type":"uint256"},{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountTokenMin","type":"uint256"},{"internalType":"uint256","name":"amountETHMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityETHWithPermitSupportingFeeOnTransferTokens","outputs":[{"internalType":"uint256","name":"amountETH","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint256","name":"liquidity","type":"uint256"},{"internalType":"uint256","name":"amountAMin","type":"uint256"},{"internalType":"uint256","name":"amountBMin","type":"uint256"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"approveMax","type":"bool"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"removeLiquidityWithPermit","outputs":[{"internalType":"uint256","name":"amountA","type":"uint256"},{"internalType":"uint256","name":"amountB","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapETHForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETHSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"},{"internalType":"uint256","name":"amountInMax","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapTokensForExactTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},{"stateMutability":"payable","type":"receive"}]
uniaddress = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
wethaddress = '0xB4FBF271143F4FBf7B91A5ded31805e42b2208d6'
tokenAdd = '0xd35CCeEAD182dcee0F148EbaC9447DA2c4D449c4'

is_goerli_test = True

if is_goerli_test:
    remote_rpc_url = 'https://winter-necessary-county.ethereum-goerli.quiknode.pro//'
else:
    remote_rpc_url = 'https://burned-sly-dew.quiknode.pro//'


remote_web3 = web_rpc_api.rpc_api(remote_rpc_url)
uni_imp = remote_web3.make_contract_object_by_address(abi,uniaddress)

WALLET = remote_web3.get_wallet_address_from_private_key(PK)
print(WALLET)
tx_nonce = remote_web3.get_nonce(WALLET)
tx_object = uni_imp.functions.swapETHForExactTokens(1000,[wethaddress,tokenAdd],WALLET,0xFFFFFFFF).buildTransaction({
        'value':  remote_web3.web3_object.toWei(0.0001, 'ether'),
        'gasPrice':  int(remote_web3.get_gas_price()), # * 1.1 ),
        'from': WALLET,
        'nonce': tx_nonce,
    })
tx_object['gas'] = remote_web3.get_estimate_gas(tx_object)

signed_tx_object = remote_web3.sign_transation_with_private_key(tx_object,PK)
print(signed_tx_object.rawTransaction.hex())
print(remote_web3.send_transation(signed_tx_object))









def eth_buy_token_calculate_eth_profit_with_expect_min_token(self,
        weth_address,
        token_address,
        in_eth_amount,     #  被夹TX输入ETH
        token_min_amount,  #  被夹TX预计换出的最少Token
        max_mev_eth_amount #  夹子最大可用的ETH
        ):
    weth_address_number = Decimal(int(weth_address,16))
    token_address_number = Decimal(int(token_address,16))
    pair_address = self.get_pair(weth_address,token_address)
    pair_imp = self.web3_imp.make_contract_object_by_address(uniswap_v2_calculator.uniswap_v2_pair_abi,pair_address)

    if self.test_reserve_a or self.test_reserve_b:
        reserve_a,reserve_b = (self.test_reserve_a,self.test_reserve_b)
    else:
        reserve_a,reserve_b,_ = pair_imp.functions.getReserves().call()

    in_eth_amount = Decimal(in_eth_amount)
    token_min_amount = Decimal(token_min_amount)
    max_mev_eth_amount = Decimal(max_mev_eth_amount)

    if weth_address_number < token_address_number:
        weth_reserve = reserve_a
        token_reserve = reserve_b
    else:
        weth_reserve = reserve_b
        token_reserve = reserve_a

    #  计算思路:
    #  第一步,计算MEV抢先买入的ETH
    #    in_eth_amount ==可以兑换==> real_token_amount
    #    套利空间(指买入这么多Token然后卖出): delta_token_amount = (token_min_amount - real_token_amount)
    #    需要买入的ETH成本: delta_token_amount ==需要兑换==> acquisition_cost_eth_amount

    '''
        function getAmountOut(uint amountIn, uint reserveIn, uint reserveOut) internal pure returns (uint amountOut) {
            require(amountIn > 0, 'UniswapV2Library: INSUFFICIENT_INPUT_AMOUNT');
            require(reserveIn > 0 && reserveOut > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
            uint amountInWithFee = amountIn.mul(997);
            uint numerator = amountInWithFee.mul(reserveOut);
            uint denominator = reserveIn.mul(1000).add(amountInWithFee);
            amountOut = numerator / denominator;
        }
        
        // given an output amount of an asset and pair reserves, returns a required input amount of the other asset
        function getAmountIn(uint amountOut, uint reserveIn, uint reserveOut) internal pure returns (uint amountIn) {
            require(amountOut > 0, 'UniswapV2Library: INSUFFICIENT_OUTPUT_AMOUNT');
            require(reserveIn > 0 && reserveOut > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
            uint numerator = reserveIn.mul(amountOut).mul(1000);
            uint denominator = reserveOut.sub(amountOut).mul(997);
            amountIn = (numerator / denominator).add(1);
        }
    '''

    real_token_amount = ((in_eth_amount * 997) * token_reserve) / (weth_reserve * 1000 + (in_eth_amount * 997))  #  getAmountOut()
    #  丢弃千分之三作为手续费
    delta_token_amount_no_fee = (real_token_amount - token_min_amount)  #  这个是打给池子的真实数额
    delta_token_amount_with_fee = (real_token_amount - token_min_amount) * 997 / 1000  #  这个是兑换出来Token的真实数额
    n = (weth_reserve * delta_token_amount_with_fee * 1000)
    m = (token_reserve - delta_token_amount_with_fee) * 997
    #   他妈的臭嗨,傻逼python不能把这段合并来算,会丢精度,不知道为什么
    #   => acquisition_cost_eth_amount = (weth_reserve * delta_token_amount_with_fee * 1000) / (token_reserve - delta_token_amount_with_fee) * 997 + 1
    acquisition_cost_eth_amount = n / m + 1  #  getAmountIn()  

    if acquisition_cost_eth_amount > max_mev_eth_amount:
        #  因为MEV里面的ETH是有限的,这个判断是在MEV Bot有限的ETH内夹出利润
        #  那么就需要从max_mev_eth_amount推导出来delta_token_amount_with_fee.使用getAmountOut()
        delta_token_amount_no_fee = ((max_mev_eth_amount * 997) * token_reserve) / (weth_reserve * 1000 + (max_mev_eth_amount * 997))  #  getAmountOut()
        delta_token_amount_with_fee = delta_token_amount_no_fee * 997 / 1000
        acquisition_cost_eth_amount = max_mev_eth_amount

    #  第二步,计算被夹用户买入之后池子的reserve的变动

    '''
        function swap(uint amount0Out, uint amount1Out, address to, bytes calldata data) external lock {
            // 省略无关代码
            balance0 = IERC20(_token0).balanceOf(address(this));
            balance1 = IERC20(_token1).balanceOf(address(this));

            // 省略无关代码
            _update(balance0, balance1, _reserve0, _reserve1);
            
        }

        function _update(uint balance0, uint balance1, uint112 _reserve0, uint112 _reserve1) private {
            // 省略无关代码
            reserve0 = uint112(balance0);
            reserve1 = uint112(balance1);
            // 省略无关代码
        }
    '''

    weth_reserve += acquisition_cost_eth_amount
    token_reserve -= delta_token_amount_no_fee
    print("reserve0 = {:.0f}".format(weth_reserve))
    print("reserve1 = {:.0f}".format(token_reserve))
    weth_reserve += (in_eth_amount)
    token_reserve -= (token_min_amount)
    print("reserve0 = {:.0f}".format(weth_reserve))
    print("reserve1 = {:.0f}".format(token_reserve))

    #  第三步,计算卖出后的总利润有多少
    #    delta_token_amount ==可以兑换==> sell_token_eth_amount

    n = (weth_reserve * delta_token_amount_with_fee * 1000)
    m = (token_reserve - delta_token_amount_with_fee) * 997
    sell_token_eth_amount = n / m + 1  #  getAmountIn()

    if sell_token_eth_amount < 0:  #  小于0就代表换币出来是盈利的
        profit_eth_amount = abs(sell_token_eth_amount) - acquisition_cost_eth_amount
    else:  #  大于0说明是亏损,因为你要倒贴ETH进去换Token
        #  acquisition_cost_eth_amount  取值为正数
        profit_eth_amount = sell_token_eth_amount + acquisition_cost_eth_amount

    return int(delta_token_amount_with_fee),int(acquisition_cost_eth_amount),int(profit_eth_amount)


