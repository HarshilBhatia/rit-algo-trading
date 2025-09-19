
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
            etf_cost_usd = ritc_ask_price * qty + qty * FEE_MKT
            fx_cost_cad = etf_cost_usd * usd_ask  # Need to buy USD at ask
            return fx_cost_cad
        else:
            ritc_bid_price, qty = get_top_level_price_and_qty(RITC, "SELL")
            etf_revenue_usd = ritc_bid_price * qty - qty * FEE_MKT
            fx_revenue_cad = etf_revenue_usd * usd_bid  # Sell USD at bid
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
            conversion_fee_cad = conversion_cost(qty)
            return stock_cost_cad + conversion_fee_cad
        else:
            # We're long RITC: Convert RITC → Sell stocks
            bull_bid_price, qty_bull = get_top_level_price_and_qty(BULL, "SELL")
            bear_bid_price, qty_bear = get_top_level_price_and_qty(BEAR, "SELL")
            qty = min(qty_bull, qty_bear)
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

# from final_utils import *
# import time
# from rich import print
# import numpy as np

# class EvaluateTendersNew():
#     def __init__(self, tender, converter):
#         self.tender = tender
#         self.action = tender['action']  # 'SELL' or 'BUY'
#         self.price = tender['price']
#         self.quantity = tender['quantity']
#         self.converter = converter
#         # --- TUNABLE PARAMETERS FOR THE NEW STRATEGY ---
#         self.SLIPPAGE_TOLERANCE = 0.02  # Max acceptable slippage in dollars per share
#         self.PATIENCE_WINDOW_SECONDS = 1.5 # How long to wait for a passive fill

#     # --- THIS PRE-TRADE EVALUATION LOGIC REMAINS THE SAME ---
#     def evaluate_tender_profit(self):
#         # ... (your existing code for this method is fine) ...
#         # NOTE: Double-check your use of usd_bid vs usd_ask here, as it can
#         # lead to inaccurate profit estimates. When buying USD-denominated
#         # assets, you must buy USD at the ask price.
#         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
#         ritc_depth = best_bid_ask_entire_depth(RITC)
#         bull_depth = best_bid_ask_entire_depth(BULL)
#         bear_depth = best_bid_ask_entire_depth(BEAR)
#         print(f"*** [TENDER EVAL] {self.action} {self.quantity} @ {self.price:.4f} USD ***")
#         self.opportunities = []
#         if self.action == 'SELL':
#             self._add_direct_buy_opportunities(ritc_depth['asks'], usd_bid, usd_ask)
#             self._add_converter_buy_opportunities(bull_depth['asks'], bear_depth['asks'], usd_bid)
#         else:
#             self._add_direct_sell_opportunities(ritc_depth['bids'], usd_bid, usd_ask)
#             self._add_converter_sell_opportunities(bull_depth['bids'], bear_depth['bids'], usd_bid)

#         self.opportunities.sort(key=lambda x: x['profit_per_share'], reverse=True)
        
#         executed, total_profit, = 0, 0
#         for opp in self.opportunities:
#             if executed >= self.quantity or opp['profit_per_share'] <= 0: break
#             take = min(self.quantity - executed, opp['quantity'])
#             total_profit += take * opp['profit_per_share']
#             executed += take 

#         return total_profit
    
#     # ... (Your _add..._opportunities methods remain here) ...
#     def _add_direct_buy_opportunities(self, ritc_asks, usd_bid, usd_ask):
#         for level in ritc_asks:
#             if level['quantity'] <= 0: continue
#             # CRITICAL: When buying RITC, you must buy USD at the ASK price.
#             cost_in_cad = level['price'] * usd_ask
#             revenue_in_cad = self.price * usd_bid
#             profit = revenue_in_cad - cost_in_cad - FEE_MKT
#             self.opportunities.append({'type': 'DIRECT_BUY', 'price': level['price'], 'quantity': level['quantity'], 'profit_per_share': profit})

#     def _add_converter_buy_opportunities(self, bull_asks, bear_asks, usd_bid):
#         for bull, bear in zip(bull_asks, bear_asks):
#             qty = min(bull['quantity'], bear['quantity'])
#             if qty <= 0: continue
#             total_cost = bull['price'] + bear['price'] + 2 * FEE_MKT + conversion_cost(1)
#             profit = self.price * usd_bid - total_cost
#             self.opportunities.append({'type': 'CONVERTER_BUY', 'price': total_cost, 'quantity': qty, 'profit_per_share': profit})

#     def _add_direct_sell_opportunities(self, ritc_bids, usd_bid, usd_ask):
#         for level in ritc_bids:
#             if level['quantity'] <= 0: continue
#             profit = (level['price'] - self.price) * usd_bid - FEE_MKT
#             self.opportunities.append({'type': 'DIRECT_SELL', 'price': level['price'], 'quantity': level['quantity'], 'profit_per_share': profit})

#     def _add_converter_sell_opportunities(self, bull_bids, bear_bids, usd_bid):
#         for bull, bear in zip(bull_bids, bear_bids):
#             qty = min(bull['quantity'], bear['quantity'])
#             if qty <= 0: continue
#             net_rev = bull['price'] + bear['price'] - 2 * FEE_MKT + conversion_cost(1) 
#             profit = net_rev - self.price * usd_bid
#             self.opportunities.append({'type': 'CONVERTER_SELL', 'price': net_rev, 'quantity': qty, 'profit_per_share': profit})


#     # ==============================================================================
#     # == NEW ADAPTIVE UNWINDING LOGIC (REPLACES ALL OLD EXECUTION METHODS)
#     # ==============================================================================

#     def unwind_tender(self):
#         """
#         Main controller for unwinding the tender position using an adaptive,
#         passive-aggressive limit order strategy.
#         """
#         print(f"\n*********************** [STARTING ADAPTIVE UNWIND] ***********************")
#         # Initial hedge for the entire tender value
#         fx_action = 'SELL' if self.action == 'SELL' else 'BUY'
#         fx_hedge(fx_action, self.price * self.quantity)
        
#         remaining_qty = self.quantity
#         while remaining_qty > 0:
#             # 1. SENSE: Get fresh market data
#             ritc_book = best_bid_ask_entire_depth(RITC)
#             bull_book = best_bid_ask_entire_depth(BULL)
#             bear_book = best_bid_ask_entire_depth(BEAR)

#             side = "BUY" if self.action == 'SELL' else "SELL"
#             book_side_key = 'asks' if side == 'BUY' else 'bids'

#             # 2. THINK: Decide on the best method and optimal chunk size
#             # Direct Route Analysis
#             direct_chunk = self._find_optimal_chunk(ritc_book[book_side_key])
#             _, direct_vwap = self._calculate_vwap_cost(ritc_book[book_side_key], direct_chunk)

#             # Converter Route Analysis
#             bull_chunk = self._find_optimal_chunk(bull_book[book_side_key])
#             bear_chunk = self._find_optimal_chunk(bear_book[book_side_key])
#             converter_chunk = min(bull_chunk, bear_chunk)
#             bull_cost, _ = self._calculate_vwap_cost(bull_book[book_side_key], converter_chunk)
#             bear_cost, _ = self._calculate_vwap_cost(bear_book[book_side_key], converter_chunk)
            
#             # Make the decision (normalized per share to be comparable)
#             cost_per_share_direct = direct_vwap if direct_chunk > 0 else float('inf')
#             cost_per_share_converter = ((bull_cost + bear_cost) / converter_chunk) if converter_chunk > 0 else float('inf')

#             # 3. ACT: Execute the best option
#             if cost_per_share_direct <= cost_per_share_converter:
#                 qty_to_execute = min(direct_chunk, remaining_qty, MAX_SIZE_EQUITY)
#                 if qty_to_execute <= 0:
#                     print("[WARNING] No viable liquidity for direct route. Waiting...")
#                     time.sleep(3)
#                     continue
#                 print(f"\n✓ Choosing DIRECT method for {qty_to_execute} shares.")
#                 self._execute_passive_aggressive_slice(RITC, side, qty_to_execute)
#             else:
#                 qty_to_execute = min(converter_chunk, remaining_qty, MAX_SIZE_EQUITY)
#                 if qty_to_execute <= 0:
#                     print("[WARNING] No viable liquidity for converter route. Waiting...")
#                     time.sleep(3)
#                     continue
#                 print(f"\n✓ Choosing CONVERTER method for {qty_to_execute} shares.")
#                 # Execute both legs of the converter
#                 self._execute_passive_aggressive_slice(BULL, side, qty_to_execute)
#                 self._execute_passive_aggressive_slice(BEAR, side, qty_to_execute)
#                 # Handle the actual conversion
#                 if side == 'BUY': self.converter.convert_bull_bear(qty_to_execute)
#                 else: self.converter.convert_ritc(qty_to_execute)

#             remaining_qty -= qty_to_execute
#             if remaining_qty > 0:
#                 print(f"--- {remaining_qty} shares remaining. Waiting for market to settle... ---")
#                 time.sleep(2)

#         print("\n--- Finalizing FX Exposure ---")
#         self.cleanup_fx_exposure()
#         print(f"*********************** [UNWIND COMPLETE] ***********************")
#         return True

#     def _execute_passive_aggressive_slice(self, security, side, quantity):
#         """Executes a single slice using the Patient Aggressor strategy."""
#         print(f"--- Executing {side} {quantity} {security} (Patient Aggressor) ---")
        
#         book_side_key = 'asks' if side == 'BUY' else 'bids'
#         book = best_bid_ask_entire_depth(security)
        
#         if not book[book_side_key]:
#             print(f"[WARNING] No liquidity on {book_side_key} for {security}. Aggressively placing market order.")
#             place_mkt(security, side, quantity)
#             return

#         target_price = book[book_side_key][0]['price']

#         print(f"Placing PASSIVE limit order at {target_price:.4f}...")
#         limit_order = place_limit(security, side, int(quantity), target_price)
#         if not limit_order:
#             print("[ERROR] Failed to place limit order. Switching to aggressive.")
#             place_mkt(security, side, int(quantity))
#             return

#         time.sleep(self.PATIENCE_WINDOW_SECONDS)
        
#         status = get_order_status(limit_order['order_id'])
        
#         if status['is_cancelled']:
#              print("[INFO] Order was cancelled, assuming filled or invalid.")
#              return

#         if status['quantity_filled'] >= quantity:
#             print(f"✓ Success! Full passive fill of {quantity} shares.")
#         else:
#             remaining_qty = int(quantity - status['quantity_filled'])
#             cancel_order(limit_order['order_id']) # Cancel the remainder
#             time.sleep(0.2)
            
#             if status['quantity_filled'] > 0:
#                 print(f"Partial fill of {status['quantity_filled']}. Going aggressive on rest.")
#             else: # No fill
#                 print(f"No fill. The market moved. Going fully aggressive.")
            
#             place_mkt(security, side, remaining_qty)
#             print(f"✓ Executed remaining {remaining_qty} shares aggressively.")

#     def _find_optimal_chunk(self, book_levels):
#         """Calculates the largest order size that meets the slippage tolerance."""
#         if not book_levels: return 0
        
#         best_price = book_levels[0]['price']
#         is_ask_side = 'ask' in book_levels[0].get('type', 'ask') # Infer side
        
#         cumulative_qty, cumulative_cost = 0, 0
        
#         for level in book_levels:
#             potential_vwap = (cumulative_cost + level['quantity'] * level['price']) / (cumulative_qty + level['quantity'])
            
#             if is_ask_side and potential_vwap > (best_price + self.SLIPPAGE_TOLERANCE):
#                 return int(cumulative_qty)
#             if not is_ask_side and potential_vwap < (best_price - self.SLIPPAGE_TOLERANCE):
#                 return int(cumulative_qty)
            
#             cumulative_qty += level['quantity']
#             cumulative_cost += level['quantity'] * level['price']

#         return int(cumulative_qty)

#     def _calculate_vwap_cost(self, book_levels, quantity):
#         """Calculates the true VWAP and cost for executing a given quantity."""
#         if not book_levels or quantity <= 0: return (float('inf'), float('inf'))

#         filled_qty, total_cost = 0, 0
#         for level in book_levels:
#             qty_to_take = min(level['quantity'], quantity - filled_qty)
#             total_cost += qty_to_take * level['price']
#             filled_qty += qty_to_take
#             if filled_qty >= quantity: break
        
#         if filled_qty < quantity: return (float('inf'), float('inf'))
#         return (total_cost, total_cost / filled_qty)

#     def cleanup_fx_exposure(self):
#         """Flattens the final USD position, effectively repatriating PnL."""
#         time.sleep(1)
#         positions = positions_map()
#         usd_position = positions.get(USD, 0)
        
#         if abs(usd_position) > 0.1:
#             action = "SELL" if usd_position > 0 else "BUY"
#             fx_hedge(action, abs(usd_position))
#             print(f"✓ Final FX Cleanup: {action} {abs(usd_position):.2f} USD.")


def check_tender(converter):
    """Fixed tender checking with correct converter cost logic"""
    tenders = get_tenders()
    if not tenders:
        return


    for tender in tenders[:2]:  # Limit to 2 tenders for safety
        # print(f"\n=== Evaluating Tender {tender['tender_id']} ===")
        
        # Quick position limit check
        if not within_limits():
            print("[WARNING] Position limits - skipping tenders")
            break
        
        T = EvaluateTenders(tender, converter)
        T.cleanup_fx_exposure()
        eval_result = T.evaluate_tender_profit()

        # print('estimated profit:', eval_result)
        
        if eval_result > 1000:
            print(f"✓ ACCEPTING tender {tender['tender_id']}: profit {eval_result} CAD")
            success = accept_tender(tender)
            if success:
                T.unwind_tender()
                # ritc_depth = best_bid_ask_entire_depth(RITC)
                # bull_depth = best_bid_ask_entire_depth(BULL)
                # bear_depth = best_bid_ask_entire_depth(BEAR)

                # print(ritc_depth)
                # print(bull_depth)
                # print(bear_depth)

                print(f"✓ Successfully processed tender {tender['tender_id']}")

            else:
                print(f"⚠ Partially processed tender {tender['tender_id']}")
                
            # Pause between tenders for safety
            sleep(2)
        else:
            print(f"✗ Rejecting tender {tender['tender_id']}: insufficient profit")


# DEBUGGING: Test the fixed converter cost calculation
def test_fixed_converter_cost():
    """Test the corrected converter cost calculation"""
    print("\n=== TESTING FIXED CONVERTER COST ===")
    
    # Mock tender for testing
    mock_tender = {
        'tender_id': 'TEST',
        'action': 'BUY', 
        'price': 24.0,
        'quantity': 5000
    }
    
    T = EvaluateTenders(mock_tender, None)
    
    test_quantities = [1000, 2500, 5000, 7500, 10000, 15000]
    
    for qty in test_quantities:
        cost = T.calculate_converter_cost(qty)
        expected_conversion_fee = 1500 * (qty / 10000) if qty <= 10000 else float('inf')
        
#         print(f"Quantity: {qty:5d} | Cost: {cost:8.2f} | Expected conv fee: {expected_conversion_fee:.2f}")

# if __name__ == "__main__":
#     test_fixed_converter_cost()


# COMPLETELY REWRITTEN TENDER EVALUATION - Proper Market Depth Analysis
# Core principle: Analyze full order book depth, create opportunity list, select optimal execution path
