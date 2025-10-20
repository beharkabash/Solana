#!/usr/bin/env python3
"""
ML Feedback Loop for Token Performance Tracking
Integrates with the Rust monitoring system to provide ML-based scoring improvements
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

from scoring.token_scorer import TokenScorer

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Structure for trade outcome tracking"""
    token_address: str
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    profit_loss_percentage: float
    success: bool
    initial_score: float


class MLFeedbackLoop:
    """ML Feedback system that learns from trading outcomes"""
    
    def __init__(self):
        self.scorer = TokenScorer()
        self.trade_log_file = "trade_results.jsonl"
        self.performance_threshold = float(os.getenv('ML_SUCCESS_THRESHOLD', 5.0))  # 5% profit
        
        # Performance tracking
        self.active_trades = {}
        self.completed_trades = []
        
        logger.info("ML Feedback Loop initialized")
    
    async def start_feedback_loop(self):
        """Start the ML feedback monitoring loop"""
        logger.info("Starting ML feedback loop...")
        
        while True:
            try:
                # Check for completed trades
                await self.check_trade_outcomes()
                
                # Process any new trade signals from Rust bot
                await self.process_trade_signals()
                
                # Update ML model if enough data
                await self.update_ml_model()
                
                # Sleep for 30 seconds before next check
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in feedback loop: {e}")
                await asyncio.sleep(60)
    
    async def process_trade_signals(self):
        """Process trade signals from the Rust monitoring system"""
        signal_file = "trade_signals.jsonl"
        
        if not os.path.exists(signal_file):
            return
        
        try:
            with open(signal_file, 'r') as f:
                lines = f.readlines()
            
            # Clear the file after reading
            open(signal_file, 'w').close()
            
            for line in lines:
                if line.strip():
                    signal = json.loads(line.strip())
                    await self.handle_trade_signal(signal)
                    
        except Exception as e:
            logger.error(f"Error processing trade signals: {e}")
    
    async def handle_trade_signal(self, signal: Dict):
        """Handle individual trade signal"""
        try:
            signal_type = signal.get('type')
            token_address = signal.get('token_address')
            
            if signal_type == 'BUY':
                # Record trade entry
                self.active_trades[token_address] = {
                    'entry_time': datetime.now(),
                    'entry_price': signal.get('price', 0),
                    'initial_score': signal.get('score', 0),
                    'amount': signal.get('amount', 0)
                }
                logger.info(f"Recorded trade entry for {token_address}")
                
            elif signal_type == 'SELL' and token_address in self.active_trades:
                # Record trade exit and calculate performance
                trade_data = self.active_trades[token_address]
                exit_price = signal.get('price', 0)
                
                if trade_data['entry_price'] > 0:
                    profit_loss_pct = ((exit_price - trade_data['entry_price']) / trade_data['entry_price']) * 100
                    success = profit_loss_pct >= self.performance_threshold
                    
                    trade_result = TradeResult(
                        token_address=token_address,
                        entry_price=trade_data['entry_price'],
                        exit_price=exit_price,
                        entry_time=trade_data['entry_time'],
                        exit_time=datetime.now(),
                        profit_loss_percentage=profit_loss_pct,
                        success=success,
                        initial_score=trade_data['initial_score']
                    )
                    
                    # Add to completed trades
                    self.completed_trades.append(trade_result)
                    
                    # Provide feedback to ML model
                    await self.provide_ml_feedback(trade_result)
                    
                    # Log to file
                    self.log_trade_result(trade_result)
                    
                    # Remove from active trades
                    del self.active_trades[token_address]
                    
                    logger.info(f"Completed trade for {token_address}: {profit_loss_pct:.2f}% {'SUCCESS' if success else 'LOSS'}")
                    
        except Exception as e:
            logger.error(f"Error handling trade signal: {e}")
    
    async def provide_ml_feedback(self, trade_result: TradeResult):
        """Provide feedback to the ML scoring model"""
        try:
            # This would integrate with the enhanced TokenScorer
            self.scorer.add_performance_feedback(
                token_address=trade_result.token_address,
                success=trade_result.success,
                price_change=trade_result.profit_loss_percentage
            )
            
        except Exception as e:
            logger.error(f"Error providing ML feedback: {e}")
    
    def log_trade_result(self, trade_result: TradeResult):
        """Log trade result to file for analysis"""
        try:
            result_data = {
                'timestamp': datetime.now().isoformat(),
                'token_address': trade_result.token_address,
                'entry_price': trade_result.entry_price,
                'exit_price': trade_result.exit_price,
                'profit_loss_percentage': trade_result.profit_loss_percentage,
                'success': trade_result.success,
                'initial_score': trade_result.initial_score,
                'hold_duration_hours': (trade_result.exit_time - trade_result.entry_time).total_seconds() / 3600
            }
            
            with open(self.trade_log_file, 'a') as f:
                f.write(json.dumps(result_data) + '\n')
                
        except Exception as e:
            logger.error(f"Error logging trade result: {e}")
    
    async def check_trade_outcomes(self):
        """Check outcomes of active trades"""
        # This could integrate with price feeds to check current prices
        # For now, we rely on explicit SELL signals
        
        # Clean up old active trades (>24 hours with no activity)
        cutoff_time = datetime.now() - timedelta(hours=24)
        expired_trades = [
            addr for addr, data in self.active_trades.items()
            if data['entry_time'] < cutoff_time
        ]
        
        for addr in expired_trades:
            logger.warning(f"Cleaning up expired trade for {addr}")
            del self.active_trades[addr]
    
    async def update_ml_model(self):
        """Update ML model periodically"""
        # Update model every 100 completed trades
        if len(self.completed_trades) % 100 == 0 and len(self.completed_trades) > 0:
            logger.info("Updating ML model with new trade data...")
            # The TokenScorer will handle the actual ML training
    
    def get_performance_stats(self) -> Dict:
        """Get performance statistics"""
        if not self.completed_trades:
            return {
                'total_trades': 0,
                'success_rate': 0,
                'average_profit': 0,
                'average_loss': 0
            }
        
        successful_trades = [t for t in self.completed_trades if t.success]
        failed_trades = [t for t in self.completed_trades if not t.success]
        
        success_rate = len(successful_trades) / len(self.completed_trades) * 100
        avg_profit = sum(t.profit_loss_percentage for t in successful_trades) / len(successful_trades) if successful_trades else 0
        avg_loss = sum(t.profit_loss_percentage for t in failed_trades) / len(failed_trades) if failed_trades else 0
        
        return {
            'total_trades': len(self.completed_trades),
            'successful_trades': len(successful_trades),
            'failed_trades': len(failed_trades),
            'success_rate': round(success_rate, 2),
            'average_profit': round(avg_profit, 2),
            'average_loss': round(avg_loss, 2),
            'active_trades': len(self.active_trades)
        }


async def main():
    """Main entry point for ML feedback loop"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    feedback_loop = MLFeedbackLoop()
    
    try:
        await feedback_loop.start_feedback_loop()
    except KeyboardInterrupt:
        logger.info("ML Feedback Loop stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in ML Feedback Loop: {e}")


if __name__ == "__main__":
    asyncio.run(main())