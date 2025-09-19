
from final_utils import *
import time
from rich import print
import numpy as np

MIN_CHUNK = 5000

class EvaluateTendersNew():
    def __init__(self, tender, converter):
        self.tender = tender
        self.action = tender['action']  # 'SELL' or 'BUY'
        self.price = tender['price']
        self.quantity = tender['quantity']
        self.converter = converter
        # --- TUNABLE PARAMETERS FOR THE NEW STRATEGY ---
        self.SLIPPAGE_TOLERANCE = 0.02  # Max acceptable slippage in dollars per share
        self.PATIENCE_WINDOW_SECONDS = 5 # How long to wait for a passive fill
        self.REQUIRED_PROFIT_MARGIN = 0.05 # Minimum profit vs FVE to consider market "favorable"
        self.MIN_DELAY_SECONDS = 1.0       # Delay when market is very favorable
        self.MAX_DELAY_SECONDS = 8.0       # Delay when market is unfavorable


        self.total_orders = 0 
        self.num_limit_order = 0

   

    # --- THIS PRE-TRADE EVALUATION LOGIC REMAINS THE SAME ---
    def evaluate_tender_profit(self):
        # ... (your existing code for this method is fine) ...
        # NOTE: Double-check your use of usd_bid vs usd_ask here, as it can
        # lead to inaccurate profit estimates. When buying USD-denominated
        # assets, you must buy USD at the ask price.
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
            if executed >= self.quantity: break

            take = min(self.quantity - executed, opp['quantity'])
            total_profit += take * opp['profit_per_share']
            executed += take 

        return total_profit
    
    # ... (Your _add..._opportunities methods remain here) ...
    def _add_direct_buy_opportunities(self, ritc_asks, usd_bid, usd_ask):
        for level in ritc_asks:
            if level['quantity'] <= 0: continue
            # CRITICAL: When buying RITC, you must buy USD at the ASK price.
            cost_in_cad = level['price'] * usd_ask
            revenue_in_cad = self.price * usd_bid
            profit = revenue_in_cad - cost_in_cad - FEE_MKT
            self.opportunities.append({'type': 'DIRECT_BUY', 'price': level['price'], 'quantity': level['quantity'], 'profit_per_share': profit})

    def _add_converter_buy_opportunities(self, bull_asks, bear_asks, usd_bid):
        for bull, bear in zip(bull_asks, bear_asks):
            qty = min(bull['quantity'], bear['quantity'])
            if qty <= 0: continue
            total_cost = bull['price'] + bear['price'] + 2 * FEE_MKT + conversion_cost(1)
            profit = self.price * usd_bid - total_cost
            self.opportunities.append({'type': 'CONVERTER_BUY', 'price': total_cost, 'quantity': qty, 'profit_per_share': profit})

    def _add_direct_sell_opportunities(self, ritc_bids, usd_bid, usd_ask):
        for level in ritc_bids:
            if level['quantity'] <= 0: continue
            profit = (level['price'] - self.price) * usd_bid - FEE_MKT
            self.opportunities.append({'type': 'DIRECT_SELL', 'price': level['price'], 'quantity': level['quantity'], 'profit_per_share': profit})

    def _add_converter_sell_opportunities(self, bull_bids, bear_bids, usd_bid):
        for bull, bear in zip(bull_bids, bear_bids):
            qty = min(bull['quantity'], bear['quantity'])
            if qty <= 0: continue
            net_rev = bull['price'] + bear['price'] - 2 * FEE_MKT + conversion_cost(1) 
            profit = net_rev - self.price * usd_bid
            self.opportunities.append({'type': 'CONVERTER_SELL', 'price': net_rev, 'quantity': qty, 'profit_per_share': profit})


    # ==============================================================================
    # == NEW ADAPTIVE UNWINDING LOGIC (REPLACES ALL OLD EXECUTION METHODS)
    # # ==============================================================================
    # def calculate_direct_cost(self):
    #     """Calculate cost of direct ETF trading"""
    #     usd_bid, usd_ask, _, _ = best_bid_ask(USD)
    #     if self.action == 'SELL':
    #         # We're short RITC, need to buy RITC directly
    #         ritc_ask_price, qty = get_top_level_price_and_qty(RITC, "BUY")
    #         etf_cost_usd = ritc_ask_price * qty + qty * FEE_MKT
    #         fx_cost_cad = etf_cost_usd * usd_ask  # Need to buy USD at ask
    #         # print("direct_p", ritc_ask_price, end = ' ')

    #         return fx_cost_cad / qty
    #     else:
    #         ritc_bid_price, qty = get_top_level_price_and_qty(RITC, "SELL")
    #         etf_revenue_usd = ritc_bid_price * qty - qty * FEE_MKT
    #         fx_revenue_cad = etf_revenue_usd * usd_bid  # Sell USD at bid
    #         # print("direct_p", ritc_bid_price, end = ' ')

            # return -fx_revenue_cad / qty  # Negative because it's revenue

    # def calculate_converter_cost(self):
    #     """Calculate cost of converter method with proportional pricing"""
    #     usd_bid, usd_ask, _, _ = best_bid_ask(USD)
    #     if self.action == 'SELL':
    #         # We're short RITC: Buy stocks → Convert to RITC
    #         bull_ask_price, qty_bull = get_top_level_price_and_qty(BULL, "BUY")
    #         bear_ask_price, qty_bear = get_top_level_price_and_qty(BEAR, "BUY")
    #         qty = min(qty_bull, qty_bear)
    #         stock_cost_cad = (bull_ask_price + bear_ask_price) * qty + qty * 2 * FEE_MKT
    #         conversion_fee_cad = conversion_cost(qty)
    #         # print("c_p", bull_ask_price, bear_ask_price)

    #         return (stock_cost_cad + conversion_fee_cad)/ qty
    #     else:
    #         # We're long RITC: Convert RITC → Sell stocks
    #         bull_bid_price, qty_bull = get_top_level_price_and_qty(BULL, "SELL")
    #         bear_bid_price, qty_bear = get_top_level_price_and_qty(BEAR, "SELL")
    #         qty = min(qty_bull, qty_bear)
    #         # print("c_p", bull_bid_price, bear_bid_price)

    #         stock_revenue_cad = (bull_bid_price + bear_bid_price) * qty - qty * 2 * FEE_MKT
    #         conversion_fee_cad = conversion_cost(qty)
            # return (conversion_fee_cad - stock_revenue_cad)/qty# Net cost


    def unwind_tender(self):
        """
        Main controller for unwinding the tender position using an adaptive,
        passive-aggressive limit order strategy with correct cost analysis and hedging.
        """
        print(f"\n*********************** [STARTING ADAPTIVE UNWIND] ***********************")
        
        remaining_qty = self.quantity
    
        side = "BUY" if self.action == 'SELL' else "SELL"
        

        while remaining_qty > 0:
            
            filled_qty, vwap = self._execute_direct(side, remaining_qty)
            remaining_qty -= filled_qty

            filled_qty, vwap = self._execute_converted(side, remaining_qty)
            remaining_qty -= filled_qty
            
            if remaining_qty > 0 and filled_qty > 0:
                delay = 0 # Replace with your intelligent delay if desired
                print(f"--- {remaining_qty} shares remaining. Waiting {delay:.1f}s... ---")
                time.sleep(delay)

        print("\n--- Finalizing FX Exposure ---")
        self.cleanup_fx_exposure()

        print(f"Perc of limit orders {self.num_limit_order} / {self.total_orders}")
        print(f"*********************** [UNWIND COMPLETE] ***********************")
        return True


    def _execute_direct(self, side, remaining_qty):
        """
        Executes a single slice using the Patient Aggressor strategy.
        MODIFIED: Now returns (quantity_filled, vwap) for hedging purposes.
        """
        
        self.total_orders += 1
        # Initial state
        total_filled_qty = 0
        total_filled_value = 0

        # size of the top chunk.
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        book, qty = get_top_level_price_and_qty(RITC, side)

        # 1. Passive Attempt
        _d = 0.1  # Amount to adjust price by (tune as needed)

        DELTA = _d if side == 'SELL' else -_d
        def check_loss(cost, buffer = 0):
            if self.action == "SELL":
                if cost >  self.price - buffer : # buying at loss
                    return 1
            else:
                if abs(cost) < self.price + buffer:  # selling at loss.
                    return 1 
            return 0 
        
        st_time = time.time()
        
        buffer = 0
        output = check_loss(book, buffer = buffer)
        while output and time.time() - st_time < 5:
            book, qty = get_top_level_price_and_qty(RITC, side)
            output = check_loss(book, buffer = buffer)
        
        print('delayed for', time.time() - st_time)  

        qty = max(qty, MIN_CHUNK)
        qty = min(qty, remaining_qty, MAX_SIZE_EQUITY)

        
        target_price = book + DELTA
        print(f"[LMT] @ {target_price:.2f}...", end = ' ')

        limit_order = place_limit(RITC, side, qty, target_price)

        if limit_order:
            time.sleep(self.PATIENCE_WINDOW_SECONDS)
            status = get_order_status(limit_order['order_id']).json()
            
            if status and status.get('quantity_filled', 0) > 0:
                filled = status['quantity_filled']
                vwap = status['vwap']
                total_filled_qty += filled
                total_filled_value += filled * vwap
                qty -= filled
                print(f"FILL: {filled} shares.")
            
            # Clean up the outstanding passive order regardless of fill
            cancel_order(limit_order['order_id'])


        # 2. Aggressive Completion
        self.num_limit_order += 1 
        if qty > 0:
            self.num_limit_order -= 1 

            market_order = place_mkt(RITC, side, qty)
            if market_order and market_order.get('quantity_filled', 0) > 0:
                filled = market_order['quantity_filled']
                vwap = market_order['vwap']
                total_filled_qty += filled
                total_filled_value += filled * vwap

                print(f"[MKR] FILL: {filled} shares @ {vwap}")
        
        final_vwap = total_filled_value / total_filled_qty if total_filled_qty > 0 else 0

        print(f"[FINAL] {total_filled_qty} @ price {final_vwap:.4f}")

        return total_filled_qty, final_vwap
    

    
    def _execute_converted(self, side, remaining_qty):
        """
        
        """
        
        self.total_orders += 1

        # size of the top chunk.
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        book_bull, qty_bl = get_top_level_price_and_qty(BULL, side)
        book_bear, qty_br = get_top_level_price_and_qty(BEAR, side)

        # 1. Passive Attempt
        _d = 0.1  # Amount to adjust price by (tune as needed)
        DELTA = _d if side == 'SELL' else -_d


        def check_loss(book_bull, book_bear, buffer = 0):

            cost = book_bull + book_bear + conversion_cost(1)
            if self.action == "SELL":
                if cost >  self.price * usd_ask - buffer : # buying at loss
                    return 1
            else:
                if abs(cost) < self.price * usd_ask + buffer:  # selling at loss.
                    return 1 
            return 0 
        
        
        st_time = time.time()

        buffer = 0
        
        output = check_loss(book_bull, book_bear, buffer=buffer)
        while output and time.time() - st_time < 5:
            book_bull, qty_bl = get_top_level_price_and_qty(BULL, side)
            book_bear, qty_br = get_top_level_price_and_qty(BEAR, side)
            output = check_loss(book_bull, book_bear, buffer = buffer)

        print('delayed for', time.time() - st_time)     

        qty = max(min(qty_bl, qty_br), MIN_CHUNK)
        order_qty = min(qty, remaining_qty, MAX_SIZE_EQUITY)   


        bull_target = book_bull + DELTA        
        limit_order_bull = place_limit(BULL, side, order_qty,  bull_target)
        print(f"[LMT] @ {bull_target:.2f}...", end = ' ')

        bear_target = book_bear + DELTA        
        limit_order_bear = place_limit(BEAR, side, order_qty, bear_target)
        print(f"[LMT] @ {bear_target:.2f}...", end = ' ')


        time.sleep(self.PATIENCE_WINDOW_SECONDS)

        def sq_limit_order(ticker, limit_order, _qty):
            total_filled_value, total_filled_qty = 0, 0

            if limit_order and "order_id" in limit_order:
                status = get_order_status(limit_order['order_id']).json()
                
                if status and status.get('quantity_filled', 0) > 0:
                    filled = status['quantity_filled']
                    vwap = status['vwap']
                    total_filled_value += filled * vwap
                    total_filled_qty += filled

                    _qty -= filled
                    print(f"FILL: {filled} shares.")
                
                # Clean up the outstanding passive order regardless of fill
                cancel_order(limit_order['order_id'])

            # 2. Aggressive Completion
            self.num_limit_order += 1 
            if _qty > 0:
                self.num_limit_order -= 1 

                market_order = place_mkt(ticker, side, _qty)
                if market_order and market_order.get('quantity_filled', 0) > 0:
                    filled = market_order['quantity_filled']
                    vwap = market_order['vwap']
                    total_filled_qty += filled
                    total_filled_value += filled * vwap
                    print(f"[MKR] FILL: {filled} shares @ {vwap}")
        
            final_vwap = total_filled_value / total_filled_qty if total_filled_qty > 0 else 0
            print(f"[FINAL] {total_filled_qty} @ price {final_vwap:.4f}")
            return total_filled_qty, final_vwap

        bear_qty, _ = sq_limit_order(BEAR, limit_order_bear, order_qty)
        bull_qty, _ = sq_limit_order(BULL, limit_order_bull, order_qty)

        if bear_qty != bull_qty: 
            print("[red] [WARNING] different bull / bear filled qty!")
        
        hedge_action = "BUY" if side == "SELL" else "SELL" # If we bought RITC (USD), we must buy USD to pay
        usd_amount_transacted = self.price * order_qty # selling with original price in mind 
        fx_hedge(hedge_action, usd_amount_transacted)

        if order_qty > 0:
            if side == 'BUY': 
                self.converter.convert_bull_bear(order_qty)
            else: 
                self.converter.convert_ritc(order_qty)

            fx_hedge("BUY", conversion_cost(order_qty))
                    
        return order_qty, _
    
    def cleanup_fx_exposure(self):
        """Flattens the final USD position, effectively repatriating PnL."""
        time.sleep(1)
        positions = positions_map()
        usd_position = positions.get(USD, 0)
        
        if abs(usd_position) > 0.1:
            action = "SELL" if usd_position > 0 else "BUY"
            fx_hedge(action, abs(usd_position))
            print(f"✓ Final FX Cleanup: {action} {abs(usd_position):.2f} USD.")


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
        
        T = EvaluateTendersNew(tender, converter)
        eval_result = T.evaluate_tender_profit()

        # print('estimated profit:', eval_result)
        
        if eval_result > 0:
            print(f"[green] tender {tender['tender_id']}: profit {eval_result} CAD")
            success = accept_tender(tender)
            if success:
                T.unwind_tender()
                # ritc_depth = best_bid_ask_entire_depth(RITC)
                # bull_depth = best_bid_ask_entire_depth(BULL)
                # bear_depth = best_bid_ask_entire_depth(BEAR)
                print(f"[green] DONE")

            else:
                print(f"⚠ Partially processed tender {tender['tender_id']}")
                
        else:
            print(f"[orange] Rejecting tender {tender['tender_id']}: insufficient profit {eval_result}")


# DEBUGGING: Test the fixed converter cost calculation
# def test_fixed_converter_cost():
#     """Test the corrected converter cost calculation"""
#     print("\n=== TESTING FIXED CONVERTER COST ===")
    
#     # Mock tender for testing
#     mock_tender = {
#         'tender_id': 'TEST',
#         'action': 'BUY', 
#         'price': 24.0,
#         'quantity': 5000
#     }
    
#     T = EvaluateTenders(mock_tender, None)
    
#     test_quantities = [1000, 2500, 5000, 7500, 10000, 15000]
    
#     for qty in test_quantities:
#         cost = T.calculate_converter_cost(qty)
#         expected_conversion_fee = 1500 * (qty / 10000) if qty <= 10000 else float('inf')
