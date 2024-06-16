// We require the Hardhat Runtime Environment explicitly here. This is optional
// but useful for running the script in a standalone fashion through `node <script>`.
//
// You can also run a script with `npx hardhat run <script>`. If you do that, Hardhat
// will compile your contracts, add the Hardhat Runtime Environment's members to the
// global scope, and execute the script.
const hre = require("hardhat");

async function main() {
  const SignerImp = await hre.ethers.getSigner();
  const WalletAddress = SignerImp.address;
  
  console.log(" >>> ==== deployContract() ====");

  const MEVBot = await hre.ethers.getContractFactory("MEVBot");
  const MEVBotImp = await MEVBot.deploy();
  await MEVBotImp.deployed();

  console.log(`Deploy Address MEVBot: ${MEVBotImp.address}`);
  
  const sendETHValue = ethers.utils.parseEther('0.01');
  const tx = await SignerImp.sendTransaction({
    to: MEVBotImp.address,
    value: sendETHValue,
  });
  await tx.wait();

  console.log(" <<< ==== deployContract() ====");
}

// We recommend this pattern to be able to use async/await everywhere
// and properly handle errors.
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
