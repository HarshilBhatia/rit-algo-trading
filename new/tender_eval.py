# # # SIMPLIFIED TENDER EVALUATION - Clean and Efficient
# # # Core principle: At each step, compare direct vs converter cost and choose optimal method

# # from final_utils import *
# # import time
# # from rich import print
# # import numpy as np

# # class EvaluateTenders():
# #     def __init__(self, tender, converter):
# #         self.tender = tender
# #         self.action = tender['action']  # SELL or BUY
# #         self.price = tender['price']
# #         self.quantity = tender['quantity']
# #         self.converter = converter
        
# #     def evaluate_tender_profit(self):
# #         """Simplified profit evaluation with proper FX conversion"""
        
# #         # Get market prices
# #         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
# #         ritc_bid, ritc_ask, _, _ = best_bid_ask(RITC) 
# #         bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
# #         bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
        
# #         # Calculate profit for the tender
# #         if self.action == 'SELL':
# #             # We sell RITC for tender_price USD, need to buy back at market
# #             tender_proceeds_cad = self.price * self.quantity * usd_bid  # Convert USD to CAD
# #             buyback_cost_cad = ritc_ask * self.quantity * usd_ask + self.quantity * FEE_MKT
# #             profit = tender_proceeds_cad - buyback_cost_cad
            
# #         else:  # BUY  
# #             # We buy RITC at tender_price USD, can sell at market
# #             market_proceeds_cad = ritc_bid * self.quantity * usd_bid - self.quantity * FEE_MKT  
# #             tender_cost_cad = self.price * self.quantity * usd_ask
# #             profit = market_proceeds_cad - tender_cost_cad
        
# #         print(f"*********************** [TENDER EVAL] ***********************")
# #         print(f"Tender: {self.action} {self.quantity} @ {self.price:.4f} USD")
# #         print(f"Estimated profit: {profit:.2f} CAD")
        
# #         profitable = profit > MIN_TENDER_PROFIT_CAD
# #         return {
# #             'profitable': profitable,
# #             'profit': profit
# #         }

# #     def accept_and_unwind_tender(self):
# #         """Accept tender and intelligently unwind position"""
        
# #         # Accept the tender first
# #         if not accept_tender(self.tender):
# #             print(f"[ERROR] Failed to accept tender {self.tender['tender_id']}")
# #             return False
        
# #         print(f"✓ Accepted tender {self.tender['tender_id']}")
        
# #         # Now we have a position to unwind
# #         remaining_qty = self.quantity
# #         total_unwinding_cost = 0
        
# #         while remaining_qty > 0:
# #             # Determine optimal chunk size (limited by converter batch or remaining)
# #             chunk_size = min(remaining_qty, 10000, 5000)  # Max 5000 for better execution
            
# #             # Calculate costs for both methods  
# #             direct_cost = self.calculate_direct_cost(chunk_size)
# #             converter_cost = self.calculate_converter_cost(chunk_size)
            
# #             print(f"\n--- Unwinding {chunk_size} shares (remaining: {remaining_qty}) ---")
# #             print(f"Direct method cost: {direct_cost:.2f} CAD")
# #             print(f"Converter method cost: {converter_cost:.2f} CAD")
            
# #             # Choose the cheaper method
# #             if direct_cost < converter_cost:
# #                 print("✓ Choosing DIRECT method")
# #                 success = self.execute_direct_unwind(chunk_size)
# #                 actual_cost = direct_cost
# #             else:
# #                 print("✓ Choosing CONVERTER method")
# #                 success = self.execute_converter_unwind(chunk_size)
# #                 actual_cost = converter_cost
                
# #             if success:
# #                 remaining_qty -= chunk_size
# #                 total_unwinding_cost += actual_cost
# #                 print(f"✓ Successfully unwound {chunk_size} shares")
# #             else:
# #                 print(f"✗ Failed to unwind {chunk_size} shares")
# #                 # Try smaller chunk or break
# #                 if chunk_size > 1000:
# #                     chunk_size = 1000
# #                     continue
# #                 else:
# #                     print("[ERROR] Cannot continue unwinding")
# #                     break
            
# #             # Brief pause between chunks
# #             if remaining_qty > 0:
# #                 sleep(0.5)
        
# #         # Final cleanup of any residual FX exposure
# #         self.cleanup_fx_exposure()
        
# #         success_rate = (self.quantity - remaining_qty) / self.quantity
# #         print(f"\n*********************** [UNWIND COMPLETE] ***********************")
# #         print(f"Unwound: {self.quantity - remaining_qty}/{self.quantity} shares ({success_rate*100:.1f}%)")
# #         print(f"Total unwinding cost: {total_unwinding_cost:.2f} CAD")
        
# #         return success_rate >= 0.95  # 95% success threshold

# #     def calculate_direct_cost(self, qty):
# #         """Calculate cost of direct ETF trading"""
# #         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        
# #         if self.action == 'SELL':
# #             # We're short RITC, need to buy RITC directly
# #             ritc_ask_price, max_qty = calculate_sweep_cost(RITC, "BUY", qty)
# #             if max_qty < qty:
# #                 return float('inf')  # Not enough liquidity
            
# #             etf_cost_usd = ritc_ask_price * qty + qty * FEE_MKT
# #             fx_cost_cad = etf_cost_usd * usd_ask  # Need to buy USD at ask
# #             return fx_cost_cad
            
# #         else:  # BUY tender
# #             # We're long RITC, need to sell RITC directly  
# #             ritc_bid_price, max_qty = calculate_sweep_cost(RITC, "SELL", qty)
# #             if max_qty < qty:
# #                 return float('inf')
            
# #             # This actually gives us USD, so it's negative cost (revenue)
# #             etf_revenue_usd = ritc_bid_price * qty - qty * FEE_MKT
# #             fx_revenue_cad = etf_revenue_usd * usd_bid  # Sell USD at bid
# #             return -fx_revenue_cad  # Negative because it's revenue

# #     def calculate_converter_cost(self, qty):
# #         """Calculate cost of converter method"""
# #         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        
# #         if self.action == 'SELL':
# #             # We're short RITC: Buy stocks → Convert to RITC
# #             bull_ask_price, bull_max = calculate_sweep_cost(BULL, "BUY", qty)
# #             bear_ask_price, bear_max = calculate_sweep_cost(BEAR, "BUY", qty)
            
# #             if bull_max < qty or bear_max < qty:
# #                 return float('inf')  # Not enough stock liquidity
                
# #             stock_cost_cad = (bull_ask_price + bear_ask_price) * qty + qty * 2 * FEE_MKT
# #             conversion_fee_cad = conversion_cost(qty)
            
# #             return stock_cost_cad + conversion_fee_cad
            
# #         else:  # BUY tender
# #             # We're long RITC: Convert RITC → Sell stocks
# #             bull_bid_price, bull_max = calculate_sweep_cost(BULL, "SELL", qty) 
# #             bear_bid_price, bear_max = calculate_sweep_cost(BEAR, "SELL", qty)
            
# #             if bull_max < qty or bear_max < qty:
# #                 return float('inf')
                
# #             # This gives us revenue from stocks, costs conversion fee
# #             stock_revenue_cad = (bull_bid_price + bear_bid_price) * qty - qty * 2 * FEE_MKT
# #             conversion_fee_cad = conversion_cost(qty)
            
# #             return conversion_fee_cad - stock_revenue_cad  # Net cost

# #     def execute_direct_unwind(self, qty):
# #         """Execute direct ETF trading"""
# #         try:
# #             if self.action == 'SELL':
# #                 # Buy RITC to cover short
# #                 result = place_mkt(RITC, "BUY", qty)
# #                 if result and result.get('vwap', 0) > 0:
# #                     print(f"✓ Bought {qty} RITC at {result['vwap']:.4f} USD")
# #                     return True
                    
# #             else:  # BUY tender
# #                 # Sell RITC
# #                 result = place_mkt(RITC, "SELL", qty)
# #                 if result and result.get('vwap', 0) > 0:
# #                     print(f"✓ Sold {qty} RITC at {result['vwap']:.4f} USD")
# #                     return True
                    
# #             return False
            
# #         except Exception as e:
# #             print(f"[ERROR] Direct unwind failed: {e}")
# #             return False

# #     def execute_converter_unwind(self, qty):
# #         """Execute converter-based unwinding"""
# #         try:
# #             if self.action == 'SELL':
# #                 # We're short RITC: Buy stocks → Convert to RITC
                
# #                 # Step 1: Buy stocks
# #                 bull_result = place_mkt(BULL, "BUY", qty)
# #                 bear_result = place_mkt(BEAR, "BUY", qty)
                
# #                 if not bull_result or not bear_result:
# #                     print("[ERROR] Failed to buy stocks")
# #                     return False
                
# #                 print(f"✓ Bought {qty} BULL and BEAR")
# #                 sleep(1)  # Allow orders to settle
                
# #                 # Step 2: Convert to RITC
# #                 conversion_result = self.converter.convert_bull_bear(qty)
# #                 if not conversion_result or not conversion_result.ok:
# #                     print(f"[ERROR] ETF creation failed")
# #                     # Emergency: sell the stocks we just bought
# #                     place_mkt(BULL, "SELL", qty)
# #                     place_mkt(BEAR, "SELL", qty)
# #                     return False
                
# #                 print(f"✓ Converted {qty} stocks to RITC")
# #                 return True
                
# #             else:  # BUY tender
# #                 # We're long RITC: Convert RITC → Sell stocks
                
# #                 # Step 1: Convert RITC to stocks
# #                 conversion_result = self.converter.convert_ritc(qty)
# #                 if not conversion_result or not conversion_result.ok:
# #                     print(f"[ERROR] ETF redemption failed")
# #                     return False
                    
# #                 print(f"✓ Converted {qty} RITC to stocks")
# #                 sleep(1)  # Allow conversion to settle
                
# #                 # Step 2: Sell stocks
# #                 bull_result = place_mkt(BULL, "SELL", qty)
# #                 bear_result = place_mkt(BEAR, "SELL", qty)
                
# #                 if not bull_result or not bear_result:
# #                     print("[WARNING] Failed to sell some stocks")
# #                     # Don't return False - we still made progress
                    
# #                 print(f"✓ Sold {qty} BULL and BEAR")
# #                 return True
                
# #         except Exception as e:
# #             print(f"[ERROR] Converter unwind failed: {e}")
# #             return False

# #     def cleanup_fx_exposure(self):
# #         """Clean up any residual USD exposure"""
# #         try:
# #             sleep(1)  # Allow all trades to settle
            
# #             # Check actual USD position
# #             positions = positions_map()
# #             usd_position = positions.get(USD, 0)
            
# #             if abs(usd_position) > 0.1:  # Only if meaningful exposure
# #                 action = "SELL" if usd_position > 0 else "BUY"
# #                 result = place_mkt(USD, action, abs(usd_position))
                
# #                 if result:
# #                     print(f"✓ FX cleanup: {action} {abs(usd_position):.2f} USD")
# #                 else:
# #                     print(f"[WARNING] Failed to cleanup {usd_position:.2f} USD")
                    
# #         except Exception as e:
# #             print(f"[ERROR] FX cleanup failed: {e}")


# # def check_tender(converter):
# #     """Simplified tender checking with optimal unwinding"""
# #     tenders = get_tenders()

# #     for tender in tenders:  # Limit to 2 tenders for safety
# #         print(f"\n=== Evaluating Tender {tender['tender_id']} ===")
        
# #         # Quick position limit check
# #         if not within_limits():
# #             print("[WARNING] Position limits - skipping tenders")
# #             break
        
# #         T = EvaluateTenders(tender, converter)
# #         eval_result = T.evaluate_tender_profit()
        
# #         if eval_result['profitable']:
# #             print(f"✓ ACCEPTING tender {tender['tender_id']}: profit {eval_result['profit']:.2f} CAD")
            
# #             success = T.accept_and_unwind_tender()
# #             if success:
# #                 print(f"✓ Successfully processed tender {tender['tender_id']}")
# #             else:
# #                 print(f"⚠ Partially processed tender {tender['tender_id']}")
                
# #             # Pause between tenders for safety
# #             sleep(2)
# #         else:
# #             print(f"✗ Rejecting tender {tender['tender_id']}: insufficient profit")


# # FIXED TENDER EVALUATION - Correct Converter Cost Logic
# # Fix: Converter cost is proportional (1500 * q/10000), max batch is 10k, not minimum!

# from final_utils import *
# import time
# from rich import print
# import numpy as np

# class EvaluateTenders():
#     def __init__(self, tender, converter):
#         self.tender = tender
#         self.action = tender['action']  # SELL or BUY
#         self.price = tender['price']
#         self.quantity = tender['quantity']
#         self.converter = converter
        
#     def evaluate_tender_profit(self):
#         """Simplified profit evaluation with proper FX conversion"""
        
#         # Get market prices
#         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
#         ritc_bid, ritc_ask, _, _ = best_bid_ask(RITC) 
        
#         # Calculate profit for the tender
#         if self.action == 'SELL':
#             # We sell RITC for tender_price USD, need to buy back at market
#             tender_proceeds_cad = self.price * self.quantity * usd_bid  # Convert USD to CAD
#             buyback_cost_cad = ritc_ask * self.quantity * usd_ask + self.quantity * FEE_MKT
#             profit = tender_proceeds_cad - buyback_cost_cad
            
#         else:  # BUY  
#             # We buy RITC at tender_price USD, can sell at market
#             market_proceeds_cad = ritc_bid * self.quantity * usd_bid - self.quantity * FEE_MKT  
#             tender_cost_cad = self.price * self.quantity * usd_ask
#             profit = market_proceeds_cad - tender_cost_cad
        
#         print(f"*********************** [TENDER EVAL] ***********************")
#         print(f"Tender: {self.action} {self.quantity} @ {self.price:.4f} USD")
#         print(f"Estimated profit: {profit:.2f} CAD")
        
#         profitable = profit > MIN_TENDER_PROFIT_CAD
#         return {
#             'profitable': profitable,
#             'profit': profit
#         }

#     def accept_and_unwind_tender(self):
#         """Accept tender and intelligently unwind position"""
        
#         # Accept the tender first
#         if not accept_tender(self.tender):
#             print(f"[ERROR] Failed to accept tender {self.tender['tender_id']}")
#             return False
        
#         print(f"✓ Accepted tender {self.tender['tender_id']}")
        
#         # Now we have a position to unwind
#         remaining_qty = self.quantity
#         total_unwinding_cost = 0
        
#         while remaining_qty > 0:
#             # Determine optimal chunk size (max 10k for converter limit)
#             chunk_size = min(remaining_qty, 10000, 5000)  # Reasonable chunk size, max 5k for execution
            
#             # Calculate costs for both methods  
#             direct_cost = self.calculate_direct_cost(chunk_size)
#             converter_cost = self.calculate_converter_cost(chunk_size)
            
#             print(f"\n--- Unwinding {chunk_size} shares (remaining: {remaining_qty}) ---")
#             print(f"Direct method cost: {direct_cost:.2f} CAD")
#             print(f"Converter method cost: {converter_cost:.2f} CAD")
            
#             # Choose the cheaper method
#             if direct_cost < converter_cost:
#                 print("✓ Choosing DIRECT method")
#                 success = self.execute_direct_unwind(chunk_size)
#                 actual_cost = direct_cost
#             else:
#                 print("✓ Choosing CONVERTER method")
#                 success = self.execute_converter_unwind(chunk_size)
#                 actual_cost = converter_cost
                
#             if success:
#                 remaining_qty -= chunk_size
#                 total_unwinding_cost += actual_cost
#                 print(f"✓ Successfully unwound {chunk_size} shares")
#             else:
#                 print(f"✗ Failed to unwind {chunk_size} shares")
#                 # Try smaller chunk or break
#                 if chunk_size > 1000:
#                     chunk_size = min(remaining_qty, 1000)
#                     continue
#                 else:
#                     print("[ERROR] Cannot continue unwinding")
#                     break
            
#             # Brief pause between chunks
#             if remaining_qty > 0:
#                 sleep(0.5)
        
#         # Final cleanup of any residual FX exposure
#         self.cleanup_fx_exposure()
        
#         success_rate = (self.quantity - remaining_qty) / self.quantity
#         print(f"\n*********************** [UNWIND COMPLETE] ***********************")
#         print(f"Unwound: {self.quantity - remaining_qty}/{self.quantity} shares ({success_rate*100:.1f}%)")
#         print(f"Total unwinding cost: {total_unwinding_cost:.2f} CAD")
        
#         return success_rate >= 0.95  # 95% success threshold

#     def calculate_direct_cost(self, qty):
#         """Calculate cost of direct ETF trading"""
#         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        
#         if self.action == 'SELL':
#             # We're short RITC, need to buy RITC directly
#             ritc_ask_price, max_qty = calculate_sweep_cost(RITC, "BUY", qty)
#             if max_qty < qty:
#                 return float('inf')  # Not enough liquidity
            
#             etf_cost_usd = ritc_ask_price * qty + qty * FEE_MKT
#             fx_cost_cad = etf_cost_usd * usd_ask  # Need to buy USD at ask
#             return fx_cost_cad
            
#         else:  # BUY tender
#             # We're long RITC, need to sell RITC directly  
#             ritc_bid_price, max_qty = calculate_sweep_cost(RITC, "SELL", qty)
#             if max_qty < qty:
#                 return float('inf')
            
#             # This actually gives us USD, so it's negative cost (revenue)
#             etf_revenue_usd = ritc_bid_price * qty - qty * FEE_MKT
#             fx_revenue_cad = etf_revenue_usd * usd_bid  # Sell USD at bid
#             return -fx_revenue_cad  # Negative because it's revenue

#     def calculate_converter_cost(self, qty):
#         """FIXED: Calculate cost of converter method with proportional pricing"""
        
#         # FIXED: Only reject if quantity exceeds maximum batch size
#         if qty > CONVERTER_BATCH:  # 10,000 is MAXIMUM, not minimum!
#             return float('inf')  # Cannot convert more than 10k at once
        
#         if qty <= 0:
#             return float('inf')  # Cannot convert zero or negative shares
            
#         usd_bid, usd_ask, _, _ = best_bid_ask(USD)
        
#         if self.action == 'SELL':
#             # We're short RITC: Buy stocks → Convert to RITC
#             bull_ask_price, bull_max = calculate_sweep_cost(BULL, "BUY", qty)
#             bear_ask_price, bear_max = calculate_sweep_cost(BEAR, "BUY", qty)
            
#             if bull_max < qty or bear_max < qty:
#                 return float('inf')  # Not enough stock liquidity
                
#             stock_cost_cad = (bull_ask_price + bear_ask_price) * qty + qty * 2 * FEE_MKT
            
#             # FIXED: Proportional conversion cost
#             conversion_fee_cad = 1500 * (qty / CONVERTER_BATCH)  # Scale by proportion
            
#             return stock_cost_cad + conversion_fee_cad
            
#         else:  # BUY tender
#             # We're long RITC: Convert RITC → Sell stocks
#             bull_bid_price, bull_max = calculate_sweep_cost(BULL, "SELL", qty) 
#             bear_bid_price, bear_max = calculate_sweep_cost(BEAR, "SELL", qty)
            
#             if bull_max < qty or bear_max < qty:
#                 return float('inf')
                
#             # This gives us revenue from stocks, costs conversion fee
#             stock_revenue_cad = (bull_bid_price + bear_bid_price) * qty - qty * 2 * FEE_MKT
            
#             # FIXED: Proportional conversion cost  
#             conversion_fee_cad = 1500 * (qty / CONVERTER_BATCH)  # Scale by proportion
            
#             return conversion_fee_cad - stock_revenue_cad  # Net cost

#     def execute_direct_unwind(self, qty):
#         """Execute direct ETF trading"""
#         try:
#             if self.action == 'SELL':
#                 # Buy RITC to cover short
#                 result = place_mkt(RITC, "BUY", qty)
#                 if result and result.get('vwap', 0) > 0:
#                     print(f"✓ Bought {qty} RITC at {result['vwap']:.4f} USD")
#                     return True
                    
#             else:  # BUY tender
#                 # Sell RITC
#                 result = place_mkt(RITC, "SELL", qty)
#                 if result and result.get('vwap', 0) > 0:
#                     print(f"✓ Sold {qty} RITC at {result['vwap']:.4f} USD")
#                     return True
                    
#             return False
            
#         except Exception as e:
#             print(f"[ERROR] Direct unwind failed: {e}")
#             return False

#     def execute_converter_unwind(self, qty):
#         """Execute converter-based unwinding - can handle any amount up to 10k"""
#         if qty > CONVERTER_BATCH:
#             print(f"[ERROR] Converter cannot handle more than {CONVERTER_BATCH} shares, got {qty}")
#             return False
            
#         try:
#             if self.action == 'SELL':
#                 # We're short RITC: Buy stocks → Convert to RITC
                
#                 # Step 1: Buy stocks
#                 bull_result = place_mkt(BULL, "BUY", qty)
#                 bear_result = place_mkt(BEAR, "BUY", qty)
                
#                 if not bull_result or not bear_result:
#                     print("[ERROR] Failed to buy stocks")
#                     return False
                
#                 print(f"✓ Bought {qty} BULL and BEAR")
#                 sleep(1)  # Allow orders to settle
                
#                 # Step 2: Convert to RITC
#                 conversion_result = self.converter.convert_bull_bear(qty)
#                 if not conversion_result or not conversion_result.ok:
#                     print(f"[ERROR] ETF creation failed")
#                     # Emergency: sell the stocks we just bought
#                     place_mkt(BULL, "SELL", qty)
#                     place_mkt(BEAR, "SELL", qty)
#                     return False
                
#                 print(f"✓ Converted {qty} stocks to RITC (cost: {1500 * qty / CONVERTER_BATCH:.2f} CAD)")
#                 return True
                
#             else:  # BUY tender
#                 # We're long RITC: Convert RITC → Sell stocks
                
#                 # Step 1: Convert RITC to stocks
#                 conversion_result = self.converter.convert_ritc(qty)
#                 if not conversion_result or not conversion_result.ok:
#                     print(f"[ERROR] ETF redemption failed")
#                     return False
                    
#                 print(f"✓ Converted {qty} RITC to stocks (cost: {1500 * qty / CONVERTER_BATCH:.2f} CAD)")
#                 sleep(1)  # Allow conversion to settle
                
#                 # Step 2: Sell stocks
#                 bull_result = place_mkt(BULL, "SELL", qty)
#                 bear_result = place_mkt(BEAR, "SELL", qty)
                
#                 if not bull_result or not bear_result:
#                     print("[WARNING] Failed to sell some stocks")
#                     # Don't return False - we still made progress
                    
#                 print(f"✓ Sold {qty} BULL and BEAR")
#                 return True
                
#         except Exception as e:
#             print(f"[ERROR] Converter unwind failed: {e}")
#             return False

#     def cleanup_fx_exposure(self):
#         """Clean up any residual USD exposure"""
#         try:
#             sleep(1)  # Allow all trades to settle
            
#             # Check actual USD position
#             positions = positions_map()
#             usd_position = positions.get(USD, 0)
            
#             if abs(usd_position) > 0.1:  # Only if meaningful exposure
#                 action = "SELL" if usd_position > 0 else "BUY"
#                 result = place_mkt(USD, action, abs(usd_position))
                
#                 if result:
#                     print(f"✓ FX cleanup: {action} {abs(usd_position):.2f} USD")
#                 else:
#                     print(f"[WARNING] Failed to cleanup {usd_position:.2f} USD")
                    
#         except Exception as e:
#             print(f"[ERROR] FX cleanup failed: {e}")


# def check_tender(converter):
#     """Fixed tender checking with correct converter cost logic"""
#     tenders = get_tenders()
#     if not tenders:
#         return

#     for tender in tenders[:2]:  # Limit to 2 tenders for safety
#         print(f"\n=== Evaluating Tender {tender['tender_id']} ===")
        
#         # Quick position limit check
#         if not within_limits():
#             print("[WARNING] Position limits - skipping tenders")
#             break
        
#         T = EvaluateTenders(tender, converter)
#         eval_result = T.evaluate_tender_profit()
        
#         if eval_result['profitable']:
#             print(f"✓ ACCEPTING tender {tender['tender_id']}: profit {eval_result['profit']:.2f} CAD")
            
#             success = T.accept_and_unwind_tender()
#             if success:
#                 print(f"✓ Successfully processed tender {tender['tender_id']}")
#             else:
#                 print(f"⚠ Partially processed tender {tender['tender_id']}")
                
#             # Pause between tenders for safety
#             sleep(2)
#         else:
#             print(f"✗ Rejecting tender {tender['tender_id']}: insufficient profit")


# # DEBUGGING: Test the fixed converter cost calculation
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
        
#         print(f"Quantity: {qty:5d} | Cost: {cost:8.2f} | Expected conv fee: {expected_conversion_fee:.2f}")

# if __name__ == "__main__":
#     test_fixed_converter_cost()


# COMPLETELY REWRITTEN TENDER EVALUATION - Proper Market Depth Analysis
# Core principle: Analyze full order book depth, create opportunity list, select optimal execution path

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