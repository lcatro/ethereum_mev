// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

import "forge-std/Test.sol";
import "../src/Counter.sol";
import "forge-std/Vm.sol";


interface IERC20 {
    
    function name() external pure returns (string memory);
    function approve(address spender, uint value) external returns (bool);
    function balanceOf(address) external returns (uint256);
    function decimals() external view returns (uint8);
    function transfer(address to, uint value) external returns (bool);
    function deposit() external payable;

}

interface IUniswapV2Pair {
    event Approval(address indexed owner, address indexed spender, uint value);
    event Transfer(address indexed from, address indexed to, uint value);

    function name() external pure returns (string memory);
    function symbol() external pure returns (string memory);
    function decimals() external pure returns (uint8);
    function totalSupply() external view returns (uint);
    function balanceOf(address owner) external view returns (uint);
    function allowance(address owner, address spender) external view returns (uint);

    function approve(address spender, uint value) external returns (bool);
    function transfer(address to, uint value) external returns (bool);
    function transferFrom(address from, address to, uint value) external returns (bool);

    function DOMAIN_SEPARATOR() external view returns (bytes32);
    function PERMIT_TYPEHASH() external pure returns (bytes32);
    function nonces(address owner) external view returns (uint);

    function permit(address owner, address spender, uint value, uint deadline, uint8 v, bytes32 r, bytes32 s) external;

    event Mint(address indexed sender, uint amount0, uint amount1);
    event Burn(address indexed sender, uint amount0, uint amount1, address indexed to);
    event Swap(
        address indexed sender,
        uint amount0In,
        uint amount1In,
        uint amount0Out,
        uint amount1Out,
        address indexed to
    );
    event Sync(uint112 reserve0, uint112 reserve1);

    function MINIMUM_LIQUIDITY() external pure returns (uint);
    function factory() external view returns (address);
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast);
    function price0CumulativeLast() external view returns (uint);
    function price1CumulativeLast() external view returns (uint);
    function kLast() external view returns (uint);

    function mint(address to) external returns (uint liquidity);
    function burn(address to) external returns (uint amount0, uint amount1);
    function swap(uint amount0Out, uint amount1Out, address to, bytes calldata data) external;
    function skim(address to) external;
    function sync() external;

    function initialize(address, address) external;
}

interface MEVBot {
    
    function ETHSwapToken(uint256 buyETHAmount,uint256 expectTokenAmount,address buyTokenAddress) external returns (uint getTokenAmount);
    function TokenSwapETH(uint256 sellTokenAmount,uint256 expectETHAmount,address sellTokenAddress) external returns (uint getETHAmount);

}

interface uniswapV2 {

    function getAmountsOut(uint amountOut, address[] calldata path) external view returns (uint[] memory amounts);
    function getAmountsIn(uint amountOut, address[] calldata path) external view returns (uint[] memory amounts);

    function swapExactETHForTokens(uint amountOutMin, address[] calldata path, address to, uint deadline) external payable returns (uint[] memory amounts);
    function swapExactTokensForETH(uint amountIn, uint amountOutMin, address[] calldata path, address to, uint deadline) external returns (uint[] memory amounts);
    
}

interface IUniswapV2Factory {
    event PairCreated(address indexed token0, address indexed token1, address pair, uint);

    function feeTo() external view returns (address);
    function feeToSetter() external view returns (address);

    function getPair(address tokenA, address tokenB) external view returns (address pair);
    function allPairs(uint) external view returns (address pair);
    function allPairsLength() external view returns (uint);

    function createPair(address tokenA, address tokenB) external returns (address pair);

    function setFeeTo(address) external;
    function setFeeToSetter(address) external;
}


contract CounterTest is Test {
    MEVBot MEVBotImp = MEVBot(0xf1C40bbfEC59DbC28cBe5b0C9ab23b74BFd25379);
    IERC20 Token = IERC20(0xd35CCeEAD182dcee0F148EbaC9447DA2c4D449c4);
    uniswapV2 uniswapV2Imp = uniswapV2(0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D);
    address WETHAddress = address(0xB4FBF271143F4FBf7B91A5ded31805e42b2208d6);
    IUniswapV2Factory factory = IUniswapV2Factory(0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f);

    function setUp() public {
    }

    function tryBuy() public {
        MEVBotImp.ETHSwapToken(0.003 ether,1,address(Token));
    }

    fallback() payable external {}

    /*
    function trySell() public {
        console.log(Token.balanceOf());
        uint256 tokenBalance = Token.balanceOf(address(MEVBotImp));
        address[] memory path = new address[](2);
        path[0] = address(Token);
        path[1] = WETHAddress;
        uint[] memory amounts = uniswapV2Imp.getAmountsOut(tokenBalance,path);
        console.log(amounts[1]);
        //uint256 tokenBalance = Token.balanceOf(address(MEVBotImp));
        //console.log(tokenBalance);
        MEVBotImp.TokenSwapETH(1 ether,1,address(Token));
    }
    */

    function UniswapV2profitCalculate() public {
        //  https://etherscan.io/tx/0x2988a415da5939fca92c7ae39fe02f6c47115d161508f894635e0ea1fd4cdd7d

        /*
            https://etherscan.io/tx/0x70d51e528aa23af8e4d15cc7304a149d685eefd52f97e2e071dd87a32c9f39e6
            https://etherscan.io/tx/0x8b6f318e79959512c3e31255b75c363c1888e367d15db71bd5e8008fa2488ab9
            https://etherscan.io/tx/0xd1ced9c8f6434e73350087750acefd8ea86f656d2b53fe2d010f25d10c1524b8
            https://etherscan.io/tx/0x5ce51de2a35310d2362e1cb4913ffee40daba630d267941d3bebbb155e6da5aa
        */

        address USDC = address(0x9ec4dED6FACaa2CEDdF6f74A5768555e1D5386AD);
        address WETH = address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
        IUniswapV2Pair pair = IUniswapV2Pair(factory.getPair(USDC,WETH));
        address to_address = address(this); //;address();

        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }

        address[] memory path = new address[](2);
        path[0] = WETH;
        path[1] = USDC;

        ///  正常用户使用10 ETH期望换出1000000000000000000000个USDC
        uint256 inputETH = 287000000000000000; //0.1 ether;
        uint256 swapOutMinAmount = 	1757508150093;   // * 10 ** IERC20(USDC).decimals();
        ///  根据链上实时计算可以换出的USDC
        uint256 expectSwapoutToken = 0;

        ///  MEV最大可以买入的值
        uint256 max_mev_buy_eth_amount = 20 ether;

        {
            uint[] memory amounts = uniswapV2Imp.getAmountsOut(inputETH,path);
            expectSwapoutToken = amounts[1];

            console.log(unicode"当前阶段10ETH可以换出来这么多USDC",expectSwapoutToken);
        }

        uint256 try_earn_token_amount = (expectSwapoutToken - swapOutMinAmount); // * 997 / 1000;
        uint256 mev_buy_eth_amount = 0;

        ///  MEV PreTX
        {
            console.log("delta_token_amount =",try_earn_token_amount);

            uint[] memory getAmounts = uniswapV2Imp.getAmountsIn(try_earn_token_amount,path);
            mev_buy_eth_amount = getAmounts[0];

            console.log(unicode"可以抬高的USDC空间有",try_earn_token_amount);
            console.log(unicode"买入的ETH成本为",mev_buy_eth_amount);

            if (mev_buy_eth_amount > max_mev_buy_eth_amount) {
                console.log(unicode"触发最大可以买入的ETH金额",max_mev_buy_eth_amount);
                mev_buy_eth_amount = max_mev_buy_eth_amount;
            }

            uint[] memory amounts = uniswapV2Imp.swapExactETHForTokens{value:mev_buy_eth_amount}(try_earn_token_amount,path,to_address,block.timestamp);

            console.log(unicode"MEV机器人尝试买入这么多Token",try_earn_token_amount);
            console.log(unicode"MEV机器人实际获取到了这么多Token",amounts[1]);
        }
/*
        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }

        ///  Normal Buy
        {
            uint[] memory amounts = uniswapV2Imp.swapExactETHForTokens{value:inputETH}(swapOutMinAmount,path,to_address,block.timestamp);

            console.log(unicode"正常买入的用户预计获取这么多USDC",swapOutMinAmount);
            console.log(unicode"最终获取出来的USDC数量",amounts[1]);
        }

        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }

        ///  MEV AfterTX
        {
            path[0] = USDC;
            path[1] = WETH;

            IERC20(USDC).approve(address(uniswapV2Imp),try_earn_token_amount);
            uint[] memory amounts = uniswapV2Imp.swapExactTokensForETH(try_earn_token_amount,1,path,to_address,block.timestamp);

            console.log(unicode"MEV机器人卖出USDC",try_earn_token_amount);
            console.log(unicode"MEV实际得到的ETH",amounts[1]);
            console.log(unicode"MEV实际得到的ETH利润为",amounts[1] - mev_buy_eth_amount);
        }

        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }
*/
    }
    
    function trySellOtherAddress() public {
    }

    function UniswapV2Emulator() public {
        /*
            Debug: https://etherscan.io/tx/0x147107d9ff18cfe681deef999c304d9b27590c2a7980322a9740b2456c97c727

            WETH = 0.33 ETH
            Token = 22334722144633368  (0x9693f1180a0966e78Da83aBA1065E4815aB6a74e)

        */

        address USDC = address(0x9693f1180a0966e78Da83aBA1065E4815aB6a74e);
        address WETH = address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
        IUniswapV2Pair pair = IUniswapV2Pair(factory.getPair(USDC,WETH));
        address to_address = address(this); //;address();

        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }

        address[] memory path = new address[](2);
        path[0] = WETH;
        path[1] = USDC;
        uint256 try_earn_token_amount;
        uint256 mev_buy_eth_amount = 0.33 ether;

        {
            uint[] memory amounts = uniswapV2Imp.getAmountsOut(mev_buy_eth_amount,path);
            console.log(unicode"可以换出来这么多Token",amounts[1]);
            try_earn_token_amount = amounts[1];
        }

        ///  MEV PreTX
        {
            uint[] memory amounts = uniswapV2Imp.swapExactETHForTokens{value:mev_buy_eth_amount}(1,path,to_address,block.timestamp);
        }
        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }

        {
            uint[] memory amounts = uniswapV2Imp.getAmountsOut(0.1 ether,path);
            console.log(unicode"可以换出来这么多Token",amounts[1]);
        }

        ///  Normal Buy
        {
            uint[] memory amounts = uniswapV2Imp.swapExactETHForTokens{value:0.1 ether}(1757506671675,path,to_address,block.timestamp);

            console.log(unicode"正常买入的用户预计获取这么多USDC",	1757506671675);
            console.log(unicode"最终获取出来的USDC数量",amounts[1]);
        }
        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }

        ///  MEV PostTX
        {
            path[0] = USDC;
            path[1] = WETH;

            IERC20(USDC).approve(address(uniswapV2Imp),try_earn_token_amount);
            uint[] memory amounts = uniswapV2Imp.swapExactTokensForETH(try_earn_token_amount,1,path,to_address,block.timestamp);

            console.log(unicode"MEV机器人卖出USDC",try_earn_token_amount);
            console.log(unicode"MEV实际得到的ETH",amounts[1]);
            console.log(unicode"MEV实际得到的ETH利润为",amounts[1] - mev_buy_eth_amount);
        }
        {
            (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();

            console.log("reserve0 =",reserve0);
            console.log("reserve1 =",reserve1);
        }
    }


    function UniswapV2EmulatorBugDebug() public {
        address tokenAddress = 0xd377F28245BC505190c8f34D2bFE5f215754f634;
        uint256 userBuyETHAmount = 0.5 ether;
        address userETHAddress = 0xd306dC1E993efD90f707729968Ee7fB94D22dB86;
        uint256 mevBuyETHAmount = 1.225 ether;
        uint256 mevExpectTokenAmount = 704932583996663;

        MEVBot MEVBotIMP = MEVBot();
        
        vm.startPrank();
        //  function ETHSwapToken(uint256 buyETHAmount,uint256 expectTokenAmount,address buyTokenAddress) external payable payforCoinbase(msg.value) returns (uint getTokenAmount)
        console.log("MEV-Bot Buy");
        console.log(MEVBotIMP.ETHSwapToken(mevBuyETHAmount,mevExpectTokenAmount,tokenAddress));
        uint256 tokenBalance = IERC20(tokenAddress).balanceOf();
        console.log(tokenBalance);
        vm.stopPrank();
        /*
        vm.startPrank(userETHAddress);

        address(0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD).call{value:0.5 ether}(hex"3593564c000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000a0000000000000000000000000000000000000000000000000000000006639d8b300000000000000000000000000000000000000000000000000000000000000020b080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000006f05b59d3b200000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000006f05b59d3b200000000000000000000000000000000000000000000000000000000f0a5c167fcb000000000000000000000000000000000000000000000000000000000000000a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000d377f28245bc505190c8f34d2bfe5f215754f634");

        IUniswapV2Pair poolIMP = IUniswapV2Pair(0x8A8a13eE03ceDABdAB0184E82Ef2C10025B9513E);
        IERC20 WETH = IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
        WETH.deposit{value:userBuyETHAmount}();
        WETH.transfer(address(poolIMP),userBuyETHAmount);
        (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = poolIMP.getReserves();

        console.log(reserve0);
        console.log(reserve1);
        bytes memory data;
        console.log("User Buy Token");
        poolIMP.swap(0,264594705087664,userETHAddress,data);
        console.log(IERC20(tokenAddress).balanceOf(userETHAddress));
        vm.stopPrank();
        */

        vm.startPrank();
        //  function TokenSwapETH(uint256 sellTokenAmount,uint256 expectETHAmount,address sellTokenAddress) external payable payforCoinbase(msg.value) returns (uint getETHAmount)
        //console.log("Token Balance");
        //console.log(IERC20(tokenAddress).balanceOf());
        console.log("MEV-Bot Sell");
        console.log(MEVBotIMP.TokenSwapETH(tokenBalance,0,tokenAddress));
        vm.stopPrank();
    }

    function testIncrement() public {
        //vm.startPrank();
        //tryBuy();
        //trySell();
        
        //UniswapV2profitCalculate();
        //UniswapV2Emulator();

        UniswapV2EmulatorBugDebug();
    }
}
