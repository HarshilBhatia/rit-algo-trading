# from final_utils import *
# import time
# import numpy as np

# class StatArbTrader:
#     def __init__(self):
#         self.positions = []
#         self.entry_threshold = 0.5  # 0.5% deviation to enter
#         self.exit_threshold = 0.2   # 0.2% deviation to exit
#         self.max_size = 1000
#         self.max_hold_time = 300    # 5 minutes
#         self.stop_loss_mult = 2.0
        
#     def get_market_data(self):
#         """Get current prices and calculate deviation"""
#         bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
#         bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
#         ritc_bid, ritc_ask, _, _ = best_bid_ask(RITC)
#         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        
#         if not all([bull_bid > 0, bear_bid > 0, ritc_bid > 0, usd_bid > 0]):
#             return None
            
#         # Calculate fair value relationship
#         bull_mid = (bull_bid + bull_ask) / 2
#         bear_mid = (bear_bid + bear_ask) / 2
#         ritc_mid = (ritc_bid + ritc_ask) / 2
#         usd_mid = (usd_bid + usd_ask) / 2
        
#         etf_cad = ritc_mid * usd_mid
#         basket_cad = bull_mid + bear_mid
#         deviation = etf_cad - basket_cad
#         deviation_pct = (deviation / basket_cad) * 100
        
#         return {
#             'etf_cad': etf_cad,
#             'basket_cad': basket_cad,
#             'deviation': deviation,
#             'deviation_pct': deviation_pct,
#             'bull_bid': bull_bid, 'bull_ask': bull_ask,
#             'bear_bid': bear_bid, 'bear_ask': bear_ask,
#             'ritc_bid': ritc_bid, 'ritc_ask': ritc_ask,
#             'usd_bid': usd_bid, 'usd_ask': usd_ask
#         }
    
#     def calc_position_size(self, deviation_pct):
#         """Calculate optimal position size"""
#         # base_size = min(self.max_size, max(100, int(abs(deviation_pct) * 200)))
#         base_size = 100
        
#         # Ensure profit > transaction costs (3 trades × $0.02/share)
#         min_profit = 0  # CAD
#         transaction_cost = base_size * 0.06
        
#         print('expected profit:', deviation_pct*base_size - transaction_cost)
#         return base_size
    
#     def enter_position(self, data, size):
#         """Enter new statistical arbitrage position"""
#         deviation = data['deviation']
        
#         if deviation > 0:
#             # ETF overvalued: SHORT ETF + LONG BASKET
#             success = self.short_etf_long_basket(size, data)
#             direction = "SHORT_ETF"
#         else:
#             # ETF undervalued: LONG ETF + SHORT BASKET  
#             success = self.long_etf_short_basket(size, data)
#             direction = "LONG_ETF"
            
#         if success:
#             position = {
#                 'direction': direction,
#                 'size': size,
#                 'entry_time': time.time(),
#                 'entry_deviation': deviation,
#                 'deviation_pct': data['deviation_pct'],
#                 'stop_loss': deviation * (1 + self.stop_loss_mult * np.sign(deviation))
#             }
#             self.positions.append(position)
#             print(f"StatArb: {direction} {size} shares, dev={deviation:.3f}")
#             return True

#         return False
    
#     def short_etf_long_basket(self, size, data):
#         """Sell ETF, Buy BULL+BEAR"""
#         try:
#             # Sell ETF → get USD → convert to CAD
#             etf_result = place_mkt(RITC, "SELL", size)
#             if not etf_result: return False
            
#             usd_proceeds = etf_result['vwap'] * size
#             place_mkt(USD, "SELL", usd_proceeds)
            
#             # Buy basket
#             bull_result = place_mkt(BULL, "BUY", size)
#             bear_result = place_mkt(BEAR, "BUY", size)
            
#             return bool(bull_result and bear_result)
#         except:
#             return False
    
#     def long_etf_short_basket(self, size, data):
#         """Buy ETF, Sell BULL+BEAR"""
#         try:
#             # Sell basket → get CAD
#             bull_result = place_mkt(BULL, "SELL", size)
#             bear_result = place_mkt(BEAR, "SELL", size)
#             if not (bull_result and bear_result): return False
            
#             # Convert CAD to USD → buy ETF
#             # usd_needed = data['ritc_ask'] * size
#             etf_result = place_mkt(RITC, "BUY", size)            
#             usd = etf_result['vwap'] * size
#             fx_result = place_mkt(USD, "BUY", usd)            
#             return bool(etf_result)
#         except:
#             return False
    
#     def should_exit(self, pos, data):
#         """Check if position should be exited"""
#         current_dev_pct = abs(data['deviation_pct'])
#         holding_time = time.time() - pos['entry_time']
        
#         # Mean reversion exit
#         if abs(pos['deviation_pct'] -data['deviation_pct']) > 0.2:
#             # this is so meh, should do something better. 
#             # historically store reversion. 
#             return True, "reversion"
            
#         # Time limit exit
#         if holding_time > self.max_hold_time:
#             return True, "time"
            
#         # Stop loss exit
#         current_dev = data['deviation']
#         if pos['direction'] == "SHORT_ETF":
#             if current_dev > pos['stop_loss']:
#                 return True, "stop_loss"
#         else:
#             if current_dev < pos['stop_loss']:
#                 return True, "stop_loss"
                
#         return False, None
    
#     def exit_position(self, pos, data, reason):
#         """Exit statistical arbitrage position"""
#         size = pos['size']
#         direction = pos['direction']
        
#         success = False
#         if direction == "SHORT_ETF":
#             # Close: Buy ETF, Sell basket
#             success = self.close_short_etf(size, data)
#         else:
#             # Close: Sell ETF, Buy basket
#             success = self.close_long_etf(size, data)
        
#         if success:
#             holding_time = int(time.time() - pos['entry_time'])
#             print(f"StatArb: CLOSED {direction} after {holding_time}s ({reason})")
#             self.positions.remove(pos)
#             return True
#         return False
    
#     def close_short_etf(self, size, data):
#         """Close short ETF position"""
#         try:
#             # Get USD → buy ETF
#             etf_result = place_mkt(RITC, "BUY", size)     
#             if not etf_result: return False

#             usd = etf_result['vwap'] * size
#             fx_result = place_mkt(USD, "BUY", usd)                        
            
#             # Sell basket
#             bull_result = place_mkt(BULL, "SELL", size)
#             bear_result = place_mkt(BEAR, "SELL", size)
            
#             return bool(bull_result and bear_result)
#         except:
#             return False
    
#     def close_long_etf(self, size, data):
#         """Close long ETF position"""
#         try:
#             # Sell ETF → get USD → convert to CAD
#             etf_result = place_mkt(RITC, "SELL", size)
#             if not etf_result: return False
            
#             usd_proceeds = etf_result['vwap'] * size
#             place_mkt(USD, "SELL", usd_proceeds)
            
#             # Buy basket
#             bull_result = place_mkt(BULL, "BUY", size)
#             bear_result = place_mkt(BEAR, "BUY", size)
            
#             return bool(bull_result and bear_result)
#         except:
#             return False
    
#     def run_strategy(self):
#         """Main strategy execution"""
#         if not within_limits():
#             return
            
#         data = self.get_market_data()
#         if not data:
#             return
            
#         # Manage existing positions
#         for pos in self.positions[:]:  # Copy list to avoid modification issues
#             should_exit, reason = self.should_exit(pos, data)
#             if should_exit:
#                 self.exit_position(pos, data, reason)
        
#         # Enter new position if none active
#         if len(self.positions) == 0:
#             deviation_pct = abs(data['deviation_pct'])
#             if deviation_pct > 0.3:
#                 size = 1000 
#                 print(deviation_pct, end = ' ')
#                 self.enter_position(data, size)

#                 # print(data['deviation_pct'])
            
#             # if deviation_pct > self.entry_threshold:
#             #     size = self.calc_position_size(deviation_pct)
#             #     print(size)
#             #     if size > 0:
#             #         self.enter_position(data, size)


# if __name__ == "__main__":
#     # Test
#     trader = StatArbTrader()
#     for i in range(3):
#         trader.run_strategy()
#         sleep(1)


from final_utils import *
import time
import numpy as np

class StatArbTrader:
    def __init__(self):
        self.positions = []
        self.dev_window = 50
        self.recent_devs = []
        self.max_size = 1000
        self.max_hold_time = 300    # 5 minutes
        self.stop_loss_mult = 2.0
        self.pnl = 0.0
        self.closed_trades = []

    def get_market_data(self):
        """Get current prices and calculate log-ratio deviation"""
        bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
        bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
        ritc_bid, ritc_ask, _, _ = best_bid_ask(RITC)
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)

        if not all([bull_bid > 0, bear_bid > 0, ritc_bid > 0, usd_bid > 0]):
            return None

        bull_mid = (bull_bid + bull_ask) / 2
        bear_mid = (bear_bid + bear_ask) / 2
        ritc_mid = (ritc_bid + ritc_ask) / 2
        usd_mid = (usd_bid + usd_ask) / 2

        etf_cad = ritc_mid * usd_mid
        basket_cad = bull_mid + bear_mid

        # Use log ratio for deviation
        deviation = np.log(etf_cad / basket_cad)
        deviation_pct = deviation * 100  # for easier thresholding

        return {
            'etf_cad': etf_cad,
            'basket_cad': basket_cad,
            'deviation': deviation,
            'deviation_pct': deviation_pct,
            'bull_mid': bull_mid,
            'bear_mid': bear_mid,
            'ritc_mid': ritc_mid,
            'usd_mid': usd_mid,
            'bull_bid': bull_bid, 'bull_ask': bull_ask,
            'bear_bid': bear_bid, 'bear_ask': bear_ask,
            'ritc_bid': ritc_bid, 'ritc_ask': ritc_ask,
            'usd_bid': usd_bid, 'usd_ask': usd_ask
        }

    def update_deviation_history(self, dev):
        self.recent_devs.append(dev)
        if len(self.recent_devs) > self.dev_window:
            self.recent_devs.pop(0)

    def calc_dynamic_thresholds(self):
        if len(self.recent_devs) < 10:
            return 0.3, 0.1  # fallback
        mean = np.mean(self.recent_devs)
        std = np.std(self.recent_devs)
        entry = abs(mean) + 1.5 * std
        exit = abs(mean) + 0.5 * std
        return entry, exit

    def calc_position_size(self, deviation_pct):
        base_size = 100
        transaction_cost = base_size * 0.06
        return base_size

    def enter_position(self, data, size):
        deviation = data['deviation']
        if deviation > 0:
            success = self.short_etf_long_basket(size, data)
            direction = "SHORT_ETF"
        else:
            success = self.long_etf_short_basket(size, data)
            direction = "LONG_ETF"

        if success:
            position = {
                'direction': direction,
                'size': size,
                'entry_time': time.time(),
                'entry_deviation': deviation,
                'entry_dev_pct': data['deviation_pct'],
                'entry_prices': data,
                'stop_loss': deviation * (1 + self.stop_loss_mult * np.sign(deviation))
            }
            self.positions.append(position)
            print(f"StatArb: {direction} {size} shares, log-dev={deviation:.4f}")
            return True
        return False

    def short_etf_long_basket(self, size, data):
        try:
            etf_result = place_mkt(RITC, "SELL", size)
            if not etf_result: return False
            usd_proceeds = etf_result['vwap'] * size
            place_mkt(USD, "SELL", usd_proceeds)
            bull_result = place_mkt(BULL, "BUY", size)
            bear_result = place_mkt(BEAR, "BUY", size)
            return bool(bull_result and bear_result)
        except:
            return False

    def long_etf_short_basket(self, size, data):
        try:
            bull_result = place_mkt(BULL, "SELL", size)
            bear_result = place_mkt(BEAR, "SELL", size)
            if not (bull_result and bear_result): return False
            etf_result = place_mkt(RITC, "BUY", size)
            usd = etf_result['vwap'] * size
            fx_result = place_mkt(USD, "BUY", usd)
            return bool(etf_result)
        except:
            return False

    def should_exit(self, pos, data):
        holding_time = time.time() - pos['entry_time']
        current_dev = data['deviation']
        entry_dev = pos['entry_deviation']

        # Mean reversion: deviation crosses zero or shrinks by 80%+
        if np.sign(current_dev) != np.sign(entry_dev) or abs(current_dev) < 0.2 * abs(entry_dev):
            return True, "mean_reversion"

        if holding_time > self.max_hold_time:
            return True, "time"

        if pos['direction'] == "SHORT_ETF":
            if current_dev > pos['stop_loss']:
                return True, "stop_loss"
        else:
            if current_dev < pos['stop_loss']:
                return True, "stop_loss"

        return False, None

    def exit_position(self, pos, data, reason):
        size = pos['size']
        direction = pos['direction']
        success = False
        if direction == "SHORT_ETF":
            success = self.close_short_etf(size, data)
        else:
            success = self.close_long_etf(size, data)

        if success:
            holding_time = int(time.time() - pos['entry_time'])
            pnl = self.calculate_pnl(pos, data)
            self.pnl += pnl
            self.closed_trades.append({'pnl': pnl, 'reason': reason, 'hold': holding_time})
            print(f"StatArb: CLOSED {direction} after {holding_time}s ({reason}) | PnL: {pnl:.2f} | Total: {self.pnl:.2f}")
            self.positions.remove(pos)
            return True
        return False

    def calculate_pnl(self, pos, exit_data):
        size = pos['size']
        entry = pos['entry_prices']
        exit = exit_data
        if pos['direction'] == "SHORT_ETF":
            etf_pnl = (entry['ritc_mid'] - exit['ritc_mid']) * size * entry['usd_mid']
            bull_pnl = (exit['bull_mid'] - entry['bull_mid']) * size
            bear_pnl = (exit['bear_mid'] - entry['bear_mid']) * size
        else:
            etf_pnl = (exit['ritc_mid'] - entry['ritc_mid']) * size * entry['usd_mid']
            bull_pnl = (entry['bull_mid'] - exit['bull_mid']) * size
            bear_pnl = (entry['bear_mid'] - exit['bear_mid']) * size
        total_pnl = etf_pnl + bull_pnl + bear_pnl
        total_pnl -= size * 0.06
        return total_pnl

    def close_short_etf(self, size, data):
        try:
            etf_result = place_mkt(RITC, "BUY", size)
            if not etf_result: return False
            usd = etf_result['vwap'] * size
            fx_result = place_mkt(USD, "BUY", usd)
            bull_result = place_mkt(BULL, "SELL", size)
            bear_result = place_mkt(BEAR, "SELL", size)
            return bool(bull_result and bear_result)
        except:
            return False

    def close_long_etf(self, size, data):
        try:
            etf_result = place_mkt(RITC, "SELL", size)
            if not etf_result: return False
            usd_proceeds = etf_result['vwap'] * size
            place_mkt(USD, "SELL", usd_proceeds)
            bull_result = place_mkt(BULL, "BUY", size)
            bear_result = place_mkt(BEAR, "BUY", size)
            return bool(bull_result and bear_result)
        except:
            return False

    def run_strategy(self):
        if not within_limits():
            return

        data = self.get_market_data()
        if not data:
            return

        self.update_deviation_history(data['deviation'])
        entry_th, exit_th = self.calc_dynamic_thresholds()

        # Manage existing positions
        for pos in self.positions[:]:
            should_exit, reason = self.should_exit(pos, data)
            if should_exit:
                self.exit_position(pos, data, reason)

        # Enter new position if none active
        if len(self.positions) == 0:
            deviation_pct = abs(data['deviation_pct'])
            if deviation_pct > entry_th:
                size = self.calc_position_size(deviation_pct)
                self.enter_position(data, size)

# if __name__ == "__main__":
#     trader = StatArbTrader()
#     for i in range(3):
#         trader.run_strategy()
#         time.sleep(1)