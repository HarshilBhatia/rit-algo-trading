
from final_utils import *
import time
import numpy as np

class ETFArbitrageTrader:
    def __init__(self):
        # Position tracking
        self.positions = []
        self.pnl = 0.0
        self.total_trades = 0
        self.successful_arbs = 0
        
        # Strategy parameters
        self.min_profit_threshold = 0.10  # Minimum profit per share in CAD
        self.max_position_size = 5000     # Max shares per trade
        self.transaction_fee = 0.02       # Fee per share
        self.converter_cost = 1500        # Cost per converter use
        self.position_limit_buffer = 0.8  # Use 80% of available limits
        
        # Risk management
        self.max_hold_time = 240          # 4 minutes max hold
        self.stop_loss_pct = 0.02         # 2% stop loss
        
        # Tender offer tracking
        self.last_tender_check = 0
        self.tender_check_interval = 5    # Check every 5 seconds
        
    def get_current_prices(self):
        """Get current bid/ask prices for all securities"""
        try:
            bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
            bear_bid, bear_ask, _, _ = best_bid_ask(BEAR) 
            ritc_bid, ritc_ask, _, _ = best_bid_ask(RITC)
            usd_bid, usd_ask, _, _ = best_bid_ask(USD)
            
            # Validate all prices are positive
            if not all(p > 0 for p in [bull_bid, bull_ask, bear_bid, bear_ask, 
                                      ritc_bid, ritc_ask, usd_bid, usd_ask]):
                return None
                
            return {
                'bull_bid': bull_bid, 'bull_ask': bull_ask,
                'bear_bid': bear_bid, 'bear_ask': bear_ask,
                'ritc_bid': ritc_bid, 'ritc_ask': ritc_ask,
                'usd_bid': usd_bid, 'usd_ask': usd_ask
            }
        except Exception as e:
            print(f"Error getting prices: {e}")
            return None
    
    def calculate_arbitrage_opportunity(self, prices):
        """Calculate potential arbitrage opportunities"""
        # Fair value of RITC = (BULL + BEAR) / USD_rate
        
        # Scenario 1: Buy RITC, Sell BULL+BEAR (RITC undervalued)
        # Cost: RITC_ask * USD_ask + transaction fees
        # Revenue: BULL_bid + BEAR_bid - transaction fees
        ritc_cost_cad = prices['ritc_ask'] * prices['usd_ask']
        basket_revenue_cad = prices['bull_bid'] + prices['bear_bid']
        buy_ritc_profit = basket_revenue_cad - ritc_cost_cad - (3 * self.transaction_fee)
        
        # Scenario 2: Sell RITC, Buy BULL+BEAR (RITC overvalued)  
        # Revenue: RITC_bid * USD_bid - transaction fees
        # Cost: BULL_ask + BEAR_ask + transaction fees
        ritc_revenue_cad = prices['ritc_bid'] * prices['usd_bid']
        basket_cost_cad = prices['bull_ask'] + prices['bear_ask']
        sell_ritc_profit = ritc_revenue_cad - basket_cost_cad - (3 * self.transaction_fee)
        
        return {
            'buy_ritc_profit': buy_ritc_profit,
            'sell_ritc_profit': sell_ritc_profit,
            'ritc_fair_value': (prices['bull_bid'] + prices['bull_ask'] + 
                               prices['bear_bid'] + prices['bear_ask']) / (4 * prices['usd_ask']),
            'ritc_mid': (prices['ritc_bid'] + prices['ritc_ask']) / 2
        }
    
    def check_position_limits(self, trade_size):
        """Check if trade would exceed position limits"""
        try:
            # Get current positions
            bull_pos = get_position(BULL)
            bear_pos = get_position(BEAR)  
            ritc_pos = get_position(RITC)
            
            # RITC positions count double toward limits
            effective_ritc_pos = ritc_pos * 2
            
            # Calculate gross and net limits after proposed trade
            current_gross = abs(bull_pos) + abs(bear_pos) + abs(effective_ritc_pos)
            current_net = bull_pos + bear_pos + effective_ritc_pos
            
            # Check if adding trade_size would exceed limits
            new_gross = current_gross + (trade_size * 3)  # 3 securities involved
            new_net = abs(current_net + trade_size * 2)   # Net impact
            
            # Use buffer to stay within limits
            return (new_gross < get_gross_limit() * self.position_limit_buffer and
                    new_net < get_net_limit() * self.position_limit_buffer)
        except:
            return False
    
    def execute_buy_ritc_arbitrage(self, trade_size, prices):
        """Execute arbitrage: Buy RITC, Sell BULL+BEAR"""
        trades = {}
        try:
            print(f"Executing BUY RITC arbitrage for {trade_size} shares")
            
            # Step 1: Buy RITC
            ritc_order = place_mkt(RITC, "BUY", trade_size)
            if not ritc_order:
                print("Failed to buy RITC")
                return None
            trades['ritc'] = ritc_order
            
            # Step 2: Buy USD for RITC purchase
            usd_needed = ritc_order['vwap'] * trade_size
            usd_order = place_mkt(USD, "BUY", usd_needed)
            if not usd_order:
                print("Failed to buy USD")
                return None
            trades['usd'] = usd_order
            
            # Step 3: Sell BULL
            bull_order = place_mkt(BULL, "SELL", trade_size)
            if not bull_order:
                print("Failed to sell BULL")
                return None
            trades['bull'] = bull_order
            
            # Step 4: Sell BEAR
            bear_order = place_mkt(BEAR, "SELL", trade_size)
            if not bear_order:
                print("Failed to sell BEAR") 
                return None
            trades['bear'] = bear_order
            
            return trades
            
        except Exception as e:
            print(f"Error in buy RITC arbitrage: {e}")
            return None
    
    def execute_sell_ritc_arbitrage(self, trade_size, prices):
        """Execute arbitrage: Sell RITC, Buy BULL+BEAR"""
        trades = {}
        try:
            print(f"Executing SELL RITC arbitrage for {trade_size} shares")
            
            # Step 1: Sell RITC
            ritc_order = place_mkt(RITC, "SELL", trade_size)
            if not ritc_order:
                print("Failed to sell RITC")
                return None
            trades['ritc'] = ritc_order
            
            # Step 2: Sell USD from RITC sale
            usd_received = ritc_order['vwap'] * trade_size
            usd_order = place_mkt(USD, "SELL", usd_received)
            if not usd_order:
                print("Failed to sell USD")
                return None
            trades['usd'] = usd_order
            
            # Step 3: Buy BULL
            bull_order = place_mkt(BULL, "BUY", trade_size)
            if not bull_order:
                print("Failed to buy BULL")
                return None
            trades['bull'] = bull_order
            
            # Step 4: Buy BEAR
            bear_order = place_mkt(BEAR, "BUY", trade_size)
            if not bear_order:
                print("Failed to buy BEAR")
                return None
            trades['bear'] = bear_order
            
            return trades
            
        except Exception as e:
            print(f"Error in sell RITC arbitrage: {e}")
            return None
    
    def use_converter_if_needed(self, direction):
        """Use ETF creation/redemption converters when market liquidity is insufficient"""
        try:
            if direction == "CREATE":
                # Convert BULL+BEAR to RITC
                result = use_converter("ETF-Creation")
                print(f"Used ETF Creation converter: {result}")
                return result
            elif direction == "REDEEM":
                # Convert RITC to BULL+BEAR
                result = use_converter("ETF-Redemption") 
                print(f"Used ETF Redemption converter: {result}")
                return result
        except Exception as e:
            print(f"Converter error: {e}")
            return False
    
    def calculate_position_pnl(self, position):
        """Calculate P&L for a closed position"""
        try:
            trades = position['trades']
            direction = position['direction']
            size = position['size']
            
            if direction == "BUY_RITC":
                # Revenue from selling BULL+BEAR
                bull_revenue = trades['bull']['vwap'] * size
                bear_revenue = trades['bear']['vwap'] * size
                
                # Cost of buying RITC (in CAD terms)
                ritc_cost_cad = trades['ritc']['vwap'] * trades['usd']['vwap'] * size
                
                gross_pnl = bull_revenue + bear_revenue - ritc_cost_cad
                
            else:  # SELL_RITC
                # Revenue from selling RITC (in CAD terms)
                ritc_revenue_cad = trades['ritc']['vwap'] * trades['usd']['vwap'] * size
                
                # Cost of buying BULL+BEAR
                bull_cost = trades['bull']['vwap'] * size
                bear_cost = trades['bear']['vwap'] * size
                
                gross_pnl = ritc_revenue_cad - bull_cost - bear_cost
            
            # Subtract transaction fees (3 securities * size * fee)
            net_pnl = gross_pnl - (3 * size * self.transaction_fee)
            
            return net_pnl
            
        except Exception as e:
            print(f"Error calculating P&L: {e}")
            return 0.0
    
    def check_tender_offers(self):
        """Check for and evaluate tender offers"""
        try:
            current_time = time.time()
            if current_time - self.last_tender_check < self.tender_check_interval:
                return
                
            self.last_tender_check = current_time
            
            # This would need to be implemented based on the specific API
            # for checking tender offers in the RIT system
            tender_offers = get_tender_offers() if hasattr(__builtins__, 'get_tender_offers') else []
            
            for offer in tender_offers:
                if self.evaluate_tender_offer(offer):
                    self.accept_tender_offer(offer)
                    
        except Exception as e:
            print(f"Error checking tender offers: {e}")
    
    def evaluate_tender_offer(self, offer):
        """Evaluate if a tender offer is profitable"""
        try:
            tender_price = offer['price']
            size = offer['size']
            
            # Get current market prices
            prices = self.get_current_prices()
            if not prices:
                return False
            
            # Calculate cost to unwind position after accepting tender
            # If we sell RITC in tender, we need to buy back basket
            unwind_cost = prices['bull_ask'] + prices['bear_ask'] + (2 * self.transaction_fee)
            
            # Calculate profit: tender price (in CAD) - unwind cost
            tender_price_cad = tender_price * prices['usd_bid']
            expected_profit = tender_price_cad - unwind_cost
            
            # Accept if profit exceeds threshold
            return expected_profit > self.min_profit_threshold
            
        except Exception as e:
            print(f"Error evaluating tender: {e}")
            return False
    
    def accept_tender_offer(self, offer):
        """Accept a profitable tender offer"""
        try:
            # Implementation would depend on RIT API
            print(f"Accepting tender offer: {offer}")
            # accept_tender(offer['id'])  # Hypothetical API call
        except Exception as e:
            print(f"Error accepting tender: {e}")
    
    def manage_existing_positions(self):
        """Manage and potentially close existing positions"""
        for position in self.positions[:]:  # Use slice to avoid modification during iteration
            hold_time = time.time() - position['entry_time']
            
            # Time-based exit
            if hold_time > self.max_hold_time:
                self.close_position(position, "time_limit")
                continue
                
            # P&L based exit (if position can be marked to market)
            try:
                current_pnl = self.estimate_current_pnl(position)
                if current_pnl < -position['size'] * self.stop_loss_pct:
                    self.close_position(position, "stop_loss")
                    continue
            except:
                pass
    
    def estimate_current_pnl(self, position):
        """Estimate current mark-to-market P&L of position"""
        try:
            prices = self.get_current_prices()
            if not prices:
                return 0.0
                
            size = position['size']
            direction = position['direction']
            entry_trades = position['trades']
            
            if direction == "BUY_RITC":
                # Current value of BULL+BEAR we sold
                current_basket_value = (prices['bull_bid'] + prices['bear_bid']) * size
                # Current cost to buy back RITC 
                current_ritc_cost = prices['ritc_ask'] * prices['usd_ask'] * size
                # Original cost we paid for RITC
                original_ritc_cost = entry_trades['ritc']['vwap'] * entry_trades['usd']['vwap'] * size
                # Original revenue from selling BULL+BEAR
                original_basket_revenue = (entry_trades['bull']['vwap'] + entry_trades['bear']['vwap']) * size
                
                # P&L = (current_basket_value - original_basket_revenue) - (current_ritc_cost - original_ritc_cost)
                unrealized_pnl = (current_basket_value - original_basket_revenue) - (current_ritc_cost - original_ritc_cost)
                
            else:  # SELL_RITC
                # Current value of RITC we sold
                current_ritc_value = prices['ritc_bid'] * prices['usd_bid'] * size
                # Current cost to buy back BULL+BEAR
                current_basket_cost = (prices['bull_ask'] + prices['bear_ask']) * size
                # Original revenue from selling RITC
                original_ritc_revenue = entry_trades['ritc']['vwap'] * entry_trades['usd']['vwap'] * size
                # Original cost we paid for BULL+BEAR
                original_basket_cost = (entry_trades['bull']['vwap'] + entry_trades['bear']['vwap']) * size
                
                # P&L = (original_ritc_revenue - current_ritc_value) - (current_basket_cost - original_basket_cost)
                unrealized_pnl = (original_ritc_revenue - current_ritc_value) - (current_basket_cost - original_basket_cost)
            
            return unrealized_pnl
            
        except Exception as e:
            print(f"Error estimating P&L: {e}")
            return 0.0
    
    def close_position(self, position, reason):
        """Close an existing position"""
        try:
            # This would reverse the original trades
            # Implementation depends on position tracking structure
            pnl = self.calculate_position_pnl(position)
            self.pnl += pnl
            self.positions.remove(position)
            print(f"Closed position: {reason}, P&L: {pnl:.2f}")
        except Exception as e:
            print(f"Error closing position: {e}")
    
    def run_strategy(self):
        """Main strategy execution loop"""
        try:
            # Check if we're within trading limits
            if not within_limits():
                return
            
            # Get current market prices
            prices = self.get_current_prices()
            if not prices:
                return
            
            # Manage existing positions
            self.manage_existing_positions()
            
            # Check for tender offers
            self.check_tender_offers()
            
            # Look for new arbitrage opportunities
            arb_opps = self.calculate_arbitrage_opportunity(prices)
            
            # Determine trade size (start smaller, can increase based on performance)
            base_trade_size = min(1000, self.max_position_size)
            
            # Execute arbitrage if profitable
            if arb_opps['buy_ritc_profit'] > self.min_profit_threshold:
                if self.check_position_limits(base_trade_size):
                    trades = self.execute_buy_ritc_arbitrage(base_trade_size, prices)
                    if trades:
                        position = {
                            'direction': 'BUY_RITC',
                            'size': base_trade_size,
                            'entry_time': time.time(),
                            'trades': trades
                        }
                        self.positions.append(position)
                        self.successful_arbs += 1
                        print(f"Opened BUY_RITC position, expected profit: {arb_opps['buy_ritc_profit']:.2f}")
                        
            elif arb_opps['sell_ritc_profit'] > self.min_profit_threshold:
                if self.check_position_limits(base_trade_size):
                    trades = self.execute_sell_ritc_arbitrage(base_trade_size, prices)
                    if trades:
                        position = {
                            'direction': 'SELL_RITC', 
                            'size': base_trade_size,
                            'entry_time': time.time(),
                            'trades': trades
                        }
                        self.positions.append(position)
                        self.successful_arbs += 1
                        print(f"Opened SELL_RITC position, expected profit: {arb_opps['sell_ritc_profit']:.2f}")
            
            # Print status occasionally
            self.total_trades += 1
            if self.total_trades % 100 == 0:
                print(f"Status: {self.successful_arbs} arbitrages, Total P&L: {self.pnl:.2f}")
                
        except Exception as e:
            print(f"Error in main strategy: {e}")

# Global trader instance
# trader = ETFArbitrageTrader()

# def main():
#     """Main execution function"""
#     trader.run_strategy()

# if __name__ == "__main__":
#     main()