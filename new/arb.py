from final_utils import *
import time
import numpy as np

class StatArbTrader:
    def __init__(self):
        self.positions = []
        self.dev_window = 30
        self.recent_devs = []
        self.max_size = 1000
        self.max_hold_time = 300    # 5 minutes
        self.pnl = 0.0
        self.closed_trades = []

    def get_market_data(self):
        """Get current prices and calculate log-ratio spread"""
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

        # Use log ratio for spread
        spread = np.log(etf_cad / basket_cad)

        return {
            'etf_cad': etf_cad,
            'basket_cad': basket_cad,
            'spread': spread,
            'bull_mid': bull_mid,
            'bear_mid': bear_mid,
            'ritc_mid': ritc_mid,
            'usd_mid': usd_mid,
            'bull_bid': bull_bid, 'bull_ask': bull_ask,
            'bear_bid': bear_bid, 'bear_ask': bear_ask,
            'ritc_bid': ritc_bid, 'ritc_ask': ritc_ask,
            'usd_bid': usd_bid, 'usd_ask': usd_ask
        }

    def update_spread_history(self, dev):
        self.recent_devs.append(dev)
        if len(self.recent_devs) > self.dev_window:
            self.recent_devs.pop(0)

    def calc_mean_std(self):
        if len(self.recent_devs) < 20:
            return None, None
        mean = np.mean(self.recent_devs)
        std = np.std(self.recent_devs)
        return mean, std

    def enter_position(self, data, size, direction):
        spread = data['spread']
        if direction == "SHORT":
            success = self.short_etf_long_basket(size, data)
        else:
            success = self.long_etf_short_basket(size, data)

        if success:
            position = {
                'direction': direction,
                'size': size,
                'entry_time': time.time(),
                'entry_spread': spread,
                'entry_prices': data
            }
            self.positions.append(position)
            print(f"StatArb: {direction} {size} shares, log-dev={spread:.4f}")
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

    def should_exit(self, pos, data, mean, std):
        holding_time = time.time() - pos['entry_time']
        current_dev = data['spread']

        # Exit when spread crosses mean (mean reversion)
        if pos['direction'] == "SHORT" and current_dev <= mean + std:
            return True, "mean_reversion"
        if pos['direction'] == "LONG" and current_dev >= mean - std:
            return True, "mean_reversion"

        # Time limit exit
        if holding_time > self.max_hold_time:
            return True, "time"

        return False, None

    def exit_position(self, pos, data, reason):
        size = pos['size']
        direction = pos['direction']
        success = False
        if direction == "SHORT":
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
        if pos['direction'] == "SHORT":
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

        self.update_spread_history(data['spread'])
        mean, std = self.calc_mean_std()
        if mean is None or std is None:
            return

        # Manage existing positions
        for pos in self.positions[:]:
            should_exit, reason = self.should_exit(pos, data, mean, std)
            if should_exit:
                self.exit_position(pos, data, reason)

        # Enter new position if none active
        if len(self.positions) == 0:
            size = 5000  # or self.max_size
            dev = data['spread']
            print(mean, std, dev)
            if dev >= mean + 2 * std:
                self.enter_position(data, size, "SHORT")
            elif dev <= mean - 2 * std:
                self.enter_position(data, size, 'LONG')