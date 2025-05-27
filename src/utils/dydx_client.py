from dydx3 import Client
from web3 import Web3
import os
from dotenv import load_dotenv

load_dotenv(override=True)

def get_dydx_client():
    return Client(
        host="https://api.dydx.exchange",
        api_key_credentials={
            "key": os.getenv("DYDX_API_KEY"),
            "secret": os.getenv("DYDX_API_SECRET"),
            "passphrase": os.getenv("DYDX_API_PASSPHRASE"),
        },
        stark_private_key=os.getenv("DYDX_STARK_PRIVATE_KEY"),
        eth_private_key=os.getenv("ETH_PRIVATE_KEY"),
        default_ethereum_address=os.getenv("ETHEREUM_ADDRESS"),
        web3=Web3(Web3.HTTPProvider("https://eth-mainnet.g.alchemy.com/v2/TON_ALCHEMY_KEY"))
    )
