# RIT ETF Arbitrage - Main Execution Engine
# Complete algorithmic trading system for ETF arbitrage case

from rit_etf_arbitrage_complete import *
from rit_etf_utils import *
import threading
import queue
import signal
import sys

# =========================================================================================
# === ENHANCED MAIN EXECUTION ENGINE ===
# =========================================================================================

class ETFArbitrageBot:
    """Complete ETF Arbitrage Trading System"""
    
    def __init__(self, config_file="etf_config.json"):
        # Load configuration
        self.config = load_config(config_file)
        
        # Initialize session
        self.session = requests.Session()
        self.session.headers.update({"X-API-key": self.config["api_key"]})
        
        # Initialize components
        self.converter = None
        self.risk_manager = RiskManager(
            max_gross=self.config["max_gross"],
            max_long_net=self.config["max_long_net"], 
            max_short_net=self.config["max_short_net"]
        )
        self.performance_tracker = PerformanceTracker()
        self.order_manager = OrderManager(self.session)
        self.market_data_manager = MarketDataManager(self.session)
        
        # Trading state
        self.is_running = False
        self.positions = {}
        self.last_arbitrage_time = 0
        self.arbitrage_cooldown = 1.0  # Minimum seconds between arbitrage attempts
        
        # Statistics
        self.stats = {
            'arbitrage_attempts': 0,
            'arbitrage_successes': 0,
            'tender_attempts': 0,
            'tender_successes': 0,
            'total_profit': 0.0
        }
        
    def initialize_systems(self):
        """Initialize all trading systems"""
        print("Initializing ETF Arbitrage Trading Bot...")
        
        # System checks
        if not run_system_checks(self.session):
            print("System checks failed! Exiting...")
            return False
            
        # Initialize converter
        try:
            self.converter = Converter()
            print("Converter initialized successfully")
        except Exception as e:
            print(f"Failed to initialize converter: {e}")
            return False
            
        # Initialize arbitrage engine
        self.arbitrage_engine = ArbitrageEngine(self.converter)
        self.tender_handler = TenderHandler(self.converter)
        
        # Initialize statistical arbitrage if enabled
        if self.config.get("enable_statistical_arb", False):
            self.stat_arb = StatisticalArbitrage()
            print("Statistical arbitrage enabled")
        else:
            self.stat_arb = None
            
        print("All systems initialized successfully")
        return True
    
    def update_positions(self):
        """Update current positions"""
        try:
            self.positions = get_positions()
        except Exception as e:
            print(f"Error updating positions: {e}")
    
    def check_arbitrage_opportunities(self):
        """Check for and execute arbitrage opportunities"""
        current_time = time.time()
        
        # Respect cooldown period
        if current_time - self.last_arbitrage_time < self.arbitrage_cooldown:
            return
            
        try:
            # Get arbitrage opportunities
            opportunities = self.arbitrage_engine.analyzer.get_arbitrage_opportunities()
            
            for opp in opportunities:
                self.stats['arbitrage_attempts'] += 1
                
                # Check risk limits before execution
                if opp['type'] == 'buy_etf_sell_basket':
                    projected_changes = {
                        'RITC': opp['max_quantity'],
                        'BULL': -opp['max_quantity'],
                        'BEAR': -opp['max_quantity']
                    }
                else:
                    projected_changes = {
                        'RITC': -opp['max_quantity'],
                        'BULL': opp['max_quantity'], 
                        'BEAR': opp['max_quantity']
                    }
                
                if not self.risk_manager.check_position_limits(self.positions, projected_changes):
                    print(f"Skipping arbitrage due to position limits")
                    continue
                
                # Execute arbitrage
                print(f"EXECUTING ARBITRAGE: {opp['type']}")
                print(f"  Expected profit: ${opp['profit_per_share'] * opp['max_quantity']:.2f}")
                
                if self.arbitrage_engine.execute_arbitrage(opp):
                    self.stats['arbitrage_successes'] += 1
                    profit = opp['profit_per_share'] * opp['max_quantity']
                    self.stats['total_profit'] += profit
                    
                    self.performance_tracker.record_trade(
                        'arbitrage', opp['max_quantity'], profit, opp
                    )
                    
                    print(f"Arbitrage executed successfully - Profit: ${profit:.2f}")
                    self.last_arbitrage_time = current_time
                    break  # Execute one arbitrage at a time
                else:
                    print("Arbitrage execution failed")
                    
        except Exception as e:
            print(f"Error in arbitrage check: {e}")
    
    def check_tender_opportunities(self):
        """Check for and execute tender opportunities"""
        try:
            tenders = get_tenders()
            
            for tender in tenders:
                self.stats['tender_attempts'] += 1
                
                evaluation = self.tender_handler.evaluate_tender(tender)
                
                if evaluation and evaluation['net_profit'] > self.config["tender_threshold"]:
                    print(f"PROFITABLE TENDER FOUND:")
                    print(f"  ID: {tender['tender_id']}")
                    print(f"  Action: {tender['action']}")
                    print(f"  Quantity: {tender['quantity']}")
                    print(f"  Price: ${tender['price']}")
                    print(f"  Expected profit: ${evaluation['net_profit']:.2f}")
                    
                    if self.tender_handler.execute_tender(evaluation):
                        self.stats['tender_successes'] += 1
                        self.stats['total_profit'] += evaluation['net_profit']
                        
                        self.performance_tracker.record_trade(
                            'tender', tender['quantity'], evaluation['net_profit'], tender
                        )
                        
                        print("Tender executed successfully")
                    else:
                        print("Tender execution failed")
                        
        except Exception as e:
            print(f"Error processing tenders: {e}")
    
    def update_statistical_arbitrage(self):
        """Update statistical arbitrage model"""
        if not self.stat_arb:
            return
            
        try:
            # Get current prices
            bull_bid, bull_ask, _, _ = self.market_data_manager.get_best_prices('BULL')
            bear_bid, bear_ask, _, _ = self.market_data_manager.get_best_prices('BEAR')
            ritc_bid, ritc_ask, _, _ = self.market_data_manager.get_best_prices('RITC')
            usd_bid, usd_ask, _, _ = self.market_data_manager.get_best_prices('USD')
            
            if all(price > 0 for price in [bull_bid, bear_bid, ritc_bid, usd_bid]):
                bull_mid = (bull_bid + bull_ask) / 2
                bear_mid = (bear_bid + bear_ask) / 2
                ritc_mid = (ritc_bid + ritc_ask) / 2
                usd_mid = (usd_bid + usd_ask) / 2
                
                self.stat_arb.update_prices(bull_mid, bear_mid, ritc_mid, usd_mid)
                
                # Check for mean reversion signals
                signal = self.stat_arb.get_mean_reversion_signal()
                if signal and signal['strength'] > 0.7:  # High confidence signals only
                    print(f"STATISTICAL ARB SIGNAL: {signal['signal']}")
                    print(f"  Strength: {signal['strength']:.2f}")
                    print(f"  Expected profit: ${signal['expected_profit']:.2f}")
                    # Could implement statistical arbitrage execution here
                    
        except Exception as e:
            print(f"Error in statistical arbitrage update: {e}")
    
    def print_status(self):
        """Print current trading status"""
        print(f"\n{'='*60}")
        print(f"TRADING STATUS")
        print(f"{'='*60}")
        
        # Positions
        print("POSITIONS:")
        for ticker, position in self.positions.items():
            if position != 0:
                print(f"  {ticker}: {position:,}")
        
        # Statistics
        print(f"\nSTATISTICS:")
        print(f"  Arbitrage: {self.stats['arbitrage_successes']}/{self.stats['arbitrage_attempts']} successful")
        print(f"  Tenders: {self.stats['tender_successes']}/{self.stats['tender_attempts']} successful")
        print(f"  Total Profit: ${self.stats['total_profit']:.2f}")
        
        # Performance metrics
        perf_stats = self.performance_tracker.get_statistics()
        if perf_stats['total_trades'] > 0:
            print(f"  Win Rate: {perf_stats['win_rate']:.1%}")
            print(f"  Avg Profit/Trade: ${perf_stats['avg_profit']:.2f}")
        
        print(f"{'='*60}\n")
    
    def run_trading_loop(self):
        """Main trading loop"""
        print("Starting trading loop...")
        self.is_running = True
        
        tick_count = 0
        last_status_time = time.time()
        status_interval = 30  # Print status every 30 seconds
        
        try:
            while self.is_running:
                tick, status = get_tick_status()
                
                if status != "ACTIVE":
                    print(f"Trading stopped - Status: {status}")
                    break
                
                tick_count += 1
                current_time = time.time()
                
                # Update positions
                self.update_positions()
                
                # Check for opportunities
                try:
                    self.check_arbitrage_opportunities()
                    self.check_tender_opportunities()
                    
                    if self.stat_arb:
                        self.update_statistical_arbitrage()
                        
                except Exception as e:
                    print(f"Error in opportunity check: {e}")
                
                # Print periodic status
                if current_time - last_status_time >= status_interval:
                    self.print_status()
                    last_status_time = current_time
                
                # Brief pause to prevent API overload
                sleep(0.2)
                
        except KeyboardInterrupt:
            print("\nReceived interrupt signal - shutting down...")
        except Exception as e:
            print(f"Critical error in trading loop: {e}")
        finally:
            self.is_running = False
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown procedure"""
        print("\nShutting down trading bot...")
        
        # Final status
        self.print_status()
        
        # Save performance log
        save_performance_log(self.performance_tracker)
        
        # Print final statistics
        print("FINAL RESULTS:")
        print(f"  Total trades executed: {self.performance_tracker.get_statistics()['total_trades']}")
        print(f"  Total profit: ${self.stats['total_profit']:.2f}")
        
        print("Shutdown complete.")

# =========================================================================================
# === SIGNAL HANDLERS ===
# =========================================================================================

bot_instance = None

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global bot_instance
    print(f"\nReceived signal {signum}")
    if bot_instance:
        bot_instance.is_running = False
    sys.exit(0)

# =========================================================================================
# === MAIN EXECUTION ===
# =========================================================================================

def main():
    """Main execution function"""
    global bot_instance
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("="*80)
    print("RIT ETF ARBITRAGE ALGORITHM - PRODUCTION VERSION")
    print("Rotman BMO Finance Research and Trading Lab")
    print("="*80)
    
    # Initialize bot
    bot_instance = ETFArbitrageBot()
    
    # Initialize all systems
    if not bot_instance.initialize_systems():
        print("Failed to initialize systems. Exiting...")
        return
    
    # Run the trading loop
    bot_instance.run_trading_loop()

if __name__ == "__main__":
    main()