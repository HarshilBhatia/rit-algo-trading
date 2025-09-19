# FIXED ARBITRAGE MODULE  
# Major fixes: Correct currency conversion, proper execution sequence, complete profit calculations

from final_utils import *

def check_conversion_arbitrage_fixed(converter):
    """COMPLETELY FIXED: Arbitrage with correct FX, sequencing, and profit calculations"""
    
    # Get current market prices
    bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
    bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
    ritc_bid_usd, ritc_ask_usd, _, _ = best_bid_ask(RITC)
    usd_bid, usd_ask, _, _ = best_bid_ask(USD)
    
    # FIXED: Use smaller, more realistic trade size
    q = 500  # Reduced trade size for better execution
    
    print(f"\n=== FIXED ARBITRAGE ANALYSIS ===")
    print(f"BULL: {bull_bid:.4f}/{bull_ask:.4f} CAD")
    print(f"BEAR: {bear_bid:.4f}/{bear_ask:.4f} CAD")
    print(f"RITC: {ritc_bid_usd:.4f}/{ritc_ask_usd:.4f} USD")
    print(f"USD: {usd_bid:.6f}/{usd_ask:.6f} CAD/USD")
    print(f"Trade size: {q} shares")

    # Direction 1: Create ETF (Buy stocks → Convert → Sell ETF)
    # FIXED: Account for all costs and proper FX conversion
    stock_cost_total = (bull_ask + bear_ask) * q  # Cost to buy stocks
    stock_fees = q * 0.04  # Stock transaction fees (2¢ per share for each stock)
    conversion_cost_cad = 1500  # Converter fee in CAD
    
    # ETF sale proceeds (we get USD, then convert to CAD at bid rate)
    etf_sale_proceeds_usd = ritc_bid_usd * q  # USD from selling ETF
    etf_fees_usd = q * 0.02  # ETF transaction fee in USD
    net_etf_proceeds_usd = etf_sale_proceeds_usd - etf_fees_usd
    net_etf_proceeds_cad = net_etf_proceeds_usd * usd_bid  # Convert USD to CAD at bid
    
    total_cost_direction1 = stock_cost_total + stock_fees + conversion_cost_cad
    profit1 = net_etf_proceeds_cad - total_cost_direction1
    
    # Direction 2: Redeem ETF (Buy ETF → Convert → Sell stocks)
    # FIXED: Account for all costs and proper FX conversion
    etf_cost_usd = ritc_ask_usd * q + q * 0.02  # Cost to buy ETF including fees
    fx_cost_to_buy_usd = etf_cost_usd * usd_ask  # CAD cost to buy required USD
    
    # Stock sale proceeds
    stock_sale_proceeds = (bull_bid + bear_bid) * q  # CAD from selling stocks
    stock_sale_fees = q * 0.04  # Stock transaction fees
    net_stock_proceeds = stock_sale_proceeds - stock_sale_fees
    
    total_cost_direction2 = fx_cost_to_buy_usd + conversion_cost_cad
    profit2 = net_stock_proceeds - total_cost_direction2

    print(f"Direction 1 (Create ETF): {profit1:.2f} CAD")
    print(f"  Stock cost: {stock_cost_total:.2f} + fees: {stock_fees:.2f}")
    print(f"  Conversion: {conversion_cost_cad:.2f} CAD")
    print(f"  ETF proceeds: {net_etf_proceeds_cad:.2f} CAD")
    
    print(f"Direction 2 (Redeem ETF): {profit2:.2f} CAD") 
    print(f"  ETF cost: {fx_cost_to_buy_usd:.2f} CAD")
    print(f"  Conversion: {conversion_cost_cad:.2f} CAD") 
    print(f"  Stock proceeds: {net_stock_proceeds:.2f} CAD")

    # Calculate theoretical fair value for reference
    theoretical_etf_cad = (bull_bid + bull_ask + bear_bid + bear_ask) / 2
    market_etf_cad = (ritc_bid_usd + ritc_ask_usd) / 2 * (usd_bid + usd_ask) / 2
    deviation = abs(theoretical_etf_cad - market_etf_cad)
    
    print(f"Fair RITC: {theoretical_etf_cad:.4f} CAD, Market: {market_etf_cad:.4f} CAD")
    print(f"Deviation: {deviation:.4f} CAD")

    # Execute only if profitable above minimum threshold
    min_profit_threshold = 50  # CAD minimum profit to cover execution risks
    
    if profit1 > min_profit_threshold and profit1 > profit2 and within_limits():
        print(f"✓ EXECUTING Direction 1: Create ETF ({profit1:.2f} CAD profit)")
        return execute_create_etf_arbitrage_fixed(converter, q, profit1)
        
    elif profit2 > min_profit_threshold and within_limits():
        print(f"✓ EXECUTING Direction 2: Redeem ETF ({profit2:.2f} CAD profit)")
        return execute_redeem_etf_arbitrage_fixed(converter, q, profit2)
        
    else:
        print("✗ No profitable arbitrage opportunity")
        print(f"  Minimum threshold: {min_profit_threshold} CAD")
        return False

def execute_create_etf_arbitrage_fixed(converter, q, expected_profit):
    """FIXED: Create ETF arbitrage with proper sequencing and error handling"""
    try:
        print(f"\n--- EXECUTING CREATE ETF ARBITRAGE ({q} shares) ---")
        
        # Step 1: Buy stocks simultaneously
        print("Step 1: Buying stocks...")
        bull_result = place_mkt(BULL, "BUY", q)
        bear_result = place_mkt(BEAR, "BUY", q)
        
        if not bull_result or not bear_result:
            print("[ERROR] Failed to buy stocks")
            return False
            
        bull_avg_price = bull_result.get('vwap', 0)
        bear_avg_price = bear_result.get('vwap', 0)
        total_stock_cost = (bull_avg_price + bear_avg_price) * q
        
        print(f"✓ Bought stocks: BULL@{bull_avg_price:.4f}, BEAR@{bear_avg_price:.4f}")
        print(f"  Total stock cost: {total_stock_cost:.2f} CAD")
        
        # Step 2: Wait and convert to ETF
        sleep(1)  # Allow stock purchases to settle
        print("Step 2: Converting stocks to ETF...")
        
        conversion_result = converter.convert_bull_bear(q)
        if not conversion_result or not conversion_result.ok:
            print(f"[ERROR] ETF creation failed: {conversion_result.text if conversion_result else 'No response'}")
            # Emergency cleanup: sell the stocks we bought
            place_mkt(BULL, "SELL", q)
            place_mkt(BEAR, "SELL", q)
            return False
            
        print(f"✓ Created {q} ETF shares (cost: 1500 CAD)")
        
        # Step 3: Wait and sell ETF
        sleep(1)  # Allow conversion to settle
        print("Step 3: Selling ETF...")
        
        etf_result = place_mkt(RITC, "SELL", q)
        if not etf_result:
            print("[ERROR] Failed to sell ETF")
            return False
            
        etf_avg_price = etf_result.get('vwap', 0)
        etf_proceeds_usd = etf_avg_price * q
        
        print(f"✓ Sold ETF: {q}@{etf_avg_price:.4f} USD = {etf_proceeds_usd:.2f} USD")
        
        # Step 4: Convert USD proceeds to CAD immediately
        sleep(0.5)  # Brief pause
        print("Step 4: Converting USD to CAD...")
        
        fx_result = place_mkt(USD, "SELL", etf_proceeds_usd)
        if not fx_result:
            print("[WARNING] Failed to convert USD to CAD")
            cad_proceeds = etf_proceeds_usd * 1.35  # Estimate
        else:
            fx_rate = fx_result.get('vwap', 1.35)
            cad_proceeds = etf_proceeds_usd * fx_rate
            
        print(f"✓ Converted to CAD: {etf_proceeds_usd:.2f} USD → {cad_proceeds:.2f} CAD")
        
        # Calculate actual profit
        total_cost = total_stock_cost + 1500 + q * 0.06  # Stocks + conversion + all fees
        actual_profit = cad_proceeds - total_cost
        
        print(f"📊 ARBITRAGE RESULT:")
        print(f"   Expected profit: {expected_profit:.2f} CAD")
        print(f"   Actual profit: {actual_profit:.2f} CAD")
        print(f"   Efficiency: {(actual_profit/expected_profit)*100:.1f}%")
        print("--- CREATE ETF ARBITRAGE COMPLETE ---\n")
        
        return actual_profit > 0
        
    except Exception as e:
        print(f"[ERROR] Create ETF arbitrage failed: {e}")
        return False

def execute_redeem_etf_arbitrage_fixed(converter, q, expected_profit):
    """FIXED: Redeem ETF arbitrage with proper sequencing and error handling"""
    try:
        print(f"\n--- EXECUTING REDEEM ETF ARBITRAGE ({q} shares) ---")
        
        # Step 1: Calculate USD needed and buy USD
        etf_ask_price = best_bid_ask(RITC)[1]
        usd_needed = etf_ask_price * q * 1.02  # Add buffer for fees and slippage
        
        print("Step 1: Buying USD...")
        fx_result = place_mkt(USD, "BUY", usd_needed)
        if not fx_result:
            print("[ERROR] Failed to buy USD")
            return False
            
        usd_cost_cad = fx_result.get('vwap', 1.35) * usd_needed
        print(f"✓ Bought USD: {usd_needed:.2f} USD for {usd_cost_cad:.2f} CAD")
        
        # Step 2: Buy ETF with USD
        sleep(0.5)  # Allow FX to settle
        print("Step 2: Buying ETF...")
        
        etf_result = place_mkt(RITC, "BUY", q)
        if not etf_result:
            print("[ERROR] Failed to buy ETF")
            # Emergency cleanup: sell USD we bought
            place_mkt(USD, "SELL", usd_needed)
            return False
            
        etf_avg_price = etf_result.get('vwap', 0)
        etf_cost_usd = etf_avg_price * q
        
        print(f"✓ Bought ETF: {q}@{etf_avg_price:.4f} USD = {etf_cost_usd:.2f} USD")
        
        # Step 3: Convert ETF to stocks
        sleep(1)  # Allow ETF purchase to settle
        print("Step 3: Converting ETF to stocks...")
        
        conversion_result = converter.convert_ritc(q)
        if not conversion_result or not conversion_result.ok:
            print(f"[ERROR] ETF redemption failed: {conversion_result.text if conversion_result else 'No response'}")
            # Emergency cleanup: sell ETF we bought
            place_mkt(RITC, "SELL", q)
            return False
            
        print(f"✓ Redeemed {q} ETF to stocks (cost: 1500 CAD)")
        
        # Step 4: Wait and sell stocks
        sleep(1)  # Allow conversion to settle
        print("Step 4: Selling stocks...")
        
        bull_result = place_mkt(BULL, "SELL", q)
        bear_result = place_mkt(BEAR, "SELL", q)
        
        if not bull_result or not bear_result:
            print("[WARNING] Failed to sell some stocks")
            return False
            
        bull_proceeds = bull_result.get('vwap', 0) * q
        bear_proceeds = bear_result.get('vwap', 0) * q
        total_stock_proceeds = bull_proceeds + bear_proceeds
        
        print(f"✓ Sold stocks: {bull_proceeds:.2f} + {bear_proceeds:.2f} = {total_stock_proceeds:.2f} CAD")
        
        # Calculate actual profit
        total_cost = usd_cost_cad + 1500 + q * 0.06  # FX cost + conversion + fees
        actual_profit = total_stock_proceeds - total_cost
        
        print(f"📊 ARBITRAGE RESULT:")
        print(f"   Expected profit: {expected_profit:.2f} CAD")
        print(f"   Actual profit: {actual_profit:.2f} CAD")
        print(f"   Efficiency: {(actual_profit/expected_profit)*100:.1f}%")
        print("--- REDEEM ETF ARBITRAGE COMPLETE ---\n")
        
        return actual_profit > 0
        
    except Exception as e:
        print(f"[ERROR] Redeem ETF arbitrage failed: {e}")
        return False



def statistical_arbitrage_fixed():
    """FIXED: Statistical arbitrage without converter, focusing on price relationships"""
    try:
        # Get mid prices for fair value calculation
        bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
        bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
        ritc_bid_usd, ritc_ask_usd, _, _ = best_bid_ask(RITC)
        usd_bid, usd_ask, _, _ = best_bid_ask(USD)

        bull_mid = (bull_bid + bull_ask) / 2
        bear_mid = (bear_bid + bear_ask) / 2
        ritc_mid_usd = (ritc_bid_usd + ritc_ask_usd) / 2
        usd_mid = (usd_bid + usd_ask) / 2

        # Calculate fair value relationship
        fair_etf_cad = bull_mid + bear_mid  # ETF should equal sum of components
        market_etf_cad = ritc_mid_usd * usd_mid
        deviation = fair_etf_cad - market_etf_cad
        deviation_pct = abs(deviation) / fair_etf_cad * 100

        print(f"\n=== STATISTICAL ARBITRAGE ANALYSIS ===")
        print(f"Fair ETF value: {fair_etf_cad:.4f} CAD")
        print(f"Market ETF value: {market_etf_cad:.4f} CAD")
        print(f"Deviation: {deviation:.4f} CAD ({deviation_pct:.2f}%)")

        # Trade only on significant deviations
        min_deviation_pct = 0.3  # 0.3% minimum deviation
        
        if deviation_pct > min_deviation_pct and within_limits():
            # Size based on deviation strength (smaller size for statistical arb)
            base_size = 300
            q = min(base_size, int(base_size * deviation_pct))
            
            print(f"Trade size: {q} shares")
            
            if deviation > 0:  # ETF undervalued relative to stocks
                print(f"✓ ETF UNDERVALUED - Buy ETF, Sell Stocks ({q} shares)")
                return execute_stat_arb_buy_etf(q, deviation)
                
            else:  # ETF overvalued relative to stocks  
                print(f"✓ ETF OVERVALUED - Sell ETF, Buy Stocks ({q} shares)")
                return execute_stat_arb_sell_etf(q, abs(deviation))
        else:
            print(f"✗ No statistical arbitrage opportunity")
            print(f"   Minimum deviation: {min_deviation_pct}%")
            return False
            
    except Exception as e:
        print(f"[ERROR] Statistical arbitrage analysis failed: {e}")
        return False

def execute_stat_arb_buy_etf(q, expected_profit_per_share):
    """Execute statistical arbitrage: Buy ETF, Sell Stocks"""
    try:
        print(f"--- STAT ARB: Buy ETF, Sell Stocks ---")
        
        # Simultaneous execution for statistical arbitrage
        bull_result = place_mkt(BULL, "SELL", q)
        bear_result = place_mkt(BEAR, "SELL", q) 
        
        if not bull_result or not bear_result:
            print("[ERROR] Failed to sell stocks")
            return False
            
        # Use stock proceeds to buy ETF
        stock_proceeds = (bull_result.get('vwap', 0) + bear_result.get('vwap', 0)) * q
        print(f"✓ Sold stocks for {stock_proceeds:.2f} CAD")
        
        # Buy USD for ETF purchase
        etf_price_usd = best_bid_ask(RITC)[1]
        usd_needed = etf_price_usd * q * 1.01
        
        fx_result = place_mkt(USD, "BUY", usd_needed)
        etf_result = place_mkt(RITC, "BUY", q)
        
        if fx_result and etf_result:
            usd_cost = fx_result.get('vwap', 1.35) * usd_needed
            print(f"✓ Bought {q} ETF for {usd_cost:.2f} CAD")
            
            actual_profit = stock_proceeds - usd_cost - q * 0.06  # Net fees
            expected_profit = expected_profit_per_share * q
            
            print(f"📊 Expected: {expected_profit:.2f} CAD, Actual: {actual_profit:.2f} CAD")
            return actual_profit > 0
        else:
            print("[ERROR] Failed to buy ETF")
            return False
            
    except Exception as e:
        print(f"[ERROR] Stat arb buy ETF failed: {e}")
        return False

def execute_stat_arb_sell_etf(q, expected_profit_per_share):
    """Execute statistical arbitrage: Sell ETF, Buy Stocks"""
    try:
        print(f"--- STAT ARB: Sell ETF, Buy Stocks ---")
        
        # Check if we have ETF position to sell (if not, skip this trade)
        positions = positions_map()
        if positions.get(RITC, 0) < q:
            print(f"[INFO] Insufficient RITC position ({positions.get(RITC, 0)}) for stat arb")
            return False
        
        # Sell ETF first
        etf_result = place_mkt(RITC, "SELL", q)
        if not etf_result:
            print("[ERROR] Failed to sell ETF")
            return False
            
        etf_proceeds_usd = etf_result.get('vwap', 0) * q
        print(f"✓ Sold {q} ETF for {etf_proceeds_usd:.2f} USD")
        
        # Convert USD to CAD
        fx_result = place_mkt(USD, "SELL", etf_proceeds_usd)
        if not fx_result:
            print("[ERROR] Failed to convert USD")
            return False
            
        cad_proceeds = fx_result.get('vwap', 1.35) * etf_proceeds_usd
        print(f"✓ Converted to {cad_proceeds:.2f} CAD")
        
        # Buy stocks with CAD proceeds
        stock_cost = (best_bid_ask(BULL)[1] + best_bid_ask(BEAR)[1]) * q
        
        if cad_proceeds > stock_cost:
            bull_result = place_mkt(BULL, "BUY", q)
            bear_result = place_mkt(BEAR, "BUY", q)
            
            if bull_result and bear_result:
                actual_cost = (bull_result.get('vwap', 0) + bear_result.get('vwap', 0)) * q
                actual_profit = cad_proceeds - actual_cost - q * 0.06  # Net fees
                expected_profit = expected_profit_per_share * q
                
                print(f"✓ Bought stocks for {actual_cost:.2f} CAD")
                print(f"📊 Expected: {expected_profit:.2f} CAD, Actual: {actual_profit:.2f} CAD")
                return actual_profit > 0
                
        print("[ERROR] Insufficient proceeds to buy stocks")
        return False
        
    except Exception as e:
        print(f"[ERROR] Stat arb sell ETF failed: {e}")
        return False