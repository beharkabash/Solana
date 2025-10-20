"""
Real-time Alert System Integration
Connects scoring system with live blockchain data and alert delivery
"""

import asyncio
import aiohttp
import json
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict
import redis
import logging
from dataclasses import asdict
import hashlib

from alert_scoring_system import (
    TokenMetrics, TokenScorer, MLScoreOptimizer,
    AlertDistributionManager, ConfidenceCalculator,
    Chain, save_model, load_model
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BlockchainDataCollector:
    """Collect real-time data from multiple blockchain sources"""

    def __init__(self):
        self.api_endpoints = {
            Chain.SOLANA: {
                'rpc': 'https://api.mainnet-beta.solana.com',
                'birdeye': 'https://api.birdeye.so',
                'jupiter': 'https://quote-api.jup.ag/v6',
                'helius': 'https://api.helius.xyz/v0'
            },
            Chain.ETHEREUM: {
                'rpc': 'https://eth-mainnet.g.alchemy.com/v2/',
                'etherscan': 'https://api.etherscan.io/api',
                'dexscreener': 'https://api.dexscreener.com/latest',
                'tokensniffer': 'https://tokensniffer.com/api'
            },
            Chain.BNB: {
                'rpc': 'https://bsc-dataseed.binance.org',
                'bscscan': 'https://api.bscscan.com/api',
                'pancakeswap': 'https://api.pancakeswap.info/api/v2'
            },
            Chain.BASE: {
                'rpc': 'https://mainnet.base.org',
                'basescan': 'https://api.basescan.org/api',
                'uniswap': 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3'
            }
        }
        self.session = None

    async def initialize(self):
        """Initialize async session"""
        self.session = aiohttp.ClientSession()

    async def collect_token_metrics(self, chain: Chain, address: str) -> Optional[TokenMetrics]:
        """Collect comprehensive metrics for a token"""
        try:
            # Parallel data collection
            tasks = [
                self._get_liquidity_data(chain, address),
                self._get_holder_data(chain, address),
                self._get_contract_security(chain, address),
                self._get_social_data(address),
                self._get_volume_data(chain, address),
                self._get_developer_data(address)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Combine results into TokenMetrics
            liquidity_data = results[0] if not isinstance(results[0], Exception) else {}
            holder_data = results[1] if not isinstance(results[1], Exception) else {}
            security_data = results[2] if not isinstance(results[2], Exception) else {}
            social_data = results[3] if not isinstance(results[3], Exception) else {}
            volume_data = results[4] if not isinstance(results[4], Exception) else {}
            dev_data = results[5] if not isinstance(results[5], Exception) else {}

            # Build TokenMetrics object
            metrics = TokenMetrics(
                chain=chain,
                address=address,
                name=liquidity_data.get('name', 'Unknown'),
                symbol=liquidity_data.get('symbol', 'UNKNOWN'),
                launch_time=datetime.fromtimestamp(liquidity_data.get('launch_time', datetime.now().timestamp())),

                # Liquidity metrics
                initial_liquidity=liquidity_data.get('initial_liquidity', 0),
                liquidity_locked=liquidity_data.get('liquidity_locked', False),
                liquidity_lock_duration=liquidity_data.get('lock_duration', 0),
                liquidity_to_mcap_ratio=liquidity_data.get('liq_mcap_ratio', 0),
                liquidity_providers_count=liquidity_data.get('lp_count', 0),

                # Holder metrics
                total_holders=holder_data.get('total_holders', 0),
                top_10_holders_percentage=holder_data.get('top_10_percentage', 100),
                top_holder_percentage=holder_data.get('top_holder_percentage', 100),
                unique_buyers_first_hour=holder_data.get('unique_buyers_1h', 0),
                holder_growth_rate=holder_data.get('growth_rate', 0),
                whale_concentration=holder_data.get('whale_concentration', 1.0),

                # Security metrics
                contract_verified=security_data.get('verified', False),
                honeypot_check=security_data.get('is_honeypot', True),
                mint_disabled=security_data.get('mint_disabled', False),
                max_tx_percentage=security_data.get('max_tx_percent', 0),
                tax_percentage=security_data.get('tax_percent', 100),
                ownership_renounced=security_data.get('renounced', False),
                audit_score=security_data.get('audit_score'),

                # Social metrics
                telegram_members=social_data.get('telegram_members', 0),
                twitter_followers=social_data.get('twitter_followers', 0),
                twitter_engagement_rate=social_data.get('engagement_rate', 0),
                social_growth_rate=social_data.get('growth_rate', 0),
                influencer_mentions=social_data.get('influencer_mentions', 0),
                sentiment_score=social_data.get('sentiment', 0),

                # Volume metrics
                volume_1h=volume_data.get('volume_1h', 0),
                volume_24h=volume_data.get('volume_24h', 0),
                buy_sell_ratio=volume_data.get('buy_sell_ratio', 0),
                average_trade_size=volume_data.get('avg_trade_size', 0),
                trades_per_minute=volume_data.get('trades_per_minute', 0),
                price_volatility=volume_data.get('volatility', 0),

                # Developer metrics
                github_commits=dev_data.get('commits', 0),
                code_updates_24h=dev_data.get('updates_24h', 0),
                developer_wallet_history=dev_data.get('wallet_history', 0),
                team_doxxed=dev_data.get('doxxed', False),

                # Community metrics
                discord_members=social_data.get('discord_members', 0),
                reddit_subscribers=social_data.get('reddit_subs', 0),
                community_engagement_score=social_data.get('engagement_score', 0),

                # Risk factors
                similar_name_tokens=security_data.get('similar_tokens', 0),
                rug_pull_indicators=security_data.get('rug_indicators', []),
                chain_specific_risks=security_data.get('chain_risks', {})
            )

            return metrics

        except Exception as e:
            logger.error(f"Error collecting metrics for {address}: {e}")
            return None

    async def _get_liquidity_data(self, chain: Chain, address: str) -> Dict:
        """Fetch liquidity data from DEX APIs"""
        # Implementation would connect to real APIs
        # This is a template showing the structure
        return {
            'name': 'TokenName',
            'symbol': 'TOKEN',
            'launch_time': datetime.now().timestamp(),
            'initial_liquidity': 50000,
            'liquidity_locked': True,
            'lock_duration': 180,
            'liq_mcap_ratio': 0.15,
            'lp_count': 75
        }

    async def _get_holder_data(self, chain: Chain, address: str) -> Dict:
        """Fetch holder distribution data"""
        return {
            'total_holders': 1500,
            'top_10_percentage': 30,
            'top_holder_percentage': 8,
            'unique_buyers_1h': 350,
            'growth_rate': 60,
            'whale_concentration': 0.4
        }

    async def _get_contract_security(self, chain: Chain, address: str) -> Dict:
        """Analyze contract security"""
        return {
            'verified': True,
            'is_honeypot': False,
            'mint_disabled': True,
            'max_tx_percent': 2,
            'tax_percent': 5,
            'renounced': True,
            'audit_score': 85,
            'similar_tokens': 2,
            'rug_indicators': [],
            'chain_risks': {}
        }

    async def _get_social_data(self, address: str) -> Dict:
        """Fetch social media metrics"""
        return {
            'telegram_members': 3000,
            'twitter_followers': 2000,
            'engagement_rate': 4.5,
            'growth_rate': 15,
            'influencer_mentions': 3,
            'sentiment': 0.6,
            'discord_members': 1000,
            'reddit_subs': 500,
            'engagement_score': 65
        }

    async def _get_volume_data(self, chain: Chain, address: str) -> Dict:
        """Fetch trading volume data"""
        return {
            'volume_1h': 85000,
            'volume_24h': 0,
            'buy_sell_ratio': 1.35,
            'avg_trade_size': 350,
            'trades_per_minute': 8,
            'volatility': 0.15
        }

    async def _get_developer_data(self, address: str) -> Dict:
        """Fetch developer activity data"""
        return {
            'commits': 25,
            'updates_24h': 2,
            'wallet_history': 2,
            'doxxed': False
        }

    async def close(self):
        """Close async session"""
        if self.session:
            await self.session.close()


class TokenMonitor:
    """Monitor multiple chains for new token launches"""

    def __init__(self):
        self.collectors = {chain: BlockchainDataCollector() for chain in Chain}
        self.scorer = TokenScorer()
        self.ml_optimizer = MLScoreOptimizer()
        self.alert_manager = AlertDistributionManager()
        self.confidence_calc = ConfidenceCalculator()
        self.processed_tokens = set()
        self.redis_client = None

    async def initialize(self):
        """Initialize all components"""
        # Initialize collectors
        for collector in self.collectors.values():
            await collector.initialize()

        # Connect to Redis for state management
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )

        # Load ML model if exists
        try:
            self.scorer, self.ml_optimizer = load_model('model.pkl')
            logger.info("Loaded existing ML model")
        except FileNotFoundError:
            logger.info("Starting with fresh model")

    async def monitor_chain(self, chain: Chain):
        """Monitor a specific chain for new tokens"""
        logger.info(f"Monitoring {chain.value} for new tokens...")

        while True:
            try:
                # Get new token launches (would connect to real APIs)
                new_tokens = await self._get_new_tokens(chain)

                for token_address in new_tokens:
                    # Check if already processed
                    token_id = f"{chain.value}:{token_address}"
                    if token_id in self.processed_tokens:
                        continue

                    # Collect metrics
                    collector = self.collectors[chain]
                    metrics = await collector.collect_token_metrics(chain, token_address)

                    if metrics:
                        # Process token
                        await self.process_token(metrics)

                    # Mark as processed
                    self.processed_tokens.add(token_id)

                # Short delay between checks
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error monitoring {chain.value}: {e}")
                await asyncio.sleep(30)

    async def _get_new_tokens(self, chain: Chain) -> List[str]:
        """Get list of new token addresses"""
        # This would connect to real blockchain APIs
        # For demo, return empty list
        return []

    async def process_token(self, metrics: TokenMetrics):
        """Process a token and determine if alert should be sent"""
        try:
            # Calculate score
            score, components = self.scorer.calculate_score(metrics)

            # Get ML prediction
            ml_probability = self.ml_optimizer.predict_success_probability(score)

            # Calculate confidence
            confidence = self.confidence_calc.calculate_confidence(
                score, components, ml_probability
            )

            # Check if should send alert
            current_hour = datetime.now().hour
            should_send, threshold = self.alert_manager.should_send_alert(
                score, metrics.chain, current_hour
            )

            if should_send:
                # Prepare alert
                alert = self.prepare_alert(metrics, score, components, confidence)

                # Send alert
                await self.send_alert(alert)

                # Log for ML training
                self.log_alert(metrics.address, score, confidence)

            # Store in database for analysis
            await self.store_token_data(metrics, score, components, confidence)

        except Exception as e:
            logger.error(f"Error processing token {metrics.address}: {e}")

    def prepare_alert(self, metrics: TokenMetrics, score: float,
                     components: Dict, confidence: Dict) -> Dict:
        """Prepare alert message"""
        return {
            'timestamp': datetime.now().isoformat(),
            'chain': metrics.chain.value,
            'token': {
                'address': metrics.address,
                'name': metrics.name,
                'symbol': metrics.symbol
            },
            'scores': {
                'total': round(score, 2),
                'components': {k: round(v, 2) for k, v in components.items()}
            },
            'confidence': {
                'level': confidence['confidence_level'],
                'success_probability': round(confidence['predicted_2x_probability'], 3),
                'timeframe': confidence['predicted_timeframe'],
                'risk_level': confidence['risk_level'].value
            },
            'metrics': {
                'liquidity': metrics.initial_liquidity,
                'holders': metrics.total_holders,
                'volume_1h': metrics.volume_1h,
                'buy_sell_ratio': round(metrics.buy_sell_ratio, 2)
            },
            'warnings': metrics.rug_pull_indicators,
            'action': self._get_action_recommendation(score, confidence)
        }

    def _get_action_recommendation(self, score: float, confidence: Dict) -> str:
        """Get trading action recommendation"""
        if score >= 75 and confidence['risk_level'].value == 'low':
            return "STRONG BUY - High confidence"
        elif score >= 60 and confidence['risk_level'].value in ['low', 'medium']:
            return "BUY - Moderate confidence"
        elif score >= 45:
            return "WATCH - Consider small position"
        else:
            return "SKIP - Low confidence"

    async def send_alert(self, alert: Dict):
        """Send alert to various channels"""
        # Webhook delivery
        await self._send_webhook(alert)

        # Store in Redis for API access
        alert_key = f"alert:{alert['timestamp']}:{alert['token']['address']}"
        self.redis_client.setex(
            alert_key,
            3600,  # Expire after 1 hour
            json.dumps(alert)
        )

        # Log alert
        logger.info(
            f"ALERT: {alert['chain']} - {alert['token']['symbol']} "
            f"Score: {alert['scores']['total']} "
            f"Action: {alert['action']}"
        )

    async def _send_webhook(self, alert: Dict):
        """Send alert via webhook"""
        webhook_url = "https://your-webhook-endpoint.com/alerts"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(webhook_url, json=alert) as response:
                    if response.status != 200:
                        logger.error(f"Webhook delivery failed: {response.status}")
            except Exception as e:
                logger.error(f"Webhook error: {e}")

    def log_alert(self, address: str, score: float, confidence: Dict):
        """Log alert for ML training"""
        self.redis_client.hset(
            f"pending_outcomes:{address}",
            mapping={
                'score': score,
                'confidence': json.dumps(confidence),
                'timestamp': datetime.now().isoformat()
            }
        )

    async def store_token_data(self, metrics: TokenMetrics, score: float,
                              components: Dict, confidence: Dict):
        """Store token data for analysis"""
        data = {
            'metrics': asdict(metrics),
            'score': score,
            'components': components,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat()
        }

        # Store in Redis with expiration
        key = f"token:{metrics.chain.value}:{metrics.address}"
        self.redis_client.setex(key, 86400, json.dumps(data))

    async def collect_outcomes(self):
        """Collect actual outcomes for ML training"""
        while True:
            try:
                # Get pending outcomes older than 24 hours
                pending_keys = self.redis_client.keys("pending_outcomes:*")

                for key in pending_keys:
                    data = self.redis_client.hgetall(key)
                    timestamp = datetime.fromisoformat(data['timestamp'])

                    # Check if 24 hours have passed
                    if datetime.now() - timestamp > timedelta(hours=24):
                        address = key.split(':')[1]

                        # Get actual price change (would fetch from API)
                        outcome = await self._get_price_change(address)

                        # Record outcome for ML training
                        self.ml_optimizer.collect_outcome(
                            address,
                            float(data['score']),
                            outcome,
                            timestamp
                        )

                        # Remove from pending
                        self.redis_client.delete(key)

                # Retrain model periodically
                if len(self.ml_optimizer.training_data) % 100 == 0:
                    self.ml_optimizer.train_model()

                    # Adjust weights
                    new_weights = self.ml_optimizer.adjust_weights(self.scorer.weights)
                    self.scorer.weights = new_weights

                    # Save model
                    save_model(self.scorer, self.ml_optimizer, 'model.pkl')

                # Check every hour
                await asyncio.sleep(3600)

            except Exception as e:
                logger.error(f"Error collecting outcomes: {e}")
                await asyncio.sleep(3600)

    async def _get_price_change(self, address: str) -> float:
        """Get actual price change after 24 hours"""
        try:
            # Fetch price data from DexScreener or similar API
            # This is a simplified implementation
            
            # TODO: Implement actual price tracking
            # Options:
            # 1. Query DexScreener API for historical price data
            # 2. Store initial price in database and compare with current
            # 3. Use CoinGecko/CoinMarketCap APIs
            
            # For now, log that this needs implementation
            logger.debug(f"Price change calculation needed for {address}")
            
            # Return 0 to indicate no change data available
            # Real implementation should track actual price movements
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting price change for {address}: {e}")
            return 0.0

    async def run(self):
        """Run the complete monitoring system"""
        await self.initialize()

        # Start monitoring all chains
        tasks = [
            self.monitor_chain(chain) for chain in Chain
        ]

        # Add outcome collection task
        tasks.append(self.collect_outcomes())

        # Run all tasks concurrently
        await asyncio.gather(*tasks)


class AlertAPI:
    """REST API for accessing alerts and statistics"""

    def __init__(self, monitor: TokenMonitor):
        self.monitor = monitor

    def get_recent_alerts(self, limit: int = 50) -> List[Dict]:
        """Get recent alerts"""
        alert_keys = self.monitor.redis_client.keys("alert:*")
        alert_keys.sort(reverse=True)  # Most recent first

        alerts = []
        for key in alert_keys[:limit]:
            alert_data = self.monitor.redis_client.get(key)
            if alert_data:
                alerts.append(json.loads(alert_data))

        return alerts

    def get_statistics(self) -> Dict:
        """Get system statistics"""
        status = self.monitor.alert_manager.get_status()

        # Add ML performance metrics
        if self.monitor.ml_optimizer.model:
            ml_stats = {
                'training_samples': len(self.monitor.ml_optimizer.training_data),
                'model_accuracy': getattr(self.monitor.ml_optimizer.model, 'score', 0)
            }
        else:
            ml_stats = {'training_samples': 0, 'model_accuracy': 0}

        return {
            'alert_distribution': status,
            'ml_performance': ml_stats,
            'processed_tokens': len(self.monitor.processed_tokens)
        }

    def get_token_analysis(self, chain: str, address: str) -> Optional[Dict]:
        """Get detailed analysis for a specific token"""
        key = f"token:{chain}:{address}"
        data = self.monitor.redis_client.get(key)

        if data:
            return json.loads(data)
        return None


async def main():
    """Main entry point"""
    monitor = TokenMonitor()

    try:
        await monitor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Cleanup
        for collector in monitor.collectors.values():
            await collector.close()


if __name__ == "__main__":
    asyncio.run(main())