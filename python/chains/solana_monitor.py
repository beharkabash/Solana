#!/usr/bin/env python3
"""
Solana Blockchain Monitor
Monitors Raydium and Pump.fun for new token launches
"""

import asyncio
import logging
import os
import json
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.pubkey import Pubkey
from solders.signature import Signature
import base58
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class SolanaMonitor:
    """Monitor Solana blockchain for new token launches"""

    # Raydium AMM Program IDs
    RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    RAYDIUM_CPMM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"

    # Pump.fun Program ID
    PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwbWqk"

    # Token Program IDs
    TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

    def __init__(self):
        """Initialize Solana monitor"""
        self.rpc_url = os.getenv('SOLANA_RPC_HTTP')
        self.wss_url = os.getenv('SOLANA_RPC_WSS')
        self.client: Optional[AsyncClient] = None
        self.session: Optional[aiohttp.ClientSession] = None

        # Track processed transactions
        self.processed_signatures = set()
        self.last_signature: Optional[str] = None

        # Cache for token metadata
        self.token_metadata_cache = {}

        logger.info("Solana monitor initialized")

    async def initialize(self):
        """Initialize connections"""
        try:
            self.client = AsyncClient(self.rpc_url)
            self.session = aiohttp.ClientSession()
            logger.info("Solana RPC client initialized")
        except Exception as e:
            logger.error(f"Error initializing Solana client: {e}")
            raise

    async def cleanup(self):
        """Clean up connections"""
        if self.client:
            await self.client.close()
        if self.session:
            await self.session.close()

    async def get_token_metadata(self, mint_address: str) -> Dict:
        """Get token metadata from various sources"""
        try:
            # Check cache first
            if mint_address in self.token_metadata_cache:
                return self.token_metadata_cache[mint_address]

            metadata = {
                'address': mint_address,
                'symbol': 'Unknown',
                'name': 'Unknown',
                'decimals': 9,
                'total_supply': 0
            }

            # Get account info
            try:
                mint_pubkey = Pubkey.from_string(mint_address)
                account_info = await self.client.get_account_info(mint_pubkey)

                if account_info and account_info.value:
                    # Parse token mint data
                    data = account_info.value.data
                    if len(data) >= 82:
                        # Basic token mint structure parsing
                        metadata['decimals'] = int(data[44])

            except Exception as e:
                logger.debug(f"Error getting mint info for {mint_address}: {e}")

            # Try to get metadata from Solana token list or API
            try:
                async with self.session.get(
                    f"https://api.solana.fm/v0/tokens/{mint_address}",
                    timeout=5
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            metadata.update({
                                'symbol': data.get('symbol', metadata['symbol']),
                                'name': data.get('name', metadata['name']),
                                'decimals': data.get('decimals', metadata['decimals'])
                            })
            except Exception:
                pass

            # Cache the metadata
            self.token_metadata_cache[mint_address] = metadata
            return metadata

        except Exception as e:
            logger.error(f"Error getting token metadata for {mint_address}: {e}")
            return {
                'address': mint_address,
                'symbol': 'Unknown',
                'name': 'Unknown'
            }

    async def parse_raydium_pool_creation(self, transaction: Dict) -> Optional[Dict]:
        """Parse Raydium pool creation transaction"""
        try:
            # Extract relevant information
            accounts = transaction.get('transaction', {}).get('message', {}).get('accountKeys', [])
            instructions = transaction.get('transaction', {}).get('message', {}).get('instructions', [])

            # Look for pool initialization instruction
            for instruction in instructions:
                program_id_index = instruction.get('programIdIndex')
                if program_id_index and program_id_index < len(accounts):
                    program_id = accounts[program_id_index]

                    # Check if it's a Raydium instruction
                    if program_id in [self.RAYDIUM_AMM_V4, self.RAYDIUM_CPMM]:
                        # Extract pool information
                        account_indices = instruction.get('accounts', [])
                        if len(account_indices) >= 10:
                            # Typical Raydium pool creation has specific account layout
                            token_a_mint = accounts[account_indices[8]] if account_indices[8] < len(accounts) else None
                            token_b_mint = accounts[account_indices[9]] if account_indices[9] < len(accounts) else None

                            if token_a_mint and token_b_mint:
                                # Determine which is the new token (not SOL/USDC/USDT)
                                known_tokens = [
                                    'So11111111111111111111111111111111111111112',  # SOL
                                    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',  # USDC
                                    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'   # USDT
                                ]

                                new_token = None
                                base_token = None

                                if token_a_mint not in known_tokens:
                                    new_token = token_a_mint
                                    base_token = token_b_mint
                                elif token_b_mint not in known_tokens:
                                    new_token = token_b_mint
                                    base_token = token_a_mint

                                if new_token:
                                    metadata = await self.get_token_metadata(new_token)
                                    return {
                                        'dex': 'Raydium',
                                        'mint_address': new_token,
                                        'base_token': base_token,
                                        'pool_address': accounts[account_indices[1]] if account_indices[1] < len(accounts) else None,
                                        **metadata
                                    }

        except Exception as e:
            logger.debug(f"Error parsing Raydium transaction: {e}")

        return None

    async def parse_pump_fun_launch(self, transaction: Dict) -> Optional[Dict]:
        """Parse Pump.fun token launch transaction"""
        try:
            accounts = transaction.get('transaction', {}).get('message', {}).get('accountKeys', [])
            instructions = transaction.get('transaction', {}).get('message', {}).get('instructions', [])

            for instruction in instructions:
                program_id_index = instruction.get('programIdIndex')
                if program_id_index and program_id_index < len(accounts):
                    program_id = accounts[program_id_index]

                    if program_id == self.PUMP_FUN_PROGRAM:
                        # Pump.fun creates tokens with specific instruction patterns
                        account_indices = instruction.get('accounts', [])
                        if len(account_indices) >= 5:
                            # First account is usually the mint
                            mint_address = accounts[account_indices[0]] if account_indices[0] < len(accounts) else None

                            if mint_address:
                                metadata = await self.get_token_metadata(mint_address)
                                return {
                                    'dex': 'Pump.fun',
                                    'mint_address': mint_address,
                                    'base_token': 'So11111111111111111111111111111111111111112',  # SOL
                                    **metadata
                                }

        except Exception as e:
            logger.debug(f"Error parsing Pump.fun transaction: {e}")

        return None

    async def get_recent_pool_creations(self) -> List[Dict]:
        """Get recent pool creation transactions"""
        pools = []

        try:
            # Get recent signatures for Raydium
            signatures = await self.client.get_signatures_for_address(
                Pubkey.from_string(self.RAYDIUM_AMM_V4),
                limit=50,
                before=self.last_signature
            )

            if signatures and signatures.value:
                for sig_info in signatures.value:
                    signature = str(sig_info.signature)

                    # Skip if already processed
                    if signature in self.processed_signatures:
                        continue

                    try:
                        # Get transaction details
                        tx = await self.client.get_transaction(
                            Signature.from_string(signature),
                            max_supported_transaction_version=0
                        )

                        if tx and tx.value:
                            # Parse pool creation
                            pool_info = await self.parse_raydium_pool_creation(tx.value)
                            if pool_info:
                                pool_info['signature'] = signature
                                pool_info['timestamp'] = sig_info.block_time or int(datetime.now().timestamp())
                                pools.append(pool_info)

                        self.processed_signatures.add(signature)

                    except Exception as e:
                        logger.debug(f"Error processing signature {signature}: {e}")

                # Update last signature for pagination
                if signatures.value:
                    self.last_signature = str(signatures.value[-1].signature)

            # Also check Pump.fun transactions
            pump_signatures = await self.client.get_signatures_for_address(
                Pubkey.from_string(self.PUMP_FUN_PROGRAM),
                limit=25
            )

            if pump_signatures and pump_signatures.value:
                for sig_info in pump_signatures.value[:10]:  # Limit to avoid overwhelming
                    signature = str(sig_info.signature)

                    if signature in self.processed_signatures:
                        continue

                    try:
                        tx = await self.client.get_transaction(
                            Signature.from_string(signature),
                            max_supported_transaction_version=0
                        )

                        if tx and tx.value:
                            launch_info = await self.parse_pump_fun_launch(tx.value)
                            if launch_info:
                                launch_info['signature'] = signature
                                launch_info['timestamp'] = sig_info.block_time or int(datetime.now().timestamp())
                                pools.append(launch_info)

                        self.processed_signatures.add(signature)

                    except Exception as e:
                        logger.debug(f"Error processing Pump.fun signature {signature}: {e}")

        except Exception as e:
            logger.error(f"Error getting recent pool creations: {e}")

        return pools

    async def get_pool_liquidity(self, pool_address: str) -> Optional[float]:
        """Get pool liquidity in USD"""
        try:
            from solders.pubkey import Pubkey
            
            # Get pool account info
            pool_pubkey = Pubkey.from_string(pool_address)
            account_info = await self.client.get_account_info(pool_pubkey)
            
            if not account_info or not account_info.value:
                logger.debug(f"No account info for pool {pool_address}")
                return None
            
            # For Raydium pools, the account data contains reserve information
            # This is a simplified calculation - assumes SOL is one of the pairs
            # and estimates based on account balance
            data = account_info.value.data
            
            # Get the SOL balance in the pool (simplified)
            # Real implementation would parse the pool structure properly
            sol_balance = account_info.value.lamports / 1e9
            
            # Estimate USD value (assuming SOL price ~$150, this should be from price oracle)
            sol_price_usd = 150.0  # TODO: Get from price oracle
            estimated_liquidity = sol_balance * sol_price_usd * 2  # *2 for both sides of pair
            
            return estimated_liquidity if estimated_liquidity > 0 else None

        except Exception as e:
            logger.error(f"Error getting pool liquidity: {e}")
            return None

    async def monitor(self) -> AsyncGenerator[Dict, None]:
        """Monitor for new tokens"""
        await self.initialize()

        try:
            while True:
                try:
                    # Get recent pool creations
                    pools = await self.get_recent_pool_creations()

                    for pool in pools:
                        # Add chain-specific data
                        pool['chain'] = 'solana'
                        pool['chain_id'] = 'mainnet-beta'
                        pool['discovered_at'] = datetime.now().isoformat()

                        # Get liquidity if available
                        if pool.get('pool_address'):
                            liquidity = await self.get_pool_liquidity(pool['pool_address'])
                            pool['liquidity_usd'] = liquidity

                        # Add explorer links
                        pool['explorer_link'] = f"https://solscan.io/token/{pool.get('mint_address', '')}"
                        pool['dexscreener_link'] = f"https://dexscreener.com/solana/{pool.get('mint_address', '')}"

                        logger.info(f"New Solana token discovered: {pool.get('symbol', 'Unknown')} on {pool.get('dex', 'Unknown')}")

                        yield pool

                    # Wait before next check
                    await asyncio.sleep(10)

                except Exception as e:
                    logger.error(f"Error in Solana monitoring loop: {e}")
                    await asyncio.sleep(30)

        finally:
            await self.cleanup()
