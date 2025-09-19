
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
        self.opportunities = []  # List of all trading opportunities
        
    def evaluate_tender_profit(self):
        """COMPLETELY REWRITTEN: Proper market depth analysis with opportunity ranking"""
        
        # Get full market depth for all instruments
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        ritc_depth = best_bid_ask_entire_depth(RITC)
        bull_depth = best_bid_ask_entire_depth(BULL)
        bear_depth = best_bid_ask_entire_depth(BEAR)
        
        print(f"*********************** [TENDER EVAL - MARKET DEPTH] ***********************")
        print(f"Tender: {self.action} {self.quantity} @ {self.price:.4f} USD")
        
        # Build opportunity list from market depth
        self.opportunities = []
        
        if self.action == 'SELL':
            # SELL tender: We get tender_price USD, need to buy back RITC
            self._add_direct_buy_opportunities(ritc_depth['asks'], usd_bid, usd_ask)
            self._add_converter_buy_opportunities(bull_depth['asks'], bear_depth['asks'], usd_bid)
            
        else:  # BUY tender
            # BUY tender: We pay tender_price USD, need to sell RITC  
            self._add_direct_sell_opportunities(ritc_depth['bids'], usd_bid, usd_ask)
            self._add_converter_sell_opportunities(bull_depth['bids'], bear_depth['bids'], usd_bid)
        
        # Sort opportunities by profit per share (descending)
        self.opportunities.sort(key=lambda x: x['profit_per_share'], reverse=True)
        
        # Calculate optimal execution by taking best opportunities
        return self._calculate_optimal_execution()
    
    def _add_direct_buy_opportunities(self, ritc_asks, usd_bid, usd_ask):
        """Add direct RITC purchase opportunities for SELL tender"""
        for level in ritc_asks:
            if level['quantity'] <= 0:
                continue
                
            # Profit = (tender_price - market_price) * fx_rate - fees
            price_diff_usd = self.price - level['price']
            profit_per_share_cad = price_diff_usd * usd_bid - FEE_MKT
            
            self.opportunities.append({
                'type': 'DIRECT_BUY',
                'method': 'Direct RITC purchase',
                'price': level['price'],
                'quantity': level['quantity'],
                'profit_per_share': profit_per_share_cad,
                'total_profit': profit_per_share_cad * level['quantity'],
                'execution_cost': level['price'] * usd_ask + FEE_MKT  # Cost in CAD per share
            })
    
    def _add_converter_buy_opportunities(self, bull_asks, bear_asks, usd_bid):
        """Add converter-based opportunities for SELL tender"""
        # Match bull and bear levels to create converter opportunities
        for i, (bull_level, bear_level) in enumerate(zip(bull_asks, bear_asks)):
            if i >= min(len(bull_asks), len(bear_asks)):
                break
                
            # Available quantity is limited by smaller of bull/bear availability
            available_qty = min(bull_level['quantity'], bear_level['quantity'], CONVERTER_BATCH)
            if available_qty <= 0:
                continue
            
            # Calculate total cost to create RITC via converter
            stock_cost_per_share = bull_level['price'] + bear_level['price'] + 2 * FEE_MKT
            conversion_cost_per_share = 1500 / CONVERTER_BATCH  # $0.15 per share
            total_cost_per_share_cad = stock_cost_per_share + conversion_cost_per_share
            
            # Profit = tender_proceeds - total_cost
            tender_proceeds_per_share_cad = self.price * usd_bid
            profit_per_share_cad = tender_proceeds_per_share_cad - total_cost_per_share_cad
            
            self.opportunities.append({
                'type': 'CONVERTER_BUY', 
                'method': f'Buy BULL@{bull_level["price"]:.4f} + BEAR@{bear_level["price"]:.4f}, convert',
                'price': total_cost_per_share_cad,
                'quantity': available_qty,
                'profit_per_share': profit_per_share_cad,
                'total_profit': profit_per_share_cad * available_qty,
                'execution_cost': total_cost_per_share_cad,
                'bull_price': bull_level['price'],
                'bear_price': bear_level['price']
            })
    
    def _add_direct_sell_opportunities(self, ritc_bids, usd_bid, usd_ask):
        """Add direct RITC sale opportunities for BUY tender"""
        for level in ritc_bids:
            if level['quantity'] <= 0:
                continue
                
            # Profit = (market_price - tender_price) * fx_rate - fees
            price_diff_usd = level['price'] - self.price
            profit_per_share_cad = price_diff_usd * usd_bid - FEE_MKT
            
            self.opportunities.append({
                'type': 'DIRECT_SELL',
                'method': 'Direct RITC sale',
                'price': level['price'],
                'quantity': level['quantity'], 
                'profit_per_share': profit_per_share_cad,
                'total_profit': profit_per_share_cad * level['quantity'],
                'execution_revenue': level['price'] * usd_bid - FEE_MKT  # Revenue in CAD per share
            })
    
    def _add_converter_sell_opportunities(self, bull_bids, bear_bids, usd_bid):
        """Add converter-based opportunities for BUY tender"""
        # Match bull and bear levels to create converter opportunities
        for i, (bull_level, bear_level) in enumerate(zip(bull_bids, bear_bids)):
            if i >= min(len(bull_bids), len(bear_bids)):
                break
                
            # Available quantity limited by smaller of bull/bear bids
            available_qty = min(bull_level['quantity'], bear_level['quantity'], CONVERTER_BATCH)
            if available_qty <= 0:
                continue
            
            # Calculate revenue from selling stocks after conversion
            stock_revenue_per_share = bull_level['price'] + bear_level['price'] - 2 * FEE_MKT
            conversion_cost_per_share = 1500 / CONVERTER_BATCH  # $0.15 per share
            net_revenue_per_share_cad = stock_revenue_per_share - conversion_cost_per_share
            
            # Profit = net_revenue - tender_cost
            tender_cost_per_share_cad = self.price * usd_ask
            profit_per_share_cad = net_revenue_per_share_cad - tender_cost_per_share_cad
            
            self.opportunities.append({
                'type': 'CONVERTER_SELL',
                'method': f'Convert, sell BULL@{bull_level["price"]:.4f} + BEAR@{bear_level["price"]:.4f}',
                'price': net_revenue_per_share_cad,
                'quantity': available_qty,
                'profit_per_share': profit_per_share_cad,
                'total_profit': profit_per_share_cad * available_qty,
                'execution_revenue': net_revenue_per_share_cad,
                'bull_price': bull_level['price'],
                'bear_price': bear_level['price']
            })
    
    def _calculate_optimal_execution(self):
        """Calculate optimal execution by selecting best opportunities"""
        
        print(f"\n=== OPPORTUNITY ANALYSIS ===")
        print(f"Total opportunities found: {len(self.opportunities)}")
        
        # Show top 5 opportunities
        for i, opp in enumerate(self.opportunities[:5]):
            print(f"{i+1}. {opp['method']}")
            print(f"   Profit: {opp['profit_per_share']:.4f} CAD/share, Qty: {opp['quantity']}")
        
        # Execute greedy selection of best opportunities
        remaining_qty = self.quantity
        total_profit = 0
        selected_opportunities = []
        
        for opp in self.opportunities:
            if remaining_qty <= 0:
                break
                
            if opp['profit_per_share'] <= 0:
                break  # Stop at unprofitable opportunities
                
            # Take as much as we can from this opportunity
            take_qty = min(remaining_qty, opp['quantity'])
            opportunity_profit = take_qty * opp['profit_per_share']
            
            total_profit += opportunity_profit
            remaining_qty -= take_qty
            
            selected_opportunities.append({
                'method': opp['method'],
                'type': opp['type'],
                'quantity': take_qty,
                'profit_per_share': opp['profit_per_share'],
                'profit': opportunity_profit
            })
        
        # Calculate execution statistics
        executed_qty = self.quantity - remaining_qty
        execution_rate = executed_qty / self.quantity if self.quantity > 0 else 0
        avg_profit_per_share = total_profit / executed_qty if executed_qty > 0 else 0
        
        print(f"\n=== OPTIMAL EXECUTION PLAN ===")
        print(f"Tender quantity: {self.quantity}")
        print(f"Executable quantity: {executed_qty} ({execution_rate*100:.1f}%)")
        print(f"Total profit: {total_profit:.2f} CAD")
        print(f"Average profit per share: {avg_profit_per_share:.4f} CAD")
        
        print(f"\nExecution breakdown:")
        for i, sel_opp in enumerate(selected_opportunities):
            print(f"{i+1}. {sel_opp['method']}: {sel_opp['quantity']} shares @ {sel_opp['profit_per_share']:.4f} CAD/share = {sel_opp['profit']:.2f} CAD")
        
        if remaining_qty > 0:
            print(f"\nWARNING: {remaining_qty} shares cannot be profitably executed")
        
        # Store execution plan for later use
        self.execution_plan = selected_opportunities
        
        profitable = total_profit > MIN_TENDER_PROFIT_CAD and execution_rate >= 0.8  # Need at least 80% execution
        
        return {
            'profitable': profitable,
            'profit': total_profit,
            'executed_quantity': executed_qty,
            'execution_rate': execution_rate,
            'avg_profit_per_share': avg_profit_per_share,
            'remaining_quantity': remaining_qty,
            'execution_plan': selected_opportunities
        }

    def accept_and_execute_tender(self):
        """Accept tender and execute according to the optimal plan"""
        
        # Accept the tender first
        if not accept_tender(self.tender):
            print(f"[ERROR] Failed to accept tender {self.tender['tender_id']}")
            return False
        
        print(f"✓ Accepted tender {self.tender['tender_id']}")
        
        # Execute according to the plan
        total_executed = 0
        total_cost = 0
        
        for step in self.execution_plan:
            print(f"\n--- Executing: {step['method']} ({step['quantity']} shares) ---")
            
            success = False
            step_cost = 0
            
            if step['type'] == 'DIRECT_BUY':
                success, step_cost = self._execute_direct_buy(step['quantity'])
            elif step['type'] == 'DIRECT_SELL':
                success, step_cost = self._execute_direct_sell(step['quantity'])
            elif step['type'] == 'CONVERTER_BUY':
                success, step_cost = self._execute_converter_buy(step['quantity'])
            elif step['type'] == 'CONVERTER_SELL':
                success, step_cost = self._execute_converter_sell(step['quantity'])
            
            if success:
                total_executed += step['quantity']
                total_cost += step_cost
                print(f"✓ Successfully executed {step['quantity']} shares")
            else:
                print(f"✗ Failed to execute {step['quantity']} shares")
                
            # Brief pause between execution steps
            sleep(0.3)
        
        # Final FX cleanup
        self.cleanup_fx_exposure()
        
        execution_rate = total_executed / self.quantity if self.quantity > 0 else 0
        
        print(f"\n*********************** [EXECUTION COMPLETE] ***********************")
        print(f"Executed: {total_executed}/{self.quantity} shares ({execution_rate*100:.1f}%)")
        print(f"Total execution cost: {total_cost:.2f} CAD")
        
        return execution_rate >= 0.9  # 90% success threshold
    
    def _execute_direct_buy(self, qty):
        """Execute direct RITC purchase"""
        try:
            result = place_mkt(RITC, "BUY", qty)
            if result and result.get('vwap', 0) > 0:
                cost_usd = result['vwap'] * qty + qty * FEE_MKT
                cost_cad = cost_usd * best_bid_ask(USD)[1]  # Convert at ask rate
                print(f"✓ Bought {qty} RITC at {result['vwap']:.4f} USD")
                return True, cost_cad
            return False, 0
        except Exception as e:
            print(f"[ERROR] Direct buy failed: {e}")
            return False, 0
    
    def _execute_direct_sell(self, qty):
        """Execute direct RITC sale"""
        try:
            result = place_mkt(RITC, "SELL", qty)
            if result and result.get('vwap', 0) > 0:
                revenue_usd = result['vwap'] * qty - qty * FEE_MKT
                revenue_cad = revenue_usd * best_bid_ask(USD)[0]  # Convert at bid rate
                print(f"✓ Sold {qty} RITC at {result['vwap']:.4f} USD")
                return True, -revenue_cad  # Negative cost (it's revenue)
            return False, 0
        except Exception as e:
            print(f"[ERROR] Direct sell failed: {e}")
            return False, 0
    
    def _execute_converter_buy(self, qty):
        """Execute converter-based RITC creation"""
        try:
            # Step 1: Buy stocks
            bull_result = place_mkt(BULL, "BUY", qty)
            bear_result = place_mkt(BEAR, "BUY", qty)
            
            if not bull_result or not bear_result:
                print("[ERROR] Failed to buy stocks for conversion")
                return False, 0
            
            stock_cost = (bull_result['vwap'] + bear_result['vwap']) * qty + qty * 2 * FEE_MKT
            print(f"✓ Bought stocks: BULL@{bull_result['vwap']:.4f}, BEAR@{bear_result['vwap']:.4f}")
            
            sleep(1)  # Allow orders to settle
            
            # Step 2: Convert to RITC
            conversion_result = self.converter.convert_bull_bear(qty)
            if not conversion_result or not conversion_result.ok:
                print("[ERROR] ETF creation failed")
                # Emergency cleanup: sell stocks
                place_mkt(BULL, "SELL", qty)
                place_mkt(BEAR, "SELL", qty)
                return False, 0
            
            conversion_cost = 1500 * (qty / CONVERTER_BATCH)
            total_cost = stock_cost + conversion_cost
            
            print(f"✓ Created {qty} RITC via converter (total cost: {total_cost:.2f} CAD)")
            return True, total_cost
            
        except Exception as e:
            print(f"[ERROR] Converter buy failed: {e}")
            return False, 0
    
    def _execute_converter_sell(self, qty):
        """Execute converter-based RITC redemption"""
        try:
            # Step 1: Convert RITC to stocks
            conversion_result = self.converter.convert_ritc(qty)
            if not conversion_result or not conversion_result.ok:
                print("[ERROR] ETF redemption failed")
                return False, 0
            
            conversion_cost = 1500 * (qty / CONVERTER_BATCH)
            print(f"✓ Redeemed {qty} RITC to stocks")
            
            sleep(1)  # Allow conversion to settle
            
            # Step 2: Sell stocks
            bull_result = place_mkt(BULL, "SELL", qty)
            bear_result = place_mkt(BEAR, "SELL", qty)
            
            if not bull_result or not bear_result:
                print("[ERROR] Failed to sell stocks after conversion")
                return False, 0
            
            stock_revenue = (bull_result['vwap'] + bear_result['vwap']) * qty - qty * 2 * FEE_MKT
            net_revenue = stock_revenue - conversion_cost
            
            print(f"✓ Sold stocks: BULL@{bull_result['vwap']:.4f}, BEAR@{bear_result['vwap']:.4f}")
            print(f"✓ Net revenue: {net_revenue:.2f} CAD")
            
            return True, -net_revenue  # Negative cost (it's revenue)
            
        except Exception as e:
            print(f"[ERROR] Converter sell failed: {e}")
            return False, 0
    
    def cleanup_fx_exposure(self):
        """Clean up any residual USD exposure"""
        try:
            sleep(1)
            positions = positions_map()
            usd_position = positions.get(USD, 0)
            
            if abs(usd_position) > 0.1:
                action = "SELL" if usd_position > 0 else "BUY"
                result = place_mkt(USD, action, abs(usd_position))
                if result:
                    print(f"✓ FX cleanup: {action} {abs(usd_position):.2f} USD")
                    
        except Exception as e:
            print(f"[ERROR] FX cleanup failed: {e}")


def check_tender(converter):
    """Enhanced tender checking with proper market depth analysis"""
    tenders = get_tenders()
    if not tenders:
        return

    for tender in tenders[:1]:  # Limit to 1 tender for thorough analysis
        print(f"\n=== Evaluating Tender {tender['tender_id']} ===")
        
        if not within_limits():
            print("[WARNING] Position limits - skipping tenders")
            break
        
        T = EvaluateTenders(tender, converter)
        eval_result = T.evaluate_tender_profit()
        
        if eval_result['profitable']:
            print(f"✓ ACCEPTING tender {tender['tender_id']}")
            print(f"  Expected profit: {eval_result['profit']:.2f} CAD")
            print(f"  Execution rate: {eval_result['execution_rate']*100:.1f}%")
            
            success = T.accept_and_execute_tender()
            if success:
                print(f"✓ Successfully processed tender {tender['tender_id']}")
            else:
                print(f"⚠ Partially processed tender {tender['tender_id']}")
                
            sleep(3)  # Longer pause for comprehensive execution
        else:
            print(f"✗ Rejecting tender {tender['tender_id']}")
            print(f"  Profit: {eval_result['profit']:.2f} CAD (threshold: {MIN_TENDER_PROFIT_CAD})")
            print(f"  Execution rate: {eval_result['execution_rate']*100:.1f}%")


*** [TENDER EVAL] BUY 75000.0 @ 24.9500 USD ***
✓ ACCEPTING tender 2178: profit 16115.374999999993 CAD

*********************** [STARTING ADAPTIVE UNWIND] ***********************
Decision Point: Direct Cost=$-25.0423 CAD vs Converter Cost=$-25.0700 CAD

✓ Choosing CONVERTER method for 8600.0 shares.
--- Executing SELL 8600.0 BULL (Patient Aggressor) ---
Placing PASSIVE limit order at 10.0200...
No/partial fill. Going AGGRESSIVE on remaining 8600 shares.
✓ Executed remaining 8600.0 shares aggressively.
✓ Slice Complete: Filled 8600.0 / 8600.0 @ avg price 9.8228
--- Executing SELL 8600.0 BEAR (Patient Aggressor) ---
Placing PASSIVE limit order at 15.5400...
No/partial fill. Going AGGRESSIVE on remaining 8600 shares.
✓ Executed remaining 8600.0 shares aggressively.
✓ Slice Complete: Filled 8600.0 / 8600.0 @ avg price 15.3100
Hedged FX: BUY 214570.00 USD
Hedged FX: BUY 1290.00 USD
✓ Converted 8600.0 shares.
--- 66400.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-25.1532 CAD vs Converter Cost=$-24.9600 CAD

✓ Choosing DIRECT method for 8400.0 shares.
--- Executing SELL 8400.0 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 25.0700...
No/partial fill. Going AGGRESSIVE on remaining 8400 shares.
✓ Executed remaining 8400.0 shares aggressively.
✓ Slice Complete: Filled 8400.0 / 8400.0 @ avg price 24.8700
--- 58000.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-25.1871 CAD vs Converter Cost=$-24.8700 CAD

✓ Choosing DIRECT method for 10000 shares.
--- Executing SELL 10000 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 25.0300...
No/partial fill. Going AGGRESSIVE on remaining 10000 shares.
✓ Executed remaining 10000.0 shares aggressively.
✓ Slice Complete: Filled 10000.0 / 10000 @ avg price 24.8200
--- 48000.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-25.0994 CAD vs Converter Cost=$-24.8100 CAD

✓ Choosing DIRECT method for 10000 shares.
--- Executing SELL 10000 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 24.9900...
No/partial fill. Going AGGRESSIVE on remaining 10000 shares.
✓ Executed remaining 10000.0 shares aggressively.
✓ Slice Complete: Filled 10000.0 / 10000 @ avg price 24.7500
--- 38000.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-25.0735 CAD vs Converter Cost=$-24.7700 CAD

✓ Choosing DIRECT method for 9000.0 shares.
--- Executing SELL 9000.0 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 24.9400...
No/partial fill. Going AGGRESSIVE on remaining 9000 shares.
✓ Executed remaining 9000.0 shares aggressively.
✓ Slice Complete: Filled 9000.0 / 9000.0 @ avg price 24.7067
--- 29000.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-24.9831 CAD vs Converter Cost=$-24.7500 CAD

✓ Choosing DIRECT method for 9500.0 shares.
--- Executing SELL 9500.0 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 24.8000...
No/partial fill. Going AGGRESSIVE on remaining 9500 shares.
✓ Executed remaining 9500.0 shares aggressively.
✓ Slice Complete: Filled 9500.0 / 9500.0 @ avg price 24.5769
--- 19500.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-25.0045 CAD vs Converter Cost=$-24.7500 CAD

✓ Choosing DIRECT method for 10000 shares.
--- Executing SELL 10000 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 24.7800...
No/partial fill. Going AGGRESSIVE on remaining 10000 shares.
✓ Executed remaining 10000.0 shares aggressively.
✓ Slice Complete: Filled 10000.0 / 10000 @ avg price 24.5500
--- 9500.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-24.9725 CAD vs Converter Cost=$-24.7500 CAD

✓ Choosing DIRECT method for 5000 shares.
--- Executing SELL 5000 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 24.7100...
No/partial fill. Going AGGRESSIVE on remaining 5000 shares.
✓ Executed remaining 5000.0 shares aggressively.
✓ Slice Complete: Filled 5000.0 / 5000 @ avg price 24.5100
--- 4500.0 shares remaining. Waiting 2.0s... ---
Decision Point: Direct Cost=$-24.9659 CAD vs Converter Cost=$-24.9600 CAD

✓ Choosing DIRECT method for 4500.0 shares.
--- Executing SELL 4500.0 RITC (Patient Aggressor) ---
Placing PASSIVE limit order at 24.7300...
No/partial fill. Going AGGRESSIVE on remaining 4500 shares.
✓ Executed remaining 4500.0 shares aggressively.
✓ Slice Complete: Filled 4500.0 / 4500.0 @ avg price 24.6509

--- Finalizing FX Exposure ---
Hedged FX: BUY 18579.00 USD
✓ Final FX Cleanup: BUY 18579.00 USD.
Perc of limit orders 0 / 10
*********************** [UNWIND COMPLETE] ***********************
✓ Successfully processed tender 2178
--- FVE Initialized: Direct=$25.00, Synthetic=$25.15 ---
*** [TENDER EVAL] SELL 93000.0 @ 24.8200 USD ***
✓ ACCEPTING tender 3178: profit 1312.8035999999995 CAD

*********************** [STARTING ADAPTIVE UNWIND] ***********************
Decision Point: Direct Cost=$25.1838 CAD vs Converter Cost=$25.3600 CAD

✓ Choosing DIRECT method for 98





    def unwind_pos(self):
        """
        Main controller for unwinding the tender position using an adaptive,
        passive-aggressive limit order strategy with correct cost analysis and hedging.
        """
        
        remaining_qty = self.quantity
        print('234')

        if remaining_qty == 0:
            return True 
    
        side = "BUY" if self.action == 'SELL' else "SELL"
        

        # while remaining_qty > 0:
        filled_qty, vwap = self._execute_direct(side, remaining_qty)
        remaining_qty -= filled_qty

        filled_qty, vwap = self._execute_converted(side, remaining_qty)
        remaining_qty -= filled_qty
        
        if remaining_qty > 0 and filled_qty > 0:
            delay = 0 # Replace with your intelligent delay if desired
            print(f"--- {remaining_qty} shares remaining. Waiting {delay:.1f}s... ---")
            time.sleep(delay)

        if remaining_qty == 0:       
            print(f"Perc of limit orders {self.num_limit_order} / {self.total_orders}")
            print(f"*********************** [UNWIND COMPLETE] ***********************")
        return True