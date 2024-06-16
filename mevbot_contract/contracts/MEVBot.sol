// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;


import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";

import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";


contract MEVBot {

    //  Mainnet
    address WETHAddress = address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    //address WETHAddress = address(0xB4FBF271143F4FBf7B91A5ded31805e42b2208d6);
    address owner;

    IUniswapV2Router02 public UniswapV2Router = IUniswapV2Router02(0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D);

    //  https://docs.flashbots.net/flashbots-auction/advanced/coinbase-payment

    modifier payforCoinbase(uint256 ethValue) {
        block.coinbase.transfer(ethValue);
        _;
    }

    receive() external payable {
    }

    constructor() {
        owner = msg.sender;
    }

    function ETHSwapToken(uint256 buyETHAmount,uint256 expectTokenAmount,address buyTokenAddress) external payable payforCoinbase(msg.value) returns (uint getTokenAmount) {
        require(msg.sender == owner,"6");
        require(buyETHAmount <= address(this).balance,"Value too low");

        address[] memory path = new address[](2);
        path[0] = WETHAddress;
        path[1] = buyTokenAddress;

        uint[] memory realAmounts = UniswapV2Router.swapExactETHForTokens{value:buyETHAmount}(expectTokenAmount,path,address(this),block.timestamp);

        getTokenAmount = realAmounts[1];
    }

    function TokenSwapETH(uint256 sellTokenAmount,uint256 expectETHAmount,address sellTokenAddress) external payable payforCoinbase(msg.value) returns (uint getETHAmount) {
        require(msg.sender == owner,"6");
        require(sellTokenAmount <= IERC20(sellTokenAddress).balanceOf(address(this)),"Value too low");  //  对于一些收税币,这里会revert

        address[] memory path = new address[](2);
        path[0] = sellTokenAddress;
        path[1] = WETHAddress;

        IERC20(sellTokenAddress).approve(address(UniswapV2Router),sellTokenAmount);
        uint[] memory realAmounts = UniswapV2Router.swapExactTokensForETH(sellTokenAmount,expectETHAmount,path,address(this),block.timestamp);

        getETHAmount = realAmounts[1];
    }

    function WithdrawETH(uint256 amount) external {
        require(msg.sender == owner,"6");
        payable(msg.sender).transfer(amount);
    }

    function WithdrawToken(uint256 amount,address tokenAddress) external {
        require(msg.sender == owner,"6");
        IERC20(tokenAddress).transfer(msg.sender,amount);
    }

}
