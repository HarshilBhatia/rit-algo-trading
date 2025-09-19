
from final_utils import *
import time
from rich import print
import numpy as np

class EvaluateTenders():
    def __init__(self, tender, converter):
        self.tender = tender
        self.action = tender['action']  # SELL or BUY
        self.price = tender['price']
        self.quantity = tender['quantity']
        self.converter = converter
      
    def evaluate_tender_profit(self):
        """Market depth analysis with opportunity ranking"""
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        ritc_depth = best_bid_ask_entire_depth(RITC)
        bull_depth = best_bid_ask_entire_depth(BULL)
        bear_depth = best_bid_ask_entire_depth(BEAR)
        print(f"*** [TENDER EVAL] {self.action} {self.quantity} @ {self.price:.4f} USD ***")
        self.opportunities = []
        if self.action == 'SELL':
            self._add_direct_buy_opportunities(ritc_depth['asks'], usd_bid, usd_ask)
            self._add_converter_buy_opportunities(bull_depth['asks'], bear_depth['asks'], usd_bid)
        else:
            self._add_direct_sell_opportunities(ritc_depth['bids'], usd_bid, usd_ask)
            self._add_converter_sell_opportunities(bull_depth['bids'], bear_depth['bids'], usd_bid)

        self.opportunities.sort(key=lambda x: x['profit_per_share'], reverse=True)
        
        executed, total_profit, = 0, 0
        for opp in self.opportunities:
            if executed >= self.quantity or opp['profit_per_share'] <= 0: break
            take = min(self.quantity - executed, opp['quantity'])
            total_profit += take * opp['profit_per_share']

            executed += take 

        avg_profit = total_profit / executed if executed else 0
        
        return total_profit


    def _add_direct_buy_opportunities(self, ritc_asks, usd_bid, usd_ask):
        for level in ritc_asks:
            if level['quantity'] <= 0: continue
            profit = (self.price - level['price']) * usd_bid - FEE_MKT
            self.opportunities.append({
                'type': 'DIRECT_BUY', 
                'price': level['price'], 'quantity': level['quantity'],
                'profit_per_share': profit})

    def _add_converter_buy_opportunities(self, bull_asks, bear_asks, usd_bid):
        for bull, bear in zip(bull_asks, bear_asks):
            qty = min(bull['quantity'], bear['quantity'])
            if qty <= 0: continue
            total_cost = bull['price'] + bear['price'] + 2 * FEE_MKT + conversion_cost(1)
            profit = self.price * usd_bid - total_cost
            self.opportunities.append({
                'type': 'CONVERTER_BUY',
                'price': total_cost, 'quantity': qty, 'profit_per_share': profit
            })

    def _add_direct_sell_opportunities(self, ritc_bids, usd_bid, usd_ask):
        for level in ritc_bids:
            if level['quantity'] <= 0: continue
            profit = (level['price'] - self.price) * usd_bid - FEE_MKT
            self.opportunities.append({
                'type': 'DIRECT_SELL',
                'price': level['price'], 'quantity': level['quantity'],
                'profit_per_share': profit
            })

    def _add_converter_sell_opportunities(self, bull_bids, bear_bids, usd_bid):
        for bull, bear in zip(bull_bids, bear_bids):
            qty = min(bull['quantity'], bear['quantity'], CONVERTER_BATCH)
            if qty <= 0: continue
            net_rev = bull['price'] + bear['price'] - 2 * FEE_MKT + conversion_cost(1) 
            profit = net_rev - self.price * usd_bid
            self.opportunities.append({
                'type': 'CONVERTER_SELL',
                'price': net_rev, 'quantity': qty, 'profit_per_share': profit
            })
        
    def unwind_tender(self):
        """Accept tender and intelligently unwind position"""
        
        # Accept the tender first
       
        
        # Now we have a position to unwind
        remaining_qty = self.quantity
        total_unwinding_cost = 0
        
        # hedge against the position 
        qty = self.price * self.quantity
        if self.action == 'SELL':
            # print('[USD HEDGE]: Buying', qty)
            fx_hedge('SELL', self.price * self.quantity)
        else:
            # print('[USD HEDGE]: Selling', qty)
            fx_hedge('BUY', self.price * self.quantity)

        while remaining_qty > 0:
            # Determine optimal chunk size (max 10k for converter limit)
            # chunk_size = min(remaining_qty, 10000, 5000)  # Reasonable chunk size, max 5k for execution
            
            # Calculate costs for both methods  
            direct_cost = self.calculate_direct_cost()
            converter_cost = self.calculate_converter_cost()
            
            print(f"\n--- Unwinding shares---")
            print(f"Direct method cost: {direct_cost:.2f} CAD")
            print(f"Converter method cost: {converter_cost:.2f} CAD")
            
            # Choose the cheaper method
            if direct_cost < converter_cost:
                print("✓ Choosing DIRECT method")
                # price, qty = self.execute_converter_unwind(remaining_qty)

                price, qty = self.execute_direct_unwind(remaining_qty)
                actual_cost = qty*price 
            else:
                print("✓ Choosing CONVERTER method")
                # price, qty = self.execute_direct_unwind(remaining_qty)
                price, qty = self.execute_converter_unwind(remaining_qty)
                actual_cost = price*qty
                
            
            remaining_qty -= qty 
            total_unwinding_cost += actual_cost # not sure if this is correct or not.
            print(f"✓ Successfully unwound {qty} shares")
            
            
            # Brief pause between chunks
            if remaining_qty > 0:
                sleep(5)
        
        # Final cleanup of any residual FX exposure
        # THIS should ideally just convert my profit back to CAD!!!
        self.cleanup_fx_exposure()
        
        success_rate = (self.quantity - remaining_qty) / self.quantity
        print(f"\n*********************** [UNWIND COMPLETE] ***********************")
        print(f"Unwound: {self.quantity - remaining_qty}/{self.quantity} shares ({success_rate*100:.1f}%)")
        print(f"Total unwinding cost: {total_unwinding_cost:.2f} CAD")
        
        return success_rate >= 0.95  # 95% success threshold


    def calculate_direct_cost(self):
        """Calculate cost of direct ETF trading"""
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        if self.action == 'SELL':
            # We're short RITC, need to buy RITC directly
            ritc_ask_price, qty = get_top_level_price_and_qty(RITC, "BUY")
            print("direct_p", ritc_ask_price, end = ' ') # this is usd price.
            
            etf_cost_usd = ritc_ask_price * qty 
            fx_cost_cad = etf_cost_usd * usd_ask  + qty * FEE_MKT# Need to buy USD at ask
            return fx_cost_cad
        else:
            ritc_bid_price, qty = get_top_level_price_and_qty(RITC, "SELL")
            print("direct_p", ritc_bid_price, end = ' ')

            etf_revenue_usd = ritc_bid_price * qty 
            fx_revenue_cad = etf_revenue_usd * usd_bid  - qty * FEE_MKT # Sell USD at bid
            return -fx_revenue_cad  # Negative because it's revenue

    def calculate_converter_cost(self):
        """Calculate cost of converter method with proportional pricing"""
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        if self.action == 'SELL':
            # We're short RITC: Buy stocks → Convert to RITC
            bull_ask_price, qty_bull = get_top_level_price_and_qty(BULL, "BUY")
            bear_ask_price, qty_bear = get_top_level_price_and_qty(BEAR, "BUY")
            qty = min(qty_bull, qty_bear)
            stock_cost_cad = (bull_ask_price + bear_ask_price) * qty + qty * 2 * FEE_MKT
            print("c_p", bull_ask_price, bear_ask_price)

            conversion_fee_cad = conversion_cost(qty)
            return stock_cost_cad + conversion_fee_cad
        else:
            # We're long RITC: Convert RITC → Sell stocks
            bull_bid_price, qty_bull = get_top_level_price_and_qty(BULL, "SELL")
            bear_bid_price, qty_bear = get_top_level_price_and_qty(BEAR, "SELL")
            qty = min(qty_bull, qty_bear)
            print("direct_p", bull_ask_price, bear_ask_price)
            stock_revenue_cad = (bull_bid_price + bear_bid_price) * qty - qty * 2 * FEE_MKT
            conversion_fee_cad = conversion_cost(qty)
            return conversion_fee_cad - stock_revenue_cad  # Net cost

    def execute_direct_unwind(self, remaining_qty):
        """Execute direct ETF trading"""
        try:
            if self.action == 'SELL':
                # Buy RITC to cover short
                _, qty = get_top_level_price_and_qty(RITC, "BUY")
                qty = min(qty, MAX_SIZE_EQUITY, remaining_qty)
                result = place_mkt(RITC, "BUY", qty)
                # need to unhedge USD here
                fx_hedge("BUY", result['vwap']*qty)

                if result and result.get('vwap', 0) > 0:
                    print(f"✓ Bought {qty} RITC at {result['vwap']:.4f} USD")
                    return result['vwap'], qty
            else:
                # Sell RITC
                _, qty = get_top_level_price_and_qty(RITC, "SELL")
                qty = min(qty, MAX_SIZE_EQUITY, remaining_qty)

                result = place_mkt(RITC, "SELL", qty)
                # need to unhedge usd 
                fx_hedge("SELL", result['vwap']*qty)

                if result and result.get('vwap', 0) > 0:
                    print(f"✓ Sold {qty} RITC at {result['vwap']:.4f} USD")
                    return result['vwap'], qty
            return 0, 0
        except Exception as e:
            print(f"[ERROR] Direct unwind failed: {e}")
            return 0, 0

    def execute_converter_unwind(self, remaining_qty):
        """Execute converter-based unwinding - can handle any amount up to 10k"""
        try:
            if self.action == 'SELL':
                # We're short RITC: Buy stocks → Convert to RITC
                _, qty_bull = get_top_level_price_and_qty(BULL, "BUY")
                _, qty_bear = get_top_level_price_and_qty(BEAR, "BUY")
                qty = min(qty_bull, qty_bear, MAX_SIZE_EQUITY, remaining_qty)
                bull_result = place_mkt(BULL, "BUY", qty)
                bear_result = place_mkt(BEAR, "BUY", qty)
                if not bull_result or not bear_result:
                    print("[ERROR] Failed to buy stocks")
                    return 0, 0
                print(f"✓ Bought {qty} BULL and BEAR")
                sleep(1)  # Allow orders to settle
                conversion_result = self.converter.convert_bull_bear(qty)
                if not conversion_result or not conversion_result.ok:
                    print(f"[ERROR] ETF creation failed")
                    place_mkt(BULL, "SELL", qty)
                    place_mkt(BEAR, "SELL", qty)
                    return 0, 0

                # unwind expected USD hedge here
                usd_hedge = conversion_cost(qty) 
                fx_hedge("BUY", usd_hedge)
                print(f"✓ Converted {qty} stocks to RITC (cost: {conversion_cost(qty):.2f} CAD)")
                return bull_result['vwap'] + bear_result['vwap'] - conversion_cost(qty), qty
            else:
                # We're long RITC: Convert RITC → Sell stocks
                _, qty_bull = get_top_level_price_and_qty(BULL, "SELL")
                _, qty_bear = get_top_level_price_and_qty(BEAR, "SELL")
                qty = min(qty_bull, qty_bear, MAX_SIZE_EQUITY, remaining_qty)

                conversion_result = self.converter.convert_ritc(qty)
                if not conversion_result or not conversion_result.ok:
                    print(f"[ERROR] ETF redemption failed")
                    return 0, 0
                
                print(f"✓ Converted {qty} RITC to stocks (cost: {conversion_cost(qty):.2f} CAD)")
                bull_result = place_mkt(BULL, "SELL", qty)
                bear_result = place_mkt(BEAR, "SELL", qty)
                
                usd_hedge = conversion_cost(qty) 
                fx_hedge("BUY", usd_hedge)

                if not bull_result or not bear_result:
                    print("[WARNING] Failed to sell some stocks")
                
                print(f"✓ Sold {qty} BULL and BEAR")
                return bull_result['vwap'] + bear_result['vwap'] - conversion_cost(qty), qty
        except Exception as e:
            print(f"[ERROR] Converter unwind failed: {e}")
            return 0, 0
        
    def cleanup_fx_exposure(self):
        """Clean up any residual USD exposure"""
        try:
            sleep(1)  # Allow all trades to settle
            
            # Check actual USD position
            positions = positions_map()
            usd_position = positions.get(USD, 0)
            
            if abs(usd_position) > 0.1:  # Only if meaningful exposure
                action = "SELL" if usd_position > 0 else "BUY"
                result = fx_hedge(action, abs(usd_position))
                                    
        except Exception as e:
            print(f"[ERROR] FX cleanup failed: {e}")




    # ... Your helper methods (_find_optimal_chunk, _calculate_vwap_cost, _calculate_intelligent_delay, cleanup_fx_exposure) remain unchanged ...

    def _find_optimal_chunk(self, book_levels):
        """Calculates the largest order size that meets the slippage tolerance."""
        if not book_levels: return 0
        
        best_price = book_levels[0]['price']
        # A more robust way to check side without relying on 'type' key
        is_ask_side = best_price > book_levels[-1]['price'] if len(book_levels) > 1 else True 
        
        cumulative_qty, cumulative_cost = 0, 0
        
        for level in book_levels:
            if (cumulative_qty + level['quantity']) == 0: continue # Avoid division by zero
            potential_vwap = (cumulative_cost + level['quantity'] * level['price']) / (cumulative_qty + level['quantity'])
            
            if is_ask_side and potential_vwap > (best_price + self.SLIPPAGE_TOLERANCE):
                return int(cumulative_qty)
            if not is_ask_side and potential_vwap < (best_price - self.SLIPPAGE_TOLERANCE):
                return int(cumulative_qty)
            
            cumulative_qty += level['quantity']
            cumulative_cost += level['quantity'] * level['price']

        return int(cumulative_qty)

    def _calculate_vwap_cost(self, book_levels, quantity):
        """Calculates the true VWAP and total cost for executing a given quantity."""
        if not book_levels or quantity <= 0: return (float('inf'), float('inf'))

        filled_qty, total_cost = 0, 0
        for level in book_levels:
            qty_to_take = min(level['quantity'], quantity - filled_qty)
            total_cost += qty_to_take * level['price']
            filled_qty += qty_to_take
            if filled_qty >= quantity: break
        
        if filled_qty < quantity: return (float('inf'), float('inf')) # Not enough liquidity
        return (total_cost, total_cost / filled_qty)


# 1. SENSE: Get fresh market data, including crucial FX rates
            # ritc_book = best_bid_ask_entire_depth(RITC)
            # bull_book = best_bid_ask_entire_depth(BULL)
            # bear_book = best_bid_ask_entire_depth(BEAR)
            # usd_bid, usd_ask, _, _ = best_bid_ask(USD)
            
            # book_side_key = 'asks' if side == 'BUY' else 'bids'

            # # 2. THINK: Decide on the best method and optimal chunk size based on ALL-IN CAD COST
            
            # # --- Direct Route Analysis ---
            # direct_chunk = self._find_optimal_chunk(ritc_book[book_side_key])
            # cost_per_share_cad_direct = self._get_cad_vwap(
            #     'DIRECT', side, direct_chunk, 
            #     {'ritc': ritc_book[book_side_key]}, 
            #     {'bid': usd_bid, 'ask': usd_ask}
            # )

            # # --- Converter Route Analysis ---
            # bull_chunk = self._find_optimal_chunk(bull_book[book_side_key])
            # bear_chunk = self._find_optimal_chunk(bear_book[book_side_key])
            # converter_chunk = min(bull_chunk, bear_chunk)
            # cost_per_share_cad_converter = self._get_cad_vwap(
            #     'CONVERTER', side, converter_chunk,
            #     {'bull': bull_book[book_side_key], 'bear': bear_book[book_side_key]},
            #     {} # No FX needed for CAD assets
            # )