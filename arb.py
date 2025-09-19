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
        """Get current prices and calculate two log-ratio spreads (short and long)"""
        bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
        bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
        ritc_bid, ritc_ask, _, _ = best_bid_ask(RITC)
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)

        if not all([bull_bid > 0, bear_bid > 0, ritc_bid > 0, usd_bid > 0]):
            return None

        # Short spread: short ETF (pay ask), long basket (buy at bid)
        etf_cad_short = ritc_ask * usd_ask
        basket_cad_short = bull_bid + bear_bid
        spread_short = np.log(etf_cad_short / basket_cad_short)

        # Long spread: long ETF (sell at bid), short basket (sell at ask)
        etf_cad_long = ritc_bid * usd_bid
        basket_cad_long = bull_ask + bear_ask
        spread_long = np.log(etf_cad_long / basket_cad_long)

        return {
            'spread_short': spread_short,
            'spread_long': spread_long,
            'bull_bid': bull_bid, 'bull_ask': bull_ask,
            'bear_bid': bear_bid, 'bear_ask': bear_ask,
            'ritc_bid': ritc_bid, 'ritc_ask': ritc_ask,
            'usd_bid': usd_bid, 'usd_ask': usd_ask
        }

    def update_spread_history(self, spread_short, spread_long):
        self.recent_devs.append((spread_short, spread_long))
        if len(self.recent_devs) > self.dev_window:
            self.recent_devs.pop(0)

    def calc_mean_std(self):
        if len(self.recent_devs) < 20:
            return None, None, None, None
        arr = np.array(self.recent_devs)
        mean_short = np.mean(arr[:,0])
        std_short = np.std(arr[:,0])
        mean_long = np.mean(arr[:,1])
        std_long = np.std(arr[:,1])
        return mean_short, std_short, mean_long, std_long

    def enter_position(self, size, direction):
        entry_trades = {}
        try:
            if direction == "SHORT":
                etf = place_mkt(RITC, "SELL", size)
                if not etf: return False
                usd = place_mkt(USD, "SELL", etf['vwap'] * size)
                bull = place_mkt(BULL, "BUY", size)
                bear = place_mkt(BEAR, "BUY", size)
                if not (usd and bull and bear): return False
                entry_trades = {'etf': etf, 'usd': usd, 'bull': bull, 'bear': bear}
            else:
                bull = place_mkt(BULL, "SELL", size)
                bear = place_mkt(BEAR, "SELL", size)
                if not (bull and bear): return False
                etf = place_mkt(RITC, "BUY", size)
                if not etf: return False
                usd = place_mkt(USD, "BUY", etf['vwap'] * size)
                if not usd: return False
                entry_trades = {'etf': etf, 'usd': usd, 'bull': bull, 'bear': bear}
            position = {
                'direction': direction,
                'size': size,
                'entry_time': time.time(),
                'entry_trades': entry_trades
            }
            self.positions.append(position)
            print(f"StatArb: {direction} {size} shares")
            return True
        except Exception as e:
            print(f"Entry error: {e}")
            return False

    def should_exit(self, pos, data, mean_short, std_short, mean_long, std_long):
        holding_time = time.time() - pos['entry_time']
        if pos['direction'] == "SHORT":
            current_spread = data['spread_short']
            if current_spread <= mean_short + std_short:
                return True, "mean_reversion"
        else:
            current_spread = data['spread_long']
            if current_spread >= mean_long - std_long:
                return True, "mean_reversion"
        if holding_time > self.max_hold_time:
            return True, "time"
        return False, None

    def exit_position(self, pos, direction):
        size = pos['size']
        exit_trades = {}
        try:
            if direction == "SHORT":
                etf = place_mkt(RITC, "BUY", size)
                if not etf: return False
                usd = place_mkt(USD, "BUY", etf['vwap'] * size)
                bull = place_mkt(BULL, "SELL", size)
                bear = place_mkt(BEAR, "SELL", size)
                if not (usd and bull and bear): return False
                exit_trades = {'etf': etf, 'usd': usd, 'bull': bull, 'bear': bear}
            else:
                etf = place_mkt(RITC, "SELL", size)
                if not etf: return False
                usd = place_mkt(USD, "SELL", etf['vwap'] * size)
                bull = place_mkt(BULL, "BUY", size)
                bear = place_mkt(BEAR, "BUY", size)
                if not (usd and bull and bear): return False
                exit_trades = {'etf': etf, 'usd': usd, 'bull': bull, 'bear': bear}
            pos['exit_trades'] = exit_trades
            return True
        except Exception as e:
            print(f"Exit error: {e}")
            return False

    def calculate_pnl(self, pos):
        size = pos['size']
        entry = pos['entry_trades']
        exit = pos['exit_trades']
        if pos['direction'] == "SHORT":
            etf_pnl = (entry['etf']['vwap'] - exit['etf']['vwap']) * size * entry['usd']['vwap']
            bull_pnl = (exit['bull']['vwap'] - entry['bull']['vwap']) * size
            bear_pnl = (exit['bear']['vwap'] - entry['bear']['vwap']) * size
        else:
            etf_pnl = (exit['etf']['vwap'] - entry['etf']['vwap']) * size * entry['usd']['vwap']
            bull_pnl = (entry['bull']['vwap'] - exit['bull']['vwap']) * size
            bear_pnl = (entry['bear']['vwap'] - exit['bear']['vwap']) * size
        total_pnl = etf_pnl + bull_pnl + bear_pnl
        total_pnl -= size * 0.06
        return total_pnl

    def run_strategy(self):
        if not within_limits():
            return

        data = self.get_market_data()
        if not data:
            return

        self.update_spread_history(data['spread_short'], data['spread_long'])
        mean_short, std_short, mean_long, std_long = self.calc_mean_std()
        if mean_short is None:
            return

        # Manage existing positions
        for pos in self.positions[:]:
            should_exit, reason = self.should_exit(pos, data, mean_short, std_short, mean_long, std_long)
            if should_exit:
                direction = pos['direction']
                if self.exit_position(pos, direction):
                    holding_time = int(time.time() - pos['entry_time'])
                    pnl = self.calculate_pnl(pos)
                    self.pnl += pnl
                    self.closed_trades.append({'pnl': pnl, 'reason': reason, 'hold': holding_time})
                    print(f"StatArb: CLOSED {direction} after {holding_time}s ({reason}) | PnL: {pnl:.2f} | Total: {self.pnl:.2f}")
                    self.positions.remove(pos)

        # Enter new position if none active
        if len(self.positions) == 0:
            size = 5000  # or self.max_size
            if data['spread_short'] >= mean_short + 2 * std_short:
                self.enter_position(size, "SHORT")
            elif data['spread_long'] <= mean_long - 2 * std_long: