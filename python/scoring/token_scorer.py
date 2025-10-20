"""
Token Scoring Engine with ML Feedback Loop
Comprehensive scoring system for evaluating newly launched tokens with learning capabilities
"""

import logging
import os
import re
import asyncio
import aiohttp
import json
import pickle
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
import numpy as np

# Add ML components
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logging.warning("scikit-learn not available. ML features disabled.")

try:
    from solders.pubkey import Pubkey
    from solana.rpc.api import Client
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False
    logging.warning("Solana libraries not available. Blockchain features limited.")

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class ScoringCriteria:
    """Criteria and weights for token scoring (max 100 points)"""
    liquidity_weight: float = float(os.getenv('LIQUIDITY_WEIGHT', 15.0))  # Max 15 points
    volume_weight: float = float(os.getenv('VOLUME_WEIGHT', 20.0))  # Max 20 points
    holder_distribution_weight: float = float(os.getenv('HOLDER_DISTRIBUTION_WEIGHT', 15.0))  # Max 15 points
    contract_verification_weight: float = float(os.getenv('CONTRACT_VERIFICATION_WEIGHT', 20.0))  # Max 20 points
    social_presence_weight: float = float(os.getenv('SOCIAL_PRESENCE_WEIGHT', 10.0))  # Max 10 points
    website_quality_weight: float = float(os.getenv('WEBSITE_QUALITY_WEIGHT', 5.0))  # Max 5 points
    token_economics_weight: float = float(os.getenv('TOKEN_ECONOMICS_WEIGHT', 15.0))  # Max 15 points


@dataclass
class TokenPerformanceData:
    """Data structure for tracking token performance for ML training"""
    token_address: str
    initial_score: float
    price_change_24h: float
    volume_change_24h: float
    holder_growth: float
    liquidity_change: float
    successful_trade: bool  # Target variable
    timestamp: datetime
    features: Dict[str, float]


class MLScoringModel:
    """Machine Learning model for adaptive token scoring"""
    
    def __init__(self):
        self.model: Optional[RandomForestClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names: List[str] = []
        self.model_path = "ml_token_model.pkl"
        self.training_data: List[TokenPerformanceData] = []
        self.min_training_samples = 100
        
        if ML_AVAILABLE:
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                class_weight='balanced'
            )
            self.scaler = StandardScaler()
            self._load_model()
    
    def _load_model(self):
        """Load trained model from disk if available"""
        try:
            if os.path.exists(self.model_path):
                with open(self.model_path, 'rb') as f:
                    model_data = pickle.load(f)
                    self.model = model_data['model']
                    self.scaler = model_data['scaler']
                    self.feature_names = model_data['feature_names']
                    logger.info("ML model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading ML model: {e}")
    
    def _save_model(self):
        """Save trained model to disk"""
        try:
            model_data = {
                'model': self.model,
                'scaler': self.scaler,
                'feature_names': self.feature_names
            }
            with open(self.model_path, 'wb') as f:
                pickle.dump(model_data, f)
            logger.info("ML model saved successfully")
        except Exception as e:
            logger.error(f"Error saving ML model: {e}")
    
    def add_training_data(self, performance_data: TokenPerformanceData):
        """Add new performance data for model training"""
        self.training_data.append(performance_data)
        
        # Retrain model periodically
        if len(self.training_data) >= self.min_training_samples and len(self.training_data) % 50 == 0:
            self.train_model()
    
    def train_model(self):
        """Train the ML model with collected performance data"""
        if not ML_AVAILABLE or len(self.training_data) < self.min_training_samples:
            return False
        
        try:
            # Prepare training data
            features = []
            targets = []
            
            for data in self.training_data:
                feature_vector = list(data.features.values())
                features.append(feature_vector)
                targets.append(1 if data.successful_trade else 0)
            
            X = np.array(features)
            y = np.array(targets)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train model
            self.model.fit(X_train_scaled, y_train)
            
            # Evaluate
            y_pred = self.model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            logger.info(f"ML model trained with accuracy: {accuracy:.3f}")
            self._save_model()
            return True
            
        except Exception as e:
            logger.error(f"Error training ML model: {e}")
            return False
    
    def predict_success_probability(self, features: Dict[str, float]) -> float:
        """Predict probability of successful trade"""
        if not ML_AVAILABLE or self.model is None:
            return 0.5  # Default probability
        
        try:
            feature_vector = np.array([list(features.values())]).reshape(1, -1)
            feature_vector_scaled = self.scaler.transform(feature_vector)
            probability = self.model.predict_proba(feature_vector_scaled)[0][1]
            return float(probability)
        except Exception as e:
            logger.error(f"Error predicting success probability: {e}")
            return 0.5


class TokenScorer:
    """Advanced token scoring system with ML feedback"""

    def __init__(self):
        """Initialize the token scorer"""
        self.criteria = ScoringCriteria()
        self.session: Optional[aiohttp.ClientSession] = None
        self.ml_model = MLScoringModel()

        # Enhanced minimum thresholds
        self.min_liquidity_usd = float(os.getenv('MIN_LIQUIDITY_USD', 5000))
        self.min_market_cap_usd = float(os.getenv('MIN_MARKET_CAP_USD', 3000))
        self.min_volume_24h = float(os.getenv('MIN_VOLUME_24H', 1000))
        self.min_holders = int(os.getenv('MIN_HOLDERS', 5))
        self.max_token_age_hours = int(os.getenv('MAX_TOKEN_AGE_HOURS', 48))
        self.max_buy_tax = float(os.getenv('MAX_BUY_TAX_PERCENT', 3.0))
        self.max_sell_tax = float(os.getenv('MAX_SELL_TAX_PERCENT', 3.0))
        
        # Performance tracking
        self.performance_tracking = {}
        
        logger.info("Enhanced Token Scorer initialized with ML capabilities")

    async def score_token(self, token_data: Dict) -> Tuple[float, Dict]:
        """
        Score a token from 0-100 with ML enhancement
        Returns: (score, analysis_details)
        """
        if not self.session:
            await self.initialize()

        analysis = {
            'timestamp': datetime.now().isoformat(),
            'token_address': token_data.get('address', token_data.get('mint_address', '')),
            'chain': token_data.get('chain', 'unknown'),
            'scores': {},
            'features': {},
            'warnings': [],
            'positives': [],
            'ml_enhanced': ML_AVAILABLE
        }

        # Calculate base scores
        total_score = 0.0
        features = {}

        # 1. Enhanced Liquidity Score (Max 15 pts)
        liquidity_score, liquidity_features = await self._score_liquidity_enhanced(token_data)
        analysis['scores']['liquidity'] = liquidity_score
        features.update(liquidity_features)
        total_score += liquidity_score

        # 2. Enhanced Volume Score (Max 20 pts)
        volume_score, volume_features = await self._score_volume_enhanced(token_data)
        analysis['scores']['volume'] = volume_score
        features.update(volume_features)
        total_score += volume_score

        # 3. Holder Distribution Score (Max 15 pts)
        holder_score = await self._score_holder_distribution(token_data)
        analysis['scores']['holder_distribution'] = holder_score
        features['holder_count'] = token_data.get('holders', 0)
        total_score += holder_score

        # 4. Contract Verification Score (Max 20 pts)
        contract_score = await self._score_contract(token_data)
        analysis['scores']['contract_verification'] = contract_score
        features['contract_verified'] = 1 if token_data.get('contract_verified', False) else 0
        total_score += contract_score

        # 5. Social Presence Score (Max 10 pts)
        social_score = await self._score_social_presence(token_data)
        analysis['scores']['social_presence'] = social_score
        features['social_score'] = social_score
        total_score += social_score

        # 6. Website Quality Score (Max 5 pts)
        website_score = await self._score_website(token_data)
        analysis['scores']['website_quality'] = website_score
        features['has_website'] = 1 if website_score > 0 else 0
        total_score += website_score

        # 7. Token Economics Score (Max 15 pts)
        economics_score = await self._score_token_economics(token_data)
        analysis['scores']['token_economics'] = economics_score
        features['token_economics'] = economics_score
        total_score += economics_score

        # Apply penalties and bonuses
        penalty = await self._calculate_penalties(token_data, analysis)
        total_score = max(0, total_score - penalty)

        bonus = await self._calculate_bonuses(token_data, analysis)
        total_score = min(100, total_score + bonus)

        # ML Enhancement
        analysis['features'] = features
        ml_probability = 0.5
        if ML_AVAILABLE and self.ml_model.model is not None:
            ml_probability = self.ml_model.predict_success_probability(features)
            # Adjust score based on ML prediction
            ml_adjustment = (ml_probability - 0.5) * 20  # +/- 10 points max
            total_score = max(0, min(100, total_score + ml_adjustment))
            analysis['ml_success_probability'] = ml_probability
            analysis['ml_adjustment'] = ml_adjustment

        analysis['final_score'] = round(total_score, 2)
        analysis['confidence_level'] = self._get_confidence_level(total_score, ml_probability)

        # Start performance tracking
        self._start_performance_tracking(analysis['token_address'], analysis)

        return total_score, analysis

    async def _score_liquidity_enhanced(self, token_data: Dict) -> Tuple[float, Dict]:
        """Enhanced liquidity scoring with additional features"""
        features = {}
        try:
            liquidity = token_data.get('liquidity_usd', 0)
            features['liquidity_usd'] = liquidity
            
            # Liquidity tiers with more granular scoring
            if liquidity >= 50000:
                score = 15
            elif liquidity >= 25000:
                score = 12
            elif liquidity >= 10000:
                score = 10
            elif liquidity >= 5000:
                score = 7
            elif liquidity >= 2500:
                score = 5
            else:
                score = 0

            # Liquidity stability check
            liquidity_24h_ago = token_data.get('liquidity_24h_ago', liquidity)
            if liquidity_24h_ago > 0:
                liquidity_change = (liquidity - liquidity_24h_ago) / liquidity_24h_ago
                features['liquidity_change_24h'] = liquidity_change
                if liquidity_change < -0.5:  # 50% drop
                    score *= 0.5  # Penalty for unstable liquidity

            return score, features

        except Exception as e:
            logger.error(f"Error scoring enhanced liquidity: {e}")
            return 0, features

    async def _score_volume_enhanced(self, token_data: Dict) -> Tuple[float, Dict]:
        """Enhanced volume scoring with velocity metrics"""
        features = {}
        try:
            volume_24h = token_data.get('volume_24h', 0)
            liquidity = token_data.get('liquidity_usd', 1)
            
            features['volume_24h'] = volume_24h
            features['volume_to_liquidity_ratio'] = volume_24h / liquidity if liquidity > 0 else 0

            # Base volume score
            if volume_24h >= 50000:
                score = 20
            elif volume_24h >= 25000:
                score = 16
            elif volume_24h >= 10000:
                score = 12
            elif volume_24h >= 5000:
                score = 8
            elif volume_24h >= 1000:
                score = 5
            else:
                score = 0

            # Volume velocity bonus
            volume_to_liquidity = volume_24h / liquidity if liquidity > 0 else 0
            if volume_to_liquidity > 2.0:  # High turnover
                score += 2
            elif volume_to_liquidity > 1.0:
                score += 1

            return min(20, score), features

        except Exception as e:
            logger.error(f"Error scoring enhanced volume: {e}")
            return 0, features

    def add_performance_feedback(self, token_address: str, success: bool, price_change: float, volume_change: float = 0):
        """Add performance feedback for ML training"""
        if token_address in self.performance_tracking:
            tracking_data = self.performance_tracking[token_address]
            
            performance_data = TokenPerformanceData(
                token_address=token_address,
                initial_score=tracking_data['initial_score'],
                price_change_24h=price_change,
                volume_change_24h=volume_change,
                holder_growth=0,  # Could be enhanced later
                liquidity_change=0,  # Could be enhanced later
                successful_trade=success,
                timestamp=datetime.now(),
                features=tracking_data['features']
            )
            
            self.ml_model.add_training_data(performance_data)
            
            # Clean up tracking data
            del self.performance_tracking[token_address]

    def _start_performance_tracking(self, token_address: str, analysis: Dict):
        """Start tracking token performance for ML feedback"""
        self.performance_tracking[token_address] = {
            'initial_score': analysis['final_score'],
            'features': analysis['features'],
            'start_time': datetime.now()
        }

    async def _score_holder_distribution(self, token_data: Dict) -> float:
        """Score based on holder distribution (Max 15 points)"""
        try:
            holders = await self._get_holder_distribution(token_data.get('address', ''), token_data.get('chain', ''))

            if not holders:
                total_holders = token_data.get('holders', 0)
            else:
                total_holders = holders.get('total', 0)

            # Enhanced scoring with concentration check
            if total_holders >= 500:
                score = 15
            elif total_holders >= 100:
                score = 12
            elif total_holders >= 50:
                score = 8
            elif total_holders >= 10:
                score = 5
            else:
                score = 0

            # Penalty for high concentration
            if holders and holders.get('top_10_percentage', 0) > 50:
                score *= 0.7  # 30% penalty for concentration

            return score

        except Exception as e:
            logger.error(f"Error scoring holder distribution: {e}")
            return 0

    async def _get_holder_distribution(self, token_address: str, chain: str) -> Optional[Dict]:
        """Get holder distribution from the blockchain"""
        if not SOLANA_AVAILABLE or chain != 'solana':
            return None

        try:
            client = Client(os.getenv("RPC_HTTP"))
            mint_pubkey = Pubkey.from_string(token_address)

            total_supply_response = client.get_token_supply(mint_pubkey)
            total_supply = total_supply_response.value.ui_amount

            largest_accounts_response = client.get_token_largest_accounts(mint_pubkey)
            largest_accounts = largest_accounts_response.value

            top_10_balance = sum(acc.ui_amount for acc in largest_accounts[:10])
            top_10_percentage = (top_10_balance / total_supply) * 100 if total_supply > 0 else 0

            return {
                'total': len(largest_accounts),
                'top_10_percentage': top_10_percentage,
            }
        except Exception as e:
            logger.error(f"Error getting holder distribution: {e}")
            return None

    # ... (rest of the scoring methods remain similar but with enhanced logic)

    async def initialize(self):
        """Initialize async resources"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()

    def _get_confidence_level(self, score: float, ml_probability: float = 0.5) -> str:
        """Get confidence level based on score and ML probability"""
        confidence = (score / 100) * ml_probability if ML_AVAILABLE else (score / 100)
        
        if score >= 80 and confidence >= 0.7:
            return "🔴 Very High (80-100): Immediate action"
        elif score >= 70 and confidence >= 0.6:
            return "🟠 High (70-79): Priority review"
        elif score >= 60 and confidence >= 0.5:
            return "🟡 Medium (60-69): Standard review"
        elif score >= 50:
            return "🟢 Low (50-59): Monitor"
        else:
            return "⚪ Very Low (<50): Filtered out"

    # Copy existing methods with minor enhancements
    async def _score_contract(self, token_data: Dict) -> float:
        try:
            score = 0
            is_verified = token_data.get('contract_verified', False)
            if is_verified:
                score += 8

            honeypot_check = token_data.get('honeypot_check', {})
            if honeypot_check:
                if not honeypot_check.get('is_honeypot', False):
                    score += 7
                else:
                    return 0

            if token_data.get('ownership_renounced', False):
                score += 3

            lp_locked = token_data.get('lp_locked', False)
            lp_lock_days = token_data.get('lp_lock_days', 0)
            if lp_locked or lp_lock_days >= 30:
                score += 2

            return min(20, score)
        except Exception as e:
            logger.error(f"Error scoring contract: {e}")
            return 0

    async def _score_social_presence(self, token_data: Dict) -> float:
        try:
            score = 0
            social_links = token_data.get('social_links', {})

            if social_links.get('twitter'):
                followers = social_links.get('twitter_followers', 0)
                if followers >= 1000:
                    score += 5
                elif followers >= 100:
                    score += 3
                elif followers >= 10:
                    score += 1

            if social_links.get('telegram'):
                members = social_links.get('telegram_members', 0)
                if members >= 500:
                    score += 3
                elif members >= 50:
                    score += 2
                elif members >= 10:
                    score += 1

            # Activity bonus
            if (social_links.get('twitter_followers', 0) >= 100 and
                social_links.get('telegram_members', 0) >= 50):
                score += 2

            return min(10, score)
        except Exception as e:
            logger.error(f"Error scoring social presence: {e}")
            return 0

    async def _score_website(self, token_data: Dict) -> float:
        try:
            website = token_data.get('social_links', {}).get('website', '')
            if website and website.startswith('http'):
                return 5
            return 0
        except Exception as e:
            logger.error(f"Error scoring website: {e}")
            return 0

    async def _score_token_economics(self, token_data: Dict) -> float:
        try:
            score = 0

            buy_tax = token_data.get('buy_tax', 0)
            sell_tax = token_data.get('sell_tax', 0)

            if buy_tax <= self.max_buy_tax and sell_tax <= self.max_sell_tax:
                score += 8

            total_supply = token_data.get('total_supply', 0)
            if total_supply > 0:
                if 1_000_000 <= total_supply <= 1_000_000_000_000:
                    score += 4

            lp_lock_days = token_data.get('lp_lock_days', 0)
            if lp_lock_days >= 30:
                score += 3

            return min(15, score)
        except Exception as e:
            logger.error(f"Error scoring token economics: {e}")
            return 0

    async def _calculate_penalties(self, token_data: Dict, analysis: Dict) -> float:
        penalty = 0
        name = token_data.get('name', '').lower()
        symbol = token_data.get('symbol', '').lower()

        scam_patterns = ['elon', 'musk', 'doge2.0', 'moon', 'safe', '100x', 'guaranteed']
        for pattern in scam_patterns:
            if pattern in name or pattern in symbol:
                penalty += 15
                analysis['warnings'].append(f"Suspicious pattern: {pattern}")

        if token_data.get('liquidity_usd', 0) < self.min_liquidity_usd:
            penalty += 5
            analysis['warnings'].append(f"Low liquidity: ${token_data.get('liquidity_usd', 0)}")

        if not token_data.get('social_links', {}):
            penalty += 10
            analysis['warnings'].append("No social presence")

        return penalty

    async def _calculate_bonuses(self, token_data: Dict, analysis: Dict) -> float:
        bonus = 0

        if token_data.get('contract_verified') and token_data.get('audited'):
            bonus += 5
            analysis['positives'].append("Verified and audited")

        volume_24h = token_data.get('volume_24h', 0)
        liquidity = token_data.get('liquidity_usd', 1)
        if volume_24h > liquidity * 1.5:
            bonus += 3
            analysis['positives'].append("High trading activity")

        return bonus