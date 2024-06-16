require("@nomicfoundation/hardhat-toolbox");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  defaultNetwork: "localhost",
  networks: {
    eth_goerli: {
      url: "https://winter-necessary-county.ethereum-goerli.quiknode.pro//",
      ethNetwork: 'goerli',
      accounts: [ process.env.pk ],
      gasPrice: 20000000000   ///  20Gwei
    },
    eth: {
      url: "https://burned-sly-dew.quiknode.pro//",
      ethNetwork: 'mainnet',
      accounts: [ process.env.pk ],
    },
  },
  solidity: "0.8.4",
};

