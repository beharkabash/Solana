"""
BNB Chain (BSC) Blockchain Monitor
Monitors PancakeSwap for new token launches
"""

import asyncio
import logging
import os
import json
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime
import aiohttp
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.middleware import async_geth_poa_middleware
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BNBMonitor:
    """Monitor BNB Chain for new token launches"""

    # PancakeSwap Factory Addresses
    PANCAKE_V2_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
    PANCAKE_V3_FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"

    # PancakeSwap Router Addresses
    PANCAKE_V2_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
    PANCAKE_V3_ROUTER = "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4"

    # Token addresses on BSC
    WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    BUSD = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
    USDT = "0x55d398326f99059fF775485246999027B3197955"
    USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"

    # Event signatures (same as Uniswap)
    PAIR_CREATED_TOPIC = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
    POOL_CREATED_TOPIC = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"

    def __init__(self):
        """Initialize BNB Chain monitor"""
        self.rpc_url = os.getenv('BNB_RPC_HTTP')
        self.wss_url = os.getenv('BNB_RPC_WSS')
        self.w3: Optional[AsyncWeb3] = None
        self.session: Optional[aiohttp.ClientSession] = None

        # Track processed blocks and transactions
        self.last_block = None
        self.processed_txs = set()

        # Cache for token metadata
        self.token_metadata_cache = {}

        # ABI for minimal BEP20 interface (same as ERC20)
        self.bep20_abi = [
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

        logger.info("BNB Chain monitor initialized")

    async def initialize(self):
        """Initialize Web3 connection to BSC"""
        try:
            self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))

            # BSC is a POA chain, add middleware
            self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

            # Test connection
            is_connected = await self.w3.is_connected()
            if is_connected:
                chain_id = await self.w3.eth.chain_id
                latest_block = await self.w3.eth.block_number
                self.last_block = latest_block - 10  # Start from 10 blocks ago
                logger.info(f"Connected to BNB Chain (Chain ID: {chain_id}, Block: {latest_block})")
            else:
                raise Exception("Failed to connect to BNB Chain RPC")

            self.session = aiohttp.ClientSession()

        except Exception as e:
            logger.error(f"Error initializing BNB Chain client: {e}")
            raise

    async def cleanup(self):
        """Clean up connections"""
        if self.session:
            await self.session.close()

    async def get_token_metadata(self, token_address: str) -> Dict:
        """Get BEP20 token metadata"""
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
            contract = self.w3.eth.contract(address=checksum_address, abi=self.bep20_abi)

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

    async def get_pancake_v2_pairs(self, from_block: int, to_block: int) -> List[Dict]:
        """Get new PancakeSwap V2 pairs created"""
        pairs = []

        try:
            # Get PairCreated events
            factory_address = self.w3.to_checksum_address(self.PANCAKE_V2_FACTORY)

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

                    # Check if one of the tokens is WBNB/BUSD/USDT/USDC
                    base_tokens = [self.WBNB, self.BUSD, self.USDT, self.USDC]
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

                    # Skip obvious scams (optional basic filter)
                    if metadata.get('symbol', '').lower() in ['test', 'testing', 'fake']:
                        continue

                    pairs.append({
                        'dex': 'PancakeSwap V2',
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
                    logger.debug(f"Error parsing PancakeSwap V2 log: {e}")

        except Exception as e:
            logger.error(f"Error getting PancakeSwap V2 pairs: {e}")

        return pairs

    async def get_pancake_v3_pools(self, from_block: int, to_block: int) -> List[Dict]:
        """Get new PancakeSwap V3 pools created"""
        pools = []

        try:
            factory_address = self.w3.to_checksum_address(self.PANCAKE_V3_FACTORY)

            logs = await self.w3.eth.get_logs({
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': factory_address,
                'topics': [self.POOL_CREATED_TOPIC]
            })

            for log in logs:
                try:
                    # Decode the log
                    token0 = '0x' + log['topics'][1].hex()[26:]
                    token1 = '0x' + log['topics'][2].hex()[26:]
                    pool_address = '0x' + log['data'].hex()[26:66]

                    # Check if one of the tokens is WBNB/BUSD/USDT/USDC
                    base_tokens = [self.WBNB, self.BUSD, self.USDT, self.USDC]
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
                        'dex': 'PancakeSwap V3',
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
                    logger.debug(f"Error parsing PancakeSwap V3 log: {e}")

        except Exception as e:
            logger.error(f"Error getting PancakeSwap V3 pools: {e}")

        return pools

    async def check_honeypot(self, token_address: str) -> Dict:
        """Basic honeypot check (simplified)"""
        # In production, you would:
        # 1. Check if contract is verified
        # 2. Simulate buy/sell transactions
        # 3. Check for malicious functions
        # 4. Use external honeypot detection APIs

        return {
            'is_honeypot': False,
            'buy_tax': 0,
            'sell_tax': 0,
            'warnings': []
        }

    async def get_pool_liquidity(self, pool_address: str, dex_version: int) -> Optional[float]:
        """Get pool liquidity in USD"""
        try:
            checksum_address = self.w3.to_checksum_address(pool_address)
            
            # Uniswap V2 style pair contract ABI (for getReserves)
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
            
            # WBNB address on BSC
            WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c".lower()
            
            # Estimate USD value
            # If one token is WBNB, use BNB price (~$600)
            bnb_price_usd = 600.0  # TODO: Get from price oracle like CoinGecko or Binance
            
            if token0.lower() == WBNB:
                liquidity_usd = reserve0 * bnb_price_usd * 2
            elif token1.lower() == WBNB:
                liquidity_usd = reserve1 * bnb_price_usd * 2
            else:
                # Estimate based on total reserves (less accurate)
                liquidity_usd = (reserve0 + reserve1) * 100  # Rough estimate
            
            return liquidity_usd if liquidity_usd > 0 else None

        except Exception as e:
            logger.debug(f"Error getting pool liquidity for {pool_address}: {e}")
            return None

    async def monitor(self) -> AsyncGenerator[Dict, None]:
        """Monitor for new tokens on BNB Chain"""
        await self.initialize()

        try:
            while True:
                try:
                    # Get current block
                    current_block = await self.w3.eth.block_number

                    if self.last_block and current_block > self.last_block:
                        # Process new blocks
                        from_block = self.last_block + 1
                        to_block = min(current_block, self.last_block + 50)  # Process max 50 blocks at a time

                        # Get new pairs/pools from both PancakeSwap versions
                        v2_pairs = await self.get_pancake_v2_pairs(from_block, to_block)
                        v3_pools = await self.get_pancake_v3_pools(from_block, to_block)

                        # Combine and process
                        all_pools = v2_pairs + v3_pools

                        for pool in all_pools:
                            # Skip if already processed
                            tx_hash = pool.get('transaction_hash')
                            if tx_hash in self.processed_txs:
                                continue

                            # Add chain-specific data
                            pool['chain'] = 'bnb'
                            pool['chain_id'] = 56
                            pool['discovered_at'] = datetime.now().isoformat()

                            # Get liquidity
                            liquidity = await self.get_pool_liquidity(
                                pool.get('pool_address', pool.get('pair_address')),
                                pool.get('version', 2)
                            )
                            pool['liquidity_usd'] = liquidity

                            # Honeypot check (optional)
                            honeypot_check = await self.check_honeypot(pool.get('new_token', ''))
                            pool['honeypot_check'] = honeypot_check

                            # Add explorer links
                            token_address = pool.get('new_token', pool.get('address', ''))
                            pool['explorer_link'] = f"https://bscscan.com/token/{token_address}"
                            pool['dexscreener_link'] = f"https://dexscreener.com/bsc/{token_address}"
                            pool['poocoin_link'] = f"https://poocoin.app/tokens/{token_address}"

                            logger.info(f"New BNB Chain token discovered: {pool.get('symbol', 'Unknown')} on {pool.get('dex', 'Unknown')}")

                            self.processed_txs.add(tx_hash)
                            yield pool

                        # Update last block
                        self.last_block = to_block

                    # Wait before next check
                    await asyncio.sleep(3)  # BSC has faster blocks

                except Exception as e:
                    logger.error(f"Error in BNB Chain monitoring loop: {e}")
                    await asyncio.sleep(30)

        finally:
            await self.cleanup()