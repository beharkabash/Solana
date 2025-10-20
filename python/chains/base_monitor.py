"""
Base Blockchain Monitor
Monitors Aerodrome and Uniswap on Base for new token launches
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


class BaseMonitor:
    """Monitor Base blockchain for new token launches"""

    # Aerodrome Finance Factory
    AERODROME_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
    AERODROME_ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"

    # Uniswap on Base
    UNISWAP_V3_FACTORY_BASE = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
    UNISWAP_V2_FACTORY_BASE = "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6"

    # BaseSwap (alternative DEX on Base)
    BASESWAP_FACTORY = "0xFDa619b6d20975be80A10332dC0C9E4A5e28Cd50"

    # Token addresses on Base
    WETH = "0x4200000000000000000000000000000000000006"  # WETH on Base
    USDC = "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA"  # USDbC (bridged USDC)
    USDC_NATIVE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Native USDC on Base
    DAI = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"  # DAI on Base

    # Event signatures
    PAIR_CREATED_TOPIC = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
    POOL_CREATED_TOPIC = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
    # Aerodrome uses different event signature
    AERODROME_POOL_CREATED = "0x2128d88d14c80cb081c1252012fd9b00229b2cbb09e4d8d417e9c53e2b642c48"

    def __init__(self):
        """Initialize Base monitor"""
        self.rpc_url = os.getenv('BASE_RPC_HTTP')
        self.wss_url = os.getenv('BASE_RPC_WSS')
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

        logger.info("Base monitor initialized")

    async def initialize(self):
        """Initialize Web3 connection to Base"""
        try:
            self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))

            # Add middleware if needed
            self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

            # Test connection
            is_connected = await self.w3.is_connected()
            if is_connected:
                chain_id = await self.w3.eth.chain_id
                latest_block = await self.w3.eth.block_number
                self.last_block = latest_block - 10  # Start from 10 blocks ago
                logger.info(f"Connected to Base (Chain ID: {chain_id}, Block: {latest_block})")
            else:
                raise Exception("Failed to connect to Base RPC")

            self.session = aiohttp.ClientSession()

        except Exception as e:
            logger.error(f"Error initializing Base client: {e}")
            raise

    async def cleanup(self):
        """Clean up connections"""
        if self.session:
            await self.session.close()

    async def get_token_metadata(self, token_address: str) -> Dict:
        """Get ERC20 token metadata on Base"""
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

    async def get_aerodrome_pools(self, from_block: int, to_block: int) -> List[Dict]:
        """Get new Aerodrome pools created"""
        pools = []

        try:
            factory_address = self.w3.to_checksum_address(self.AERODROME_FACTORY)

            # Get pool creation events
            logs = await self.w3.eth.get_logs({
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': factory_address
            })

            for log in logs:
                try:
                    # Parse Aerodrome pool creation event
                    if len(log['topics']) >= 3:
                        token0 = '0x' + log['topics'][1].hex()[26:]
                        token1 = '0x' + log['topics'][2].hex()[26:]

                        # Extract pool address from data
                        if len(log['data'].hex()) >= 66:
                            pool_address = '0x' + log['data'].hex()[26:66]
                        else:
                            continue

                        # Check if one of the tokens is WETH/USDC/DAI
                        base_tokens = [self.WETH, self.USDC, self.USDC_NATIVE, self.DAI]
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
                            'dex': 'Aerodrome',
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
                    logger.debug(f"Error parsing Aerodrome log: {e}")

        except Exception as e:
            logger.error(f"Error getting Aerodrome pools: {e}")

        return pools

    async def get_uniswap_pools(self, from_block: int, to_block: int) -> List[Dict]:
        """Get new Uniswap pools on Base"""
        pools = []

        try:
            # Check Uniswap V3 on Base
            factory_address = self.w3.to_checksum_address(self.UNISWAP_V3_FACTORY_BASE)

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

                    # Check if one of the tokens is a base token
                    base_tokens = [self.WETH, self.USDC, self.USDC_NATIVE, self.DAI]
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
                        'dex': 'Uniswap V3 (Base)',
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
                    logger.debug(f"Error parsing Uniswap Base log: {e}")

        except Exception as e:
            logger.error(f"Error getting Uniswap pools on Base: {e}")

        return pools

    async def get_baseswap_pairs(self, from_block: int, to_block: int) -> List[Dict]:
        """Get new BaseSwap pairs created"""
        pairs = []

        try:
            factory_address = self.w3.to_checksum_address(self.BASESWAP_FACTORY)

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

                    # Check if one of the tokens is a base token
                    base_tokens = [self.WETH, self.USDC, self.USDC_NATIVE, self.DAI]
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

                    pairs.append({
                        'dex': 'BaseSwap',
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
                    logger.debug(f"Error parsing BaseSwap log: {e}")

        except Exception as e:
            logger.error(f"Error getting BaseSwap pairs: {e}")

        return pairs

    async def get_pool_liquidity(self, pool_address: str, dex: str) -> Optional[float]:
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
            
            # WETH address on Base
            WETH = "0x4200000000000000000000000000000000000006".lower()
            
            # Estimate USD value
            # If one token is WETH, use ETH price (~$3500)
            eth_price_usd = 3500.0  # TODO: Get from price oracle
            
            if token0.lower() == WETH:
                liquidity_usd = reserve0 * eth_price_usd * 2
            elif token1.lower() == WETH:
                liquidity_usd = reserve1 * eth_price_usd * 2
            else:
                # Estimate based on total reserves (less accurate)
                liquidity_usd = (reserve0 + reserve1) * 50  # Conservative estimate for Base
            
            return liquidity_usd if liquidity_usd > 0 else None

        except Exception as e:
            logger.debug(f"Error getting pool liquidity for {pool_address}: {e}")
            return None

    async def monitor(self) -> AsyncGenerator[Dict, None]:
        """Monitor for new tokens on Base"""
        await self.initialize()

        try:
            while True:
                try:
                    # Get current block
                    current_block = await self.w3.eth.block_number

                    if self.last_block and current_block > self.last_block:
                        # Process new blocks
                        from_block = self.last_block + 1
                        to_block = min(current_block, self.last_block + 100)  # Process max 100 blocks

                        # Get new pools from all DEXs on Base
                        aerodrome_pools = await self.get_aerodrome_pools(from_block, to_block)
                        uniswap_pools = await self.get_uniswap_pools(from_block, to_block)
                        baseswap_pairs = await self.get_baseswap_pairs(from_block, to_block)

                        # Combine all pools
                        all_pools = aerodrome_pools + uniswap_pools + baseswap_pairs

                        for pool in all_pools:
                            # Skip if already processed
                            tx_hash = pool.get('transaction_hash')
                            if tx_hash in self.processed_txs:
                                continue

                            # Add chain-specific data
                            pool['chain'] = 'base'
                            pool['chain_id'] = 8453
                            pool['discovered_at'] = datetime.now().isoformat()

                            # Get liquidity
                            liquidity = await self.get_pool_liquidity(
                                pool.get('pool_address', pool.get('pair_address')),
                                pool.get('dex', 'Unknown')
                            )
                            pool['liquidity_usd'] = liquidity

                            # Add explorer links
                            token_address = pool.get('new_token', pool.get('address', ''))
                            pool['explorer_link'] = f"https://basescan.org/token/{token_address}"
                            pool['dexscreener_link'] = f"https://dexscreener.com/base/{token_address}"

                            # Add Base-specific info
                            pool['is_base_native'] = True  # All tokens on Base are native to Base

                            logger.info(f"New Base token discovered: {pool.get('symbol', 'Unknown')} on {pool.get('dex', 'Unknown')}")

                            self.processed_txs.add(tx_hash)
                            yield pool

                        # Update last block
                        self.last_block = to_block

                    # Wait before next check
                    await asyncio.sleep(2)  # Base has fast block times

                except Exception as e:
                    logger.error(f"Error in Base monitoring loop: {e}")
                    await asyncio.sleep(30)

        finally:
            await self.cleanup()