"""
Ethereum Blockchain Monitor
Monitors Uniswap V2/V3 for new token launches
"""

import asyncio
import logging
import os
import json
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime
import aiohttp
from web3 import Web3, HTTPProvider
from web3.exceptions import TransactionNotFound
from web3.middleware import geth_poa_middleware
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class EthereumMonitor:
    """Monitor Ethereum blockchain for new token launches"""

    # Uniswap Factory Addresses
    UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

    # Uniswap Router Addresses
    UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
    UNISWAP_V3_ROUTER = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"

    # Token addresses
    WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    DAI = "0x6B175474E89094C44Da98b954EedeAC495271d0F"

    # Event signatures
    PAIR_CREATED_TOPIC = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"  # PairCreated
    POOL_CREATED_TOPIC = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"  # PoolCreated

    def __init__(self):
        """Initialize Ethereum monitor"""
        self.rpc_url = os.getenv('ETHEREUM_RPC_HTTP')
        self.wss_url = os.getenv('ETHEREUM_RPC_WSS')
        self.w3: Optional[AsyncWeb3] = None
        self.session: Optional[aiohttp.ClientSession] = None

        # Track processed blocks and transactions
        self.last_block = None
        self.processed_txs = set()

        # Cache for token metadata
        self.token_metadata_cache = {}

        # ABI for minimal ERC20 interface
        self.erc20_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "totalSupply",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            }
        ]

        # Uniswap V2 Factory ABI (minimal)
        self.factory_v2_abi = [
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "token0", "type": "address"},
                    {"indexed": True, "name": "token1", "type": "address"},
                    {"indexed": False, "name": "pair", "type": "address"},
                    {"indexed": False, "name": "uint", "type": "uint256"}
                ],
                "name": "PairCreated",
                "type": "event"
            }
        ]

        logger.info("Ethereum monitor initialized")

    async def initialize(self):
        """Initialize Web3 connection"""
        try:
            self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))

            # Add middleware for POA chains if needed
            self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

            # Test connection
            is_connected = await self.w3.is_connected()
            if is_connected:
                chain_id = await self.w3.eth.chain_id
                latest_block = await self.w3.eth.block_number
                self.last_block = latest_block - 10  # Start from 10 blocks ago
                logger.info(f"Connected to Ethereum (Chain ID: {chain_id}, Block: {latest_block})")
            else:
                raise Exception("Failed to connect to Ethereum RPC")

            self.session = aiohttp.ClientSession()

        except Exception as e:
            logger.error(f"Error initializing Ethereum client: {e}")
            raise

    async def cleanup(self):
        """Clean up connections"""
        if self.session:
            await self.session.close()

    async def get_token_metadata(self, token_address: str) -> Dict:
        """Get ERC20 token metadata"""
        try:
            # Check cache first
            if token_address in self.token_metadata_cache:
                return self.token_metadata_cache[token_address]

            metadata = {
                'address': token_address,
                'symbol': 'Unknown',
                'name': 'Unknown',
                'decimals': 18,
                'total_supply': 0
            }

            # Create contract instance
            checksum_address = self.w3.to_checksum_address(token_address)
            contract = self.w3.eth.contract(address=checksum_address, abi=self.erc20_abi)

            # Try to get token info
            try:
                # Get all metadata in parallel
                results = await asyncio.gather(
                    contract.functions.symbol().call(),
                    contract.functions.name().call(),
                    contract.functions.decimals().call(),
                    contract.functions.totalSupply().call(),
                    return_exceptions=True
                )

                if not isinstance(results[0], Exception):
                    metadata['symbol'] = results[0]
                if not isinstance(results[1], Exception):
                    metadata['name'] = results[1]
                if not isinstance(results[2], Exception):
                    metadata['decimals'] = results[2]
                if not isinstance(results[3], Exception):
                    metadata['total_supply'] = results[3]

            except Exception as e:
                logger.debug(f"Error getting token metadata for {token_address}: {e}")

            # Cache the metadata
            self.token_metadata_cache[token_address] = metadata
            return metadata

        except Exception as e:
            logger.error(f"Error getting token metadata for {token_address}: {e}")
            return {
                'address': token_address,
                'symbol': 'Unknown',
                'name': 'Unknown'
            }

    async def get_uniswap_v2_pairs(self, from_block: int, to_block: int) -> List[Dict]:
        """Get new Uniswap V2 pairs created"""
        pairs = []

        try:
            # Get PairCreated events
            factory_address = self.w3.to_checksum_address(self.UNISWAP_V2_FACTORY)

            logs = await self.w3.eth.get_logs({
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': factory_address,
                'topics': [self.PAIR_CREATED_TOPIC]
            })

            for log in logs:
                try:
                    # Decode the log
                    token0 = '0x' + log['topics'][1].hex()[26:]
                    token1 = '0x' + log['topics'][2].hex()[26:]
                    pair_address = '0x' + log['data'].hex()[26:66]

                    # Check if one of the tokens is WETH/USDC/USDT/DAI
                    base_tokens = [self.WETH, self.USDC, self.USDT, self.DAI]
                    base_token = None
                    new_token = None

                    if token0.lower() in [t.lower() for t in base_tokens]:
                        base_token = token0
                        new_token = token1
                    elif token1.lower() in [t.lower() for t in base_tokens]:
                        base_token = token1
                        new_token = token0
                    else:
                        # Skip if no recognized base token
                        continue

                    # Get token metadata
                    metadata = await self.get_token_metadata(new_token)

                    pairs.append({
                        'dex': 'Uniswap V2',
                        'version': 2,
                        'pair_address': pair_address,
                        'token0': token0,
                        'token1': token1,
                        'new_token': new_token,
                        'base_token': base_token,
                        'block_number': log['blockNumber'],
                        'transaction_hash': log['transactionHash'].hex(),
                        **metadata
                    })

                except Exception as e:
                    logger.debug(f"Error parsing Uniswap V2 log: {e}")

        except Exception as e:
            logger.error(f"Error getting Uniswap V2 pairs: {e}")

        return pairs

    async def get_uniswap_v3_pools(self, from_block: int, to_block: int) -> List[Dict]:
        """Get new Uniswap V3 pools created"""
        pools = []

        try:
            factory_address = self.w3.to_checksum_address(self.UNISWAP_V3_FACTORY)

            logs = await self.w3.eth.get_logs({
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': factory_address,
                'topics': [self.POOL_CREATED_TOPIC]
            })

            for log in logs:
                try:
                    # Decode the log (V3 has different structure)
                    token0 = '0x' + log['topics'][1].hex()[26:]
                    token1 = '0x' + log['topics'][2].hex()[26:]
                    # Fee tier is in topics[3]
                    pool_address = '0x' + log['data'].hex()[26:66]

                    # Check if one of the tokens is WETH/USDC/USDT/DAI
                    base_tokens = [self.WETH, self.USDC, self.USDT, self.DAI]
                    base_token = None
                    new_token = None

                    if token0.lower() in [t.lower() for t in base_tokens]:
                        base_token = token0
                        new_token = token1
                    elif token1.lower() in [t.lower() for t in base_tokens]:
                        base_token = token1
                        new_token = token0
                    else:
                        continue

                    # Get token metadata
                    metadata = await self.get_token_metadata(new_token)

                    pools.append({
                        'dex': 'Uniswap V3',
                        'version': 3,
                        'pool_address': pool_address,
                        'token0': token0,
                        'token1': token1,
                        'new_token': new_token,
                        'base_token': base_token,
                        'block_number': log['blockNumber'],
                        'transaction_hash': log['transactionHash'].hex(),
                        **metadata
                    })

                except Exception as e:
                    logger.debug(f"Error parsing Uniswap V3 log: {e}")

        except Exception as e:
            logger.error(f"Error getting Uniswap V3 pools: {e}")

        return pools

    async def get_pool_liquidity(self, pool_address: str, dex_version: int) -> Optional[float]:
        """Get pool liquidity in USD"""
        try:
            checksum_address = self.w3.to_checksum_address(pool_address)
            
            # Uniswap V2 style pair contract ABI
            pair_abi = [
                {
                    "constant": True,
                    "inputs": [],
                    "name": "getReserves",
                    "outputs": [
                        {"name": "reserve0", "type": "uint112"},
                        {"name": "reserve1", "type": "uint112"},
                        {"name": "blockTimestampLast", "type": "uint32"}
                    ],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "token0",
                    "outputs": [{"name": "", "type": "address"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "token1",
                    "outputs": [{"name": "", "type": "address"}],
                    "type": "function"
                }
            ]
            
            pair_contract = self.w3.eth.contract(address=checksum_address, abi=pair_abi)
            
            # Get reserves
            reserves = await pair_contract.functions.getReserves().call()
            reserve0 = reserves[0] / 1e18
            reserve1 = reserves[1] / 1e18
            
            # Get token addresses
            token0 = await pair_contract.functions.token0().call()
            token1 = await pair_contract.functions.token1().call()
            
            # WETH address on Ethereum mainnet
            WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2".lower()
            
            # Estimate USD value
            # If one token is WETH, use ETH price (~$3500)
            eth_price_usd = 3500.0  # TODO: Get from price oracle like CoinGecko or Chainlink
            
            if token0.lower() == WETH:
                liquidity_usd = reserve0 * eth_price_usd * 2
            elif token1.lower() == WETH:
                liquidity_usd = reserve1 * eth_price_usd * 2
            else:
                # Estimate based on total reserves (less accurate for non-ETH pairs)
                liquidity_usd = (reserve0 + reserve1) * 200  # Rough estimate
            
            return liquidity_usd if liquidity_usd > 0 else None

        except Exception as e:
            logger.debug(f"Error getting pool liquidity for {pool_address}: {e}")
            return None

    async def monitor(self) -> AsyncGenerator[Dict, None]:
        """Monitor for new tokens"""
        await self.initialize()

        try:
            while True:
                try:
                    # Get current block
                    current_block = await self.w3.eth.block_number

                    if self.last_block and current_block > self.last_block:
                        # Process new blocks
                        from_block = self.last_block + 1
                        to_block = min(current_block, self.last_block + 100)  # Process max 100 blocks at a time

                        # Get new pairs/pools from both Uniswap versions
                        v2_pairs = await self.get_uniswap_v2_pairs(from_block, to_block)
                        v3_pools = await self.get_uniswap_v3_pools(from_block, to_block)

                        # Combine and process
                        all_pools = v2_pairs + v3_pools

                        for pool in all_pools:
                            # Skip if already processed
                            tx_hash = pool.get('transaction_hash')
                            if tx_hash in self.processed_txs:
                                continue

                            # Add chain-specific data
                            pool['chain'] = 'ethereum'
                            pool['chain_id'] = 1
                            pool['discovered_at'] = datetime.now().isoformat()

                            # Get liquidity
                            liquidity = await self.get_pool_liquidity(
                                pool.get('pool_address', pool.get('pair_address')),
                                pool.get('version', 2)
                            )
                            pool['liquidity_usd'] = liquidity

                            # Add explorer links
                            token_address = pool.get('new_token', pool.get('address', ''))
                            pool['explorer_link'] = f"https://etherscan.io/token/{token_address}"
                            pool['dexscreener_link'] = f"https://dexscreener.com/ethereum/{token_address}"

                            logger.info(f"New Ethereum token discovered: {pool.get('symbol', 'Unknown')} on {pool.get('dex', 'Unknown')}")

                            self.processed_txs.add(tx_hash)
                            yield pool

                        # Update last block
                        self.last_block = to_block

                    # Wait before next check
                    await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Error in Ethereum monitoring loop: {e}")
                    await asyncio.sleep(30)

        finally:
            await self.cleanup()