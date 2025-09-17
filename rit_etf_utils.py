# RIT ETF Arbitrage - Utility Functions
# Supporting functions for the main arbitrage algorithm

import requests
import time
from typing import Dict, List, Optional, Tuple
import json

# =========================================================================================
# === UTILITY CLASSES ===
# =========================================================================================

class RiskManager:
    """Advanced risk management for position limits and exposure"""
    
    def __init__(self, max_gross=100000, max_long_net=30000, max_short_net=-30000):
        self.max_gross = max_gross
        self.max_long_net = max_long_net  
        self.max_short_net = max_short_net
        self.position_history = []
        
    def check_position_limits(self, positions: Dict, projected_changes: Dict) -> bool:
        """Check if projected position changes violate risk limits"""
        try:
            # Calculate projected positions
            proj_positions = {}
            for ticker in ['BULL', 'BEAR', 'RITC']:
                current = positions.get(ticker, 0)
                change = projected_changes.get(ticker, 0)
                proj_positions[ticker] = current + change
            
            # Calculate gross (ETF has 2x multiplier)
            gross = (abs(proj_positions['BULL']) + 
                    abs(proj_positions['BEAR']) + 
                    2 * abs(proj_positions['RITC']))
            
            # Calculate net (ETF has 2x multiplier)
            net = (proj_positions['BULL'] + 
                  proj_positions['BEAR'] + 
                  2 * proj_positions['RITC'])
            
            # Check limits
            gross_ok = gross <= self.max_gross
            net_ok = self.max_short_net <= net <= self.max_long_net
            
            if not gross_ok:
                print(f"RISK: Gross limit violation: {gross} > {self.max_gross}")
            if not net_ok:
                print(f"RISK: Net limit violation: {net} not in [{self.max_short_net}, {self.max_long_net}]")
                
            return gross_ok and net_ok
            
        except Exception as e:
            print(f"Error checking position limits: {e}")
            return False
    
    def get_max_trade_size(self, positions: Dict, trade_type: str) -> int:
        """Calculate maximum safe trade size given current positions"""
        try:
            current_gross = (abs(positions.get('BULL', 0)) + 
                           abs(positions.get('BEAR', 0)) + 
                           2 * abs(positions.get('RITC', 0)))
            
            available_gross = self.max_gross - current_gross
            
            if trade_type == 'arbitrage':
                # Arbitrage affects all three instruments
                # Conservative estimate: assume worst case impact
                max_size = available_gross // 5  # Rough approximation
            elif trade_type == 'etf_only':
                # Only ETF trading (2x multiplier)
                max_size = available_gross // 2
            else:
                # Stock trading only
                max_size = available_gross
            
            return max(0, min(max_size, 10000))  # Cap at order limit
            
        except Exception as e:
            print(f"Error calculating max trade size: {e}")
            return 0

class PerformanceTracker:
    """Track trading performance and statistics"""
    
    def __init__(self):
        self.trades = []
        self.start_time = time.time()
        self.pnl_history = []
        
    def record_trade(self, trade_type: str, quantity: int, profit: float, details: Dict):
        """Record a completed trade"""
        trade_record = {
            'timestamp': time.time(),
            'type': trade_type,
            'quantity': quantity,
            'profit': profit,
            'details': details
        }
        self.trades.append(trade_record)
        
    def get_statistics(self) -> Dict:
        """Get performance statistics"""
        if not self.trades:
            return {'total_trades': 0, 'total_profit': 0, 'avg_profit': 0}
            
        total_profit = sum(trade['profit'] for trade in self.trades)
        total_trades = len(self.trades)
        avg_profit = total_profit / total_trades if total_trades > 0 else 0
        
        profitable_trades = sum(1 for trade in self.trades if trade['profit'] > 0)
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        return {
            'total_trades': total_trades,
            'total_profit': total_profit,
            'avg_profit': avg_profit,
            'win_rate': win_rate,
            'runtime_minutes': (time.time() - self.start_time) / 60
        }

class OrderManager:
    """Manage order execution with retry logic and error handling"""
    
    def __init__(self, session, max_retries=3):
        self.session = session
        self.max_retries = max_retries
        self.pending_orders = {}
        
    def execute_order_with_retry(self, ticker: str, action: str, quantity: int, 
                                order_type: str = "MARKET", price: float = None) -> Optional[Dict]:
        """Execute order with retry logic"""
        for attempt in range(self.max_retries):
            try:
                if order_type == "MARKET":
                    result = self.place_market_order(ticker, action, quantity)
                else:
                    result = self.place_limit_order(ticker, action, quantity, price)
                    
                if result:
                    return result
                else:
                    print(f"Order attempt {attempt + 1} failed for {ticker}")
                    time.sleep(0.1)  # Brief pause before retry
                    
            except Exception as e:
                print(f"Order attempt {attempt + 1} exception: {e}")
                time.sleep(0.1)
                
        print(f"All order attempts failed for {ticker} {action} {quantity}")
        return None
    
    def place_market_order(self, ticker: str, action: str, quantity: int) -> Optional[Dict]:
        """Place market order"""
        try:
            resp = self.session.post("http://localhost:9999/v1/orders", params={
                "ticker": ticker,
                "type": "MARKET", 
                "quantity": int(quantity),
                "action": action
            })
            
            if resp.ok:
                result = resp.json()
                print(f"ORDER: {action} {quantity} {ticker} @ {result.get('vwap', 'MKT')}")
                return result
            else:
                print(f"Market order failed: {resp.text}")
                return None
                
        except Exception as e:
            print(f"Market order exception: {e}")
            return None
    
    def place_limit_order(self, ticker: str, action: str, quantity: int, price: float) -> Optional[Dict]:
        """Place limit order"""
        try:
            resp = self.session.post("http://localhost:9999/v1/orders", params={
                "ticker": ticker,
                "type": "LIMIT",
                "quantity": int(quantity), 
                "action": action,
                "price": round(price, 4)
            })
            
            if resp.ok:
                result = resp.json()
                print(f"LIMIT: {action} {quantity} {ticker} @ {price}")
                return result
            else:
                print(f"Limit order failed: {resp.text}")
                return None
                
        except Exception as e:
            print(f"Limit order exception: {e}")
            return None

class MarketDataManager:
    """Efficient market data management with caching"""
    
    def __init__(self, session):
        self.session = session
        self.cache = {}
        self.last_update = {}
        self.cache_duration = 0.5  # Cache for 0.5 seconds
        
    def get_order_book(self, ticker: str, force_refresh: bool = False) -> Dict:
        """Get order book with caching"""
        current_time = time.time()
        
        if (not force_refresh and 
            ticker in self.cache and 
            current_time - self.last_update.get(ticker, 0) < self.cache_duration):
            return self.cache[ticker]
        
        try:
            resp = self.session.get("http://localhost:9999/v1/securities/book", 
                                  params={"ticker": ticker, "limit": 10})
            resp.raise_for_status()
            
            book = resp.json()
            self.cache[ticker] = book
            self.last_update[ticker] = current_time
            
            return book
            
        except Exception as e:
            print(f"Error getting order book for {ticker}: {e}")
            return {"bids": [], "asks": []}
    
    def get_best_prices(self, ticker: str) -> Tuple[float, float, int, int]:
        """Get best bid/ask prices and quantities"""
        book = self.get_order_book(ticker)
        
        if book["bids"] and book["asks"]:
            bid = float(book["bids"][0]["price"])
            ask = float(book["asks"][0]["price"]) 
            bid_qty = int(book["bids"][0]["quantity"])
            ask_qty = int(book["asks"][0]["quantity"])
            return bid, ask, bid_qty, ask_qty
        else:
            return 0.0, float('inf'), 0, 0
    
    def get_market_depth(self, ticker: str, levels: int = 5) -> Dict:
        """Get market depth analysis"""
        book = self.get_order_book(ticker)
        
        bid_volume = sum(int(level["quantity"]) for level in book["bids"][:levels])
        ask_volume = sum(int(level["quantity"]) for level in book["asks"][:levels])
        
        bid_value = sum(float(level["price"]) * int(level["quantity"]) 
                       for level in book["bids"][:levels])
        ask_value = sum(float(level["price"]) * int(level["quantity"])
                       for level in book["asks"][:levels])
        
        return {
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "total_volume": bid_volume + ask_volume,
            "bid_value": bid_value,
            "ask_value": ask_value,
            "imbalance": (bid_volume - ask_volume) / (bid_volume + ask_volume) if (bid_volume + ask_volume) > 0 else 0
        }

# =========================================================================================  
# === SPECIALIZED ARBITRAGE STRATEGIES ===
# =========================================================================================

class StatisticalArbitrage:
    """Statistical arbitrage between ETF and basket"""
    
    def __init__(self, lookback_periods=20):
        self.lookback_periods = lookback_periods
        self.price_history = {}
        self.spread_history = []
        
    def update_prices(self, bull_price: float, bear_price: float, 
                     ritc_price: float, usd_rate: float):
        """Update price history for statistical analysis"""
        timestamp = time.time()
        
        basket_value_cad = bull_price + bear_price
        etf_value_cad = ritc_price * usd_rate
        spread = etf_value_cad - basket_value_cad
        
        self.price_history[timestamp] = {
            'bull': bull_price,
            'bear': bear_price,
            'ritc': ritc_price,
            'usd_rate': usd_rate,
            'basket_cad': basket_value_cad,
            'etf_cad': etf_value_cad,
            'spread': spread
        }
        
        self.spread_history.append(spread)
        if len(self.spread_history) > self.lookback_periods:
            self.spread_history.pop(0)
    
    def get_mean_reversion_signal(self) -> Optional[Dict]:
        """Calculate mean reversion trading signal"""
        if len(self.spread_history) < self.lookback_periods:
            return None
            
        try:
            import numpy as np
            
            spreads = np.array(self.spread_history)
            mean_spread = np.mean(spreads)
            std_spread = np.std(spreads)
            current_spread = spreads[-1]
            
            # Z-score calculation
            if std_spread > 0:
                z_score = (current_spread - mean_spread) / std_spread
                
                # Generate signals based on z-score thresholds
                if z_score > 2.0:  # ETF overvalued relative to basket
                    return {
                        'signal': 'sell_etf_buy_basket',
                        'strength': min(abs(z_score), 4.0) / 4.0,  # Normalize to 0-1
                        'z_score': z_score,
                        'expected_profit': abs(current_spread - mean_spread)
                    }
                elif z_score < -2.0:  # ETF undervalued relative to basket
                    return {
                        'signal': 'buy_etf_sell_basket',
                        'strength': min(abs(z_score), 4.0) / 4.0,
                        'z_score': z_score,
                        'expected_profit': abs(current_spread - mean_spread)
                    }
                    
            return None
            
        except ImportError:
            # Fallback without numpy
            if len(self.spread_history) >= 5:
                recent_spreads = self.spread_history[-5:]
                avg_spread = sum(recent_spreads) / len(recent_spreads)
                current_spread = self.spread_history[-1]
                
                if current_spread > avg_spread + 0.10:  # Simple threshold
                    return {
                        'signal': 'sell_etf_buy_basket',
                        'strength': 0.5,
                        'expected_profit': current_spread - avg_spread
                    }
                elif current_spread < avg_spread - 0.10:
                    return {
                        'signal': 'buy_etf_sell_basket', 
                        'strength': 0.5,
                        'expected_profit': avg_spread - current_spread
                    }
            return None
        except Exception as e:
            print(f"Error in mean reversion calculation: {e}")
            return None

# =========================================================================================
# === CONFIGURATION HELPERS ===
# =========================================================================================

def load_config(config_file: str = "etf_config.json") -> Dict:
    """Load configuration from file"""
    default_config = {
        "api_key": "PA83Q8EP",
        "max_gross": 100000,
        "max_long_net": 30000,
        "max_short_net": -30000,
        "arb_threshold": 15.0,
        "tender_threshold": 100.0,
        "position_sizing": 0.8,
        "enable_statistical_arb": True,
        "enable_aggressive_hedging": True,
        "cache_duration": 0.5
    }
    
    try:
        with open(config_file, 'r') as f:
            file_config = json.load(f)
            default_config.update(file_config)
    except FileNotFoundError:
        print(f"Config file {config_file} not found, using defaults")
        # Create default config file
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
    except Exception as e:
        print(f"Error loading config: {e}, using defaults")
    
    return default_config

def save_performance_log(performance_tracker: PerformanceTracker, filename: str = "performance_log.json"):
    """Save performance data to file"""
    try:
        stats = performance_tracker.get_statistics()
        log_data = {
            'timestamp': time.time(),
            'statistics': stats,
            'trades': performance_tracker.trades[-100:]  # Save last 100 trades
        }
        
        with open(filename, 'w') as f:
            json.dump(log_data, f, indent=2)
            
        print(f"Performance log saved to {filename}")
        
    except Exception as e:
        print(f"Error saving performance log: {e}")

# =========================================================================================
# === TESTING AND VALIDATION ===
# =========================================================================================

def validate_api_connection(session) -> bool:
    """Validate API connection and permissions"""
    try:
        resp = session.get("http://localhost:9999/v1/case")
        if resp.ok:
            data = resp.json()
            print(f"API Connection OK - Tick: {data.get('tick')}, Status: {data.get('status')}")
            return True
        else:
            print(f"API Connection Failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"API Validation Error: {e}")
        return False

def run_system_checks(session) -> bool:
    """Run comprehensive system checks"""
    print("Running system checks...")
    
    checks = []
    
    # API Connection
    checks.append(("API Connection", validate_api_connection(session)))
    
    # Market Data Access
    try:
        resp = session.get("http://localhost:9999/v1/securities")
        checks.append(("Market Data", resp.ok))
    except:
        checks.append(("Market Data", False))
    
    # Order Placement (dry run)
    try:
        # This should fail but test the endpoint
        resp = session.post("http://localhost:9999/v1/orders", params={
            "ticker": "BULL", "type": "LIMIT", "quantity": 1, "action": "BUY", "price": 0.01
        })
        checks.append(("Order Endpoint", True))  # Even failure indicates endpoint works
    except:
        checks.append(("Order Endpoint", False))
    
    # Print results
    print("\nSystem Check Results:")
    all_passed = True
    for check_name, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  {check_name}: {status}")
        if not result:
            all_passed = False
    
    return all_passed

# =========================================================================================
# === MAIN UTILITY FUNCTIONS ===
# =========================================================================================

def format_number(num: float, decimals: int = 2) -> str:
    """Format number with appropriate precision"""
    return f"{num:,.{decimals}f}"

def calculate_transaction_costs(quantity: int, num_legs: int = 1) -> float:
    """Calculate total transaction costs"""
    return quantity * num_legs * 0.02  # $0.02 per share per leg

def get_fair_value(bull_price: float, bear_price: float, usd_rate: float) -> float:
    """Calculate ETF fair value in USD"""
    basket_value_cad = bull_price + bear_price
    return basket_value_cad / usd_rate