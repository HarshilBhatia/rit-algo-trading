
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
        
        return avg_profit


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
            qty = min(bull['quantity'], bear['quantity'], CONVERTER_BATCH)
            if qty <= 0: continue
            total_cost = bull['price'] + bear['price'] + 2 * FEE_MKT + 1500 / CONVERTER_BATCH
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
            net_rev = bull['price'] + bear['price'] - 2 * FEE_MKT - 1500 / CONVERTER_BATCH
            profit = net_rev - self.price * usd_bid
            self.opportunities.append({
                'type': 'CONVERTER_SELL',
                'price': net_rev, 'quantity': qty, 'profit_per_share': profit
            })
        
    def accept_and_unwind_tender(self):
        """Accept tender and intelligently unwind position"""
        
        # Accept the tender first
        if not accept_tender(self.tender):
            print(f"[ERROR] Failed to accept tender {self.tender['tender_id']}")
            return False
        
        print(f"✓ Accepted tender {self.tender['tender_id']}")
        
        # Now we have a position to unwind
        remaining_qty = self.quantity
        total_unwinding_cost = 0
        
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
                price, qty = self.execute_direct_unwind()
                actual_cost = qty*price 
            else:
                print("✓ Choosing CONVERTER method")
                price, qty = self.execute_converter_unwind()
                actual_cost = price*qty
                
            
            remaining_qty -= qty 
            total_unwinding_cost += actual_cost # not sure if this is correct or not.
            print(f"✓ Successfully unwound {qty} shares")
            
            
            # Brief pause between chunks
            if remaining_qty > 0:
                sleep(0.5)
        
        # Final cleanup of any residual FX exposure
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

    def execute_direct_unwind(self):
        """Execute direct ETF trading"""
        try:
            if self.action == 'SELL':
                # Buy RITC to cover short
                _, qty = get_top_level_price_and_qty(RITC, "BUY")
                result = place_mkt(RITC, "BUY", qty)
                if result and result.get('vwap', 0) > 0:
                    print(f"✓ Bought {qty} RITC at {result['vwap']:.4f} USD")
                    return result['vwap'], qty
            else:
                # Sell RITC
                _, qty = get_top_level_price_and_qty(RITC, "SELL")
                result = place_mkt(RITC, "SELL", qty)
                if result and result.get('vwap', 0) > 0:
                    print(f"✓ Sold {qty} RITC at {result['vwap']:.4f} USD")
                    return result['vwap'], qty
            return 0, 0
        except Exception as e:
            print(f"[ERROR] Direct unwind failed: {e}")
            return 0, 0

    def execute_converter_unwind(self):
        """Execute converter-based unwinding - can handle any amount up to 10k"""
        try:
            if self.action == 'SELL':
                # We're short RITC: Buy stocks → Convert to RITC
                _, qty_bull = get_top_level_price_and_qty(BULL, "BUY")
                _, qty_bear = get_top_level_price_and_qty(BEAR, "BUY")
                qty = min(qty_bull, qty_bear)
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
                print(f"✓ Converted {qty} stocks to RITC (cost: {self._conversion_fee(qty):.2f} CAD)")
                return bull_result['vwap'] + bear_result['vwap'] - self._conversion_fee(qty), qty
            else:
                # We're long RITC: Convert RITC → Sell stocks
                _, qty_bull = get_top_level_price_and_qty(BULL, "SELL")
                _, qty_bear = get_top_level_price_and_qty(BEAR, "SELL")
                qty = min(qty_bull, qty_bear)
                conversion_result = self.converter.convert_ritc(qty)
                if not conversion_result or not conversion_result.ok:
                    print(f"[ERROR] ETF redemption failed")
                    return 0, 0
                print(f"✓ Converted {qty} RITC to stocks (cost: {self._conversion_fee(qty):.2f} CAD)")
                sleep(1)  # Allow conversion to settle
                bull_result = place_mkt(BULL, "SELL", qty)
                bear_result = place_mkt(BEAR, "SELL", qty)
                if not bull_result or not bear_result:
                    print("[WARNING] Failed to sell some stocks")
                print(f"✓ Sold {qty} BULL and BEAR")
                return bull_result['vwap'] + bear_result['vwap'] - self._conversion_fee(qty), qty
        except Exception as e:
            print(f"[ERROR] Converter unwind failed: {e}")
            return 0, 0
        
    # def calculate_direct_cost(self):
    #     """Calculate cost of direct ETF trading"""
    #     usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        
    #     if self.action == 'SELL':
    #         # We're short RITC, need to buy RITC directly
    #         ritc_ask_price, qty = get_top_level_price_and_qty(RITC, "BUY")

    #         etf_cost_usd = ritc_ask_price * qty + qty * FEE_MKT
    #         fx_cost_cad = etf_cost_usd * usd_ask  # Need to buy USD at ask

    #         return fx_cost_cad
    #     else: 
    #         ritc_bid_price, qty = get_top_level_price_and_qty(RITC, "SELL")
    #         # This actually gives us USD, so it's negative cost (revenue)
    #         etf_revenue_usd = ritc_bid_price * qty - qty * FEE_MKT
    #         fx_revenue_cad = etf_revenue_usd * usd_bid  # Sell USD at bid
    #         return -fx_revenue_cad  # Negative because it's revenue

    # def calculate_converter_cost(self):
    #     """FIXED: Calculate cost of converter method with proportional pricing"""
        
    #     # FIXED: Only reject if quantity exceeds maximum batch size
        
    #     usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        
    #     if self.action == 'SELL':
    #         # We're short RITC: Buy stocks → Convert to RITC
    #         bull_ask_price, qty = get_top_level_price_and_qty(BULL, "BUY")
    #         bear_ask_price, qty = get_top_level_price_and_qty(BEAR, "BUY")
            
    #         stock_cost_cad = (bull_ask_price + bear_ask_price) * qty + qty * 2 * FEE_MKT
            
    #         conversion_fee_cad = 1500 * (qty / CONVERTER_BATCH)
            
    #         return stock_cost_cad + conversion_fee_cad
            
    #     else:  # BUY tender
    #         # We're long RITC: Convert RITC → Sell stocks
    #         bull_bid_price, bull_max = get_top_level_price_and_qty(BULL, "SELL") 
    #         bear_bid_price, bear_max = get_top_level_price_and_qty(BEAR, "SELL")
    #         # This gives us revenue from stocks, costs conversion fee
    #         stock_revenue_cad = (bull_bid_price + bear_bid_price) * qty - qty * 2 * FEE_MKT
            
    #         conversion_fee_cad = 1500 * (qty / CONVERTER_BATCH)
            
    #         return conversion_fee_cad - stock_revenue_cad  # Net cost

    # def execute_direct_unwind(self):
    #     """Execute direct ETF trading"""
    #     try:
    #         if self.action == 'SELL':
    #             # Buy RITC to cover short
    #             _, qty = get_top_level_price_and_qty(RITC, "BUY")
    #             result = place_mkt(RITC, "BUY", qty)

    #             if result and result.get('vwap', 0) > 0:
    #                 print(f"✓ Bought {qty} RITC at {result['vwap']:.4f} USD")
    #                 return result['vwap'], qty
                    
    #         else:  # BUY tender
    #             # Sell RITC
    #             _, qty = get_top_level_price_and_qty(RITC, "SELL")
    #             result = place_mkt(RITC, "SELL", qty)
    #             if result and result.get('vwap', 0) > 0:
    #                 print(f"✓ Sold {qty} RITC at {result['vwap']:.4f} USD")
    #                 return result['vwap'], qty
                    
    #         return 0,0
            
    #     except Exception as e:
    #         print(f"[ERROR] Direct unwind failed: {e}")
    #         return 0,0

    # def execute_converter_unwind(self):
    #     """Execute converter-based unwinding - can handle any amount up to 10k"""
        
    #     try:
    #         if self.action == 'SELL':
    #             # We're short RITC: Buy stocks → Convert to RITC
                
    #             # Step 1: Buy stocks
    #             _, qty_bull = get_top_level_price_and_qty(BULL, "BUY")
    #             _, qty_bear = get_top_level_price_and_qty(BEAR, "BUY")

    #             qty = min(qty_bull, qty_bear)
    #             bull_result = place_mkt(BULL, "BUY", qty)
    #             bear_result = place_mkt(BEAR, "BUY", qty)
                
    #             if not bull_result or not bear_result:
    #                 print("[ERROR] Failed to buy stocks")
    #                 return 0,0
                
    #             print(f"✓ Bought {qty} BULL and BEAR")
    #             sleep(1)  # Allow orders to settle
                
    #             # Step 2: Convert to RITC
    #             conversion_result = self.converter.convert_bull_bear(qty)
    #             if not conversion_result or not conversion_result.ok:
    #                 print(f"[ERROR] ETF creation failed")
    #                 # Emergency: sell the stocks we just bought
    #                 place_mkt(BULL, "SELL", qty)
    #                 place_mkt(BEAR, "SELL", qty)
    #                 return 0,0
                
    #             print(f"✓ Converted {qty} stocks to RITC (cost: {1500 * qty / CONVERTER_BATCH:.2f} CAD)")
    #             return bull_result['vwap'] + bear_result['vwap'] - qty * 1500/CONVERTER_BATCH, qty
                
    #         else:  # BUY tender
    #             # We're long RITC: Convert RITC → Sell stocks
                
    #             # Step 1: Convert RITC to stocks

    #             _, qty_bull = get_top_level_price_and_qty(BULL, "SELL")
    #             _, qty_bear = get_top_level_price_and_qty(BEAR, "SELL")

    #             qty = min(qty_bull, qty_bear)

    #             conversion_result = self.converter.convert_ritc(qty)
    #             if not conversion_result or not conversion_result.ok:
    #                 print(f"[ERROR] ETF redemption failed")
    #                 return False
                    
    #             print(f"✓ Converted {qty} RITC to stocks (cost: {1500 * qty / CONVERTER_BATCH:.2f} CAD)")
    #             sleep(1)  # Allow conversion to settle
                
    #             # Step 2: Sell stocks
    #             bull_result = place_mkt(BULL, "SELL", qty)
    #             bear_result = place_mkt(BEAR, "SELL", qty)
                
    #             if not bull_result or not bear_result:
    #                 print("[WARNING] Failed to sell some stocks")
    #                 # Don't return False - we still made progress
                    
    #             print(f"✓ Sold {qty} BULL and BEAR")
    #             return bull_result['vwap'] + bear_result['vwap'] - qty * 1500/CONVERTER_BATCH, qty 
                
    #     except Exception as e:
    #         print(f"[ERROR] Converter unwind failed: {e}")
    #         return 0,0

    def cleanup_fx_exposure(self):
        """Clean up any residual USD exposure"""
        try:
            sleep(1)  # Allow all trades to settle
            
            # Check actual USD position
            positions = positions_map()
            usd_position = positions.get(USD, 0)
            
            if abs(usd_position) > 0.1:  # Only if meaningful exposure
                action = "SELL" if usd_position > 0 else "BUY"
                result = place_mkt(USD, action, abs(usd_position))
                
                if result:
                    print(f"✓ FX cleanup: {action} {abs(usd_position):.2f} USD")
                else:
                    print(f"[WARNING] Failed to cleanup {usd_position:.2f} USD")
                    
        except Exception as e:
            print(f"[ERROR] FX cleanup failed: {e}")


def check_tender(converter):
    """Fixed tender checking with correct converter cost logic"""
    tenders = get_tenders()
    if not tenders:
        return

    for tender in tenders[:2]:  # Limit to 2 tenders for safety
        print(f"\n=== Evaluating Tender {tender['tender_id']} ===")
        
        # Quick position limit check
        if not within_limits():
            print("[WARNING] Position limits - skipping tenders")
            break
        
        T = EvaluateTenders(tender, converter)
        eval_result = T.evaluate_tender_profit()
        
        if eval_result['profitable']:
            print(f"✓ ACCEPTING tender {tender['tender_id']}: profit {eval_result['profit']:.2f} CAD")
            
            success = T.accept_and_unwind_tender()
            if success:
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
