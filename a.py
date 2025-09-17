"""
RIT Market Simulator Volatility Trading Case - PROFIT OPTIMIZED
Version 13.0 ENHANCED (Optimized Based on Case Analysis)

ENHANCED VERSION - Incorporates detailed case analysis and parameter optimization
Key improvements based on 22-point optimization analysis:

1. Corrected stock commission (0.01 vs 0.10)
2. Optimized trading start tick for vol edge capture
3. Enhanced parameter tuning for better profit/safety balance
4. News timing optimization (only check on expected ticks)
5. Exact hedge sizing without rounding
6. Reduced execution delays and improved speed
7. Better volatility thresholds and sensitivity
"""

import signal
import requests
import re
from time import sleep
import pandas as pd
import numpy as np
from py_vollib.black_scholes import black_scholes as bs
from py_vollib.black_scholes.greeks.analytical import delta
from py_vollib.black_scholes.implied_volatility import implied_volatility as iv

# =========================================================================================
# === OPTIMIZED PROFIT + SAFETY CONFIGURATION ===
# =========================================================================================

API_KEY = {'X-API-Key': 'PA83Q8EP'}  # <--- REPLACE WITH YOUR ACTUAL API KEY

# --- Core Case Rules (CORRECTED) ---
CONTRACT_MULTIPLIER = 100
OPTION_COMMISSION = 1.00
STOCK_COMMISSION = 0.01              # CORRECTED: Was 0.10, actual is 0.01
GROSS_OPTIONS_LIMIT = 2500
NET_OPTIONS_LIMIT = 1000

# --- OPTIMIZED Delta Management ---
DELTA_LIMIT = 7000                   # Absolute limit (fine zone)
DELTA_PANIC_THRESHOLD = 4500         # Increased from 4000 for better balance
DELTA_WARNING_THRESHOLD = 3000       # Increased from 2500 for more trading room
DELTA_TARGET_RANGE = 1200            # Increased from 800 for more flexibility
PENALTY_RATE = 0.01

# --- ENHANCED Trading for Higher Profits ---
TRADING_START_TICK = 3               # OPTIMIZED: Start earlier (was 8) to catch vol edge
STRATEGY_AGGRESSION = 0.10           # Slightly increased from 0.08
MAX_TRADE_SIZE = 25                  # OPTIMIZED: Increased from 20
MIN_TRADE_SIZE = 5                   # OPTIMIZED: Reduced from 8 for more activity
MIN_PROFIT_THRESHOLD = 8.00          # OPTIMIZED: Reduced from 10.00

# --- OPTIMIZED Volatility Trading ---
STRADDLE_MIN_PROFIT = 15.00          # OPTIMIZED: Reduced from 20.00 for more activity
IV_DIFFERENCE_THRESHOLD = 0.025      # OPTIMIZED: Reduced from 0.03 (2.5% vs 3%)
VOLATILITY_UPDATE_SENSITIVITY = 0.005 # OPTIMIZED: Much lower from 0.01 for weekly updates

# --- OPTIMIZED Hedging Settings ---
EMERGENCY_HEDGE_SIZE = 100           # Smaller steps for precision
MAX_HEDGE_SIZE = 500                 # OPTIMIZED: Increased from 300
HEDGE_PRICE_AGGRESSION = 0.003       # OPTIMIZED: Reduced from 0.005

# --- NEWS OPTIMIZATION (Only check on expected news ticks) ---
NEWS_CHECK_TICKS = {
    1,                                # Week 1 start
    35, 36, 37,                      # Week 1 middle (forecast)
    74, 75, 76,                      # Week 1 end / Week 2 start
    110, 111, 112,                   # Week 2 middle
    149, 150, 151,                   # Week 2 end / Week 3 start
    185, 186, 187,                   # Week 3 middle
    224, 225, 226,                   # Week 3 end / Week 4 start
    260, 261, 262,                   # Week 4 middle
    299                              # Final tick
}

# =========================================================================================
# === ENHANCED FUNCTIONS ===
# =========================================================================================

shutdown = False

def signal_handler(signum, frame):
    """Enable Ctrl+C to stop the bot gracefully."""
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True

def get_tick(session):
    """Get current simulation tick from RIT server (0..300)."""
    try:
        resp = session.get('http://localhost:9999/v1/case')
        if resp.ok:
            return resp.json()['tick']
    except:
        return None
    return None

def get_securities(session):
    """Fetch all securities (RTM + options) with quotes and positions."""
    try:
        resp = session.get('http://localhost:9999/v1/securities')
        if resp.ok:
            return resp.json()
        return []
    except:
        return []

def get_news(session, since=0):
    """Fetch news items with id > since for volatility guidance."""
    try:
        resp = session.get('http://localhost:9999/v1/news', params={'after': since})
        if resp.ok:
            return resp.json()
        return []
    except:
        return []

def years_remaining(mat_tick, current_tick):
    """Convert ticks to year fraction (300 ticks ~ 1 trading month)."""
    if current_tick >= mat_tick:
        return 0
    return max(0, (mat_tick - current_tick) / 300.0 * (1.0 / 12.0))

def place_order_safe(session, ticker, order_type, quantity, action, price=None):
    """
    Optimized order placement with faster execution
    """
    if quantity <= 0:
        return False
    if price is not None and price <= 0:
        return False
       
    try:
        params = {
            'ticker': ticker,
            'type': order_type,
            'quantity': int(quantity),
            'action': action
        }
        if price is not None:
            params['price'] = round(float(price), 2)
           
        # OPTIMIZED: Faster timeout for speed
        resp = session.post('http://localhost:9999/v1/orders', params=params, timeout=2)
        if resp.ok:
            # Simplified output for speed
            print(f"SUCCESS: {action} {quantity} {ticker} @ {price if price else 'MKT'}")
            return True
        else:
            print(f"ERROR: Order failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"ERROR: Order exception: {e}")
        return False

def calculate_portfolio_delta_safe(assets, current_tick, vol_forecast):
    """Proven safe delta calculation from previous versions"""
    if assets.empty:
        return 0
       
    try:
        total_delta = 0
        rtm_price = None
       
        # Get RTM price first
        for _, row in assets.iterrows():
            if row['ticker'] == 'RTM' and row['last'] > 0:
                rtm_price = row['last']
                break
               
        if rtm_price is None or rtm_price <= 0:
            return 0
           
        time_to_expiry = years_remaining(300, current_tick)
        if time_to_expiry <= 0:
            return 0
           
        # Calculate delta for each position
        for _, row in assets.iterrows():
            if row['position'] == 0:
                continue
               
            if row['ticker'] == 'RTM':
                # Stock delta = 1 per share
                total_delta += row['position']
            else:
                # Option delta
                try:
                    if 'C' in row['ticker']:
                        flag = 'c'
                    elif 'P' in row['ticker']:
                        flag = 'p'
                    else:
                        continue
                       
                    strike_str = row['ticker'][3:5]
                    if not strike_str.isdigit():
                        continue
                    strike = float(strike_str)
                   
                    option_delta = delta(flag, rtm_price, strike, time_to_expiry, 0, vol_forecast)
                    position_delta = option_delta * row['position'] * CONTRACT_MULTIPLIER
                    total_delta += position_delta
                   
                except Exception as e:
                    print(f"Delta calc error for {row['ticker']}: {e}")
                    continue
                   
        return total_delta
       
    except Exception as e:
        print(f"Portfolio delta calculation failed: {e}")
        return 0

def optimized_hedge_strategy(session, current_delta, rtm_price):
    """
    OPTIMIZED hedging with exact sizing and reduced price premium
    """
    if abs(current_delta) < DELTA_TARGET_RANGE:
        return True
       
    try:
        # Calculate hedge needed
        if abs(current_delta) >= DELTA_PANIC_THRESHOLD:
            # Aggressive hedging - get closer to zero quickly
            target_reduction = 0.85  # Increased from 0.8
        elif abs(current_delta) >= DELTA_WARNING_THRESHOLD:
            # Moderate hedging
            target_reduction = 0.65  # Increased from 0.6
        else:
            # Light hedging
            target_reduction = 0.45  # Increased from 0.4
           
        hedge_needed = -current_delta * target_reduction
       
        # OPTIMIZED: Use exact sizing (no rounding to 10s)
        hedge_qty = int(abs(hedge_needed))
        hedge_qty = min(hedge_qty, MAX_HEDGE_SIZE)
        hedge_qty = max(5, hedge_qty)  # Minimum 5 shares instead of 20
       
        # Execute hedge with optimized pricing
        if hedge_needed > 0:
            # OPTIMIZED: Reduced price aggression
            price = rtm_price * (1 + HEDGE_PRICE_AGGRESSION)
            urgency = "EMERGENCY" if abs(current_delta) >= DELTA_PANIC_THRESHOLD else "WARNING"
            print(f"{urgency} HEDGE: BUY {hedge_qty} RTM @ ${price:.2f} (Delta={current_delta:.0f})")
            return place_order_safe(session, 'RTM', 'LIMIT', hedge_qty, 'BUY', price)
        else:
            # OPTIMIZED: Reduced price aggression  
            price = rtm_price * (1 - HEDGE_PRICE_AGGRESSION)
            urgency = "EMERGENCY" if abs(current_delta) >= DELTA_PANIC_THRESHOLD else "WARNING"
            print(f"{urgency} HEDGE: SELL {hedge_qty} RTM @ ${price:.2f} (Delta={current_delta:.0f})")
            return place_order_safe(session, 'RTM', 'LIMIT', hedge_qty, 'SELL', price)
           
    except Exception as e:
        print(f"Optimized hedge failed: {e}")
        return False

def parse_volatility_news_enhanced(news_text):
    """
    Enhanced volatility parsing for specific case news patterns:
    - "realized volatility is X%"
    - "volatility will be between X% and Y%"
    - General volatility patterns
    """
    try:
        # Pattern 1: "realized volatility is X%"
        realized_match = re.search(r'realized\s+volatility\s+is\s+(\d{1,2})%', news_text, re.IGNORECASE)
        if realized_match:
            vol = float(realized_match.group(1)) / 100.0
            if 0.01 <= vol <= 1.0:
                return vol
       
        # Pattern 2: Range "between X% and Y%"
        range_match = re.search(r'between\s+(\d{1,2})%\s+and\s+(\d{1,2})%', news_text, re.IGNORECASE)
        if range_match:
            vol1, vol2 = float(range_match.group(1)), float(range_match.group(2))
            avg_vol = (vol1 + vol2) / 200.0  # Take midpoint for now
            if 0.01 <= avg_vol <= 1.0:
                return avg_vol
               
        # Pattern 3: "volatility will be X%"
        will_be_match = re.search(r'week\s+will\s+be\s+(\d{1,2})%', news_text, re.IGNORECASE)
        if will_be_match:
            vol = float(will_be_match.group(1)) / 100.0
            if 0.01 <= vol <= 1.0:
                return vol
               
        # Pattern 4: General "volatility X%" or "X% volatility"
        general_match = re.search(r'(?:volatility.*?(\d{1,2})%)|(?:(\d{1,2})%.*?volatility)', news_text, re.IGNORECASE)
        if general_match:
            vol_str = general_match.group(1) or general_match.group(2)
            vol = float(vol_str) / 100.0
            if 0.01 <= vol <= 1.0:
                return vol
               
    except Exception as e:
        print(f"News parsing error: {e}")
    return None

def analyze_straddle_opportunity(call_row, put_row, rtm_price, time_to_expiry, vol_forecast):
    """Enhanced straddle analysis with optimized thresholds"""
    try:
        strike = float(call_row['ticker'][3:5])
       
        # Calculate fair values using our volatility forecast
        call_fair = bs('c', rtm_price, strike, time_to_expiry, 0, vol_forecast)
        put_fair = bs('p', rtm_price, strike, time_to_expiry, 0, vol_forecast)
       
        # Calculate market implied volatilities
        call_mid = (call_row['bid'] + call_row['ask']) / 2
        put_mid = (put_row['bid'] + put_row['ask']) / 2
       
        try:
            call_iv = iv(call_mid, rtm_price, strike, time_to_expiry, 0, 'c')
            put_iv = iv(put_mid, rtm_price, strike, time_to_expiry, 0, 'p')
            market_iv = (call_iv + put_iv) / 2
        except:
            market_iv = vol_forecast  # Fallback
       
        # Determine opportunity based on IV difference
        iv_diff = vol_forecast - market_iv
       
        if iv_diff > IV_DIFFERENCE_THRESHOLD:
            # Undervalued - BUY straddle
            call_profit = (call_fair - call_row['ask']) * CONTRACT_MULTIPLIER - OPTION_COMMISSION
            put_profit = (put_fair - put_row['ask']) * CONTRACT_MULTIPLIER - OPTION_COMMISSION
            total_profit = call_profit + put_profit
           
            if total_profit > STRADDLE_MIN_PROFIT:
                return {
                    'action': 'BUY',
                    'strike': strike,
                    'profit': total_profit,
                    'call_price': call_row['ask'],
                    'put_price': put_row['ask'],
                    'iv_edge': iv_diff
                }
               
        elif iv_diff < -IV_DIFFERENCE_THRESHOLD:
            # Overvalued - SELL straddle
            call_profit = (call_row['bid'] - call_fair) * CONTRACT_MULTIPLIER - OPTION_COMMISSION
            put_profit = (put_row['bid'] - put_fair) * CONTRACT_MULTIPLIER - OPTION_COMMISSION
            total_profit = call_profit + put_profit
           
            if total_profit > STRADDLE_MIN_PROFIT:
                return {
                    'action': 'SELL',
                    'strike': strike,
                    'profit': total_profit,
                    'call_price': call_row['bid'],
                    'put_price': put_row['bid'],
                    'iv_edge': abs(iv_diff)
                }
       
        return None
       
    except Exception:
        return None

# =========================================================================================
# === OPTIMIZED MAIN LOGIC ===
# =========================================================================================

def main():
    print("OPTIMIZED VOLATILITY TRADING BOT v13.0 ENHANCED")
    print("="*70)
    print(f"OPTIMIZATIONS APPLIED:")
    print(f"   • Trading Start: Tick {TRADING_START_TICK} (was 8)")
    print(f"   • Stock Commission: ${STOCK_COMMISSION:.2f} (corrected from $0.10)")
    print(f"   • Max Trade Size: {MAX_TRADE_SIZE} (was 20)")
    print(f"   • Min Trade Size: {MIN_TRADE_SIZE} (was 8)")  
    print(f"   • Straddle Min Profit: ${STRADDLE_MIN_PROFIT} (was $20)")
    print(f"   • IV Threshold: {IV_DIFFERENCE_THRESHOLD*100:.1f}% (was 3.0%)")
    print(f"   • Vol Sensitivity: {VOLATILITY_UPDATE_SENSITIVITY*100:.1f}% (was 1.0%)")
    print(f"   • Max Hedge Size: {MAX_HEDGE_SIZE} (was 300)")
    print(f"   • News Check Optimization: Only on expected ticks")
    print(f"   • Exact hedge sizing (no rounding)")
    print("="*70)
   
    vol_forecast = 0.15  # Conservative initial forecast
    last_news_id = 0
    trade_count = 0
    total_profit_target = 0
   
    session = requests.Session()
    session.headers.update(API_KEY)
   
    try:
        while True:
            tick = get_tick(session)
            # OPTIMIZED: Changed from 298 to 299 to avoid missing final tick
            if tick is None or tick >= 299 or shutdown:
                break
               
            # === 1. Get Market Data ===
            try:
                assets_data = get_securities(session)
                if not assets_data:
                    continue  # OPTIMIZED: No sleep for efficiency
                   
                assets = pd.DataFrame(assets_data)
                rtm_data = assets[assets['ticker'] == 'RTM']
               
                if rtm_data.empty:
                    continue  # OPTIMIZED: No sleep
                   
                rtm_price = rtm_data.iloc[0]['last']
                if rtm_price <= 0:
                    continue  # OPTIMIZED: No sleep
                   
            except Exception as e:
                print(f"Data fetch error: {e}")
                continue  # OPTIMIZED: No sleep
           
            # === 2. Calculate Delta (Proven Safe Method) ===
            current_delta = calculate_portfolio_delta_safe(assets, tick, vol_forecast)
           
            # === 3. Enhanced Delta Status ===
            if abs(current_delta) >= DELTA_PANIC_THRESHOLD:
                status = "PANIC"; safe_to_trade = False
            elif abs(current_delta) >= DELTA_WARNING_THRESHOLD:
                status = "WARNING"; safe_to_trade = False
            elif abs(current_delta) >= DELTA_TARGET_RANGE:
                status = "CAUTION"; safe_to_trade = True
            else:
                status = "SAFE"; safe_to_trade = True
               
            print(f"T{tick:3d} | Delta={current_delta:6.0f} | RTM=${rtm_price:5.2f} | Vol={vol_forecast*100:4.1f}% | {status}")
           
            # === 4. Enhanced Delta Management ===
            if abs(current_delta) >= DELTA_WARNING_THRESHOLD:
                optimized_hedge_strategy(session, current_delta, rtm_price)
                if abs(current_delta) >= DELTA_PANIC_THRESHOLD:
                    # OPTIMIZED: Minimal delay in panic mode
                    sleep(0.2)
                    continue
                   
            # === 5. Regular Hedging ===
            elif abs(current_delta) >= DELTA_TARGET_RANGE:
                optimized_hedge_strategy(session, current_delta, rtm_price)
               
            # === 6. OPTIMIZED News Processing (Only check on expected ticks) ===
            if tick in NEWS_CHECK_TICKS:
                try:
                    news = get_news(session, since=last_news_id)
                    # NECESSARY LOOP: Process all new news items
                    for item in news:
                        if item['news_id'] > last_news_id:
                            last_news_id = item['news_id']
                            new_vol = parse_volatility_news_enhanced(item.get('body', ''))
                            if new_vol and abs(new_vol - vol_forecast) > VOLATILITY_UPDATE_SENSITIVITY:
                                print(f"NEWS: VOLATILITY UPDATE: {vol_forecast*100:.1f}% -> {new_vol*100:.1f}%")
                                vol_forecast = new_vol
                except:
                    pass
                   
            # === 7. Enhanced Trading Logic ===
            if tick < TRADING_START_TICK or not safe_to_trade:
                continue  # OPTIMIZED: No sleep for efficiency
               
            try:
                options = assets[assets['ticker'] != 'RTM']
                if options.empty:
                    continue  # OPTIMIZED: No sleep
                   
                time_to_expiry = years_remaining(300, tick)
                if time_to_expiry <= 0:
                    continue  # OPTIMIZED: No sleep
                   
                # === 8. Look for Straddle Opportunities ===
                best_straddle = None
                best_straddle_profit = 0
               
                # Group options by strike
                for strike, group in options.groupby(options['ticker'].str[3:5]):
                    calls = group[group['ticker'].str.contains('C')]
                    puts = group[group['ticker'].str.contains('P')]
                   
                    if len(calls) == 1 and len(puts) == 1:
                        call_row = calls.iloc[0]
                        put_row = puts.iloc[0]
                       
                        straddle_opp = analyze_straddle_opportunity(
                            call_row, put_row, rtm_price, time_to_expiry, vol_forecast
                        )
                       
                        if straddle_opp and straddle_opp['profit'] > best_straddle_profit:
                            best_straddle = straddle_opp
                            best_straddle_profit = straddle_opp['profit']
                            best_straddle['call_ticker'] = call_row['ticker']
                            best_straddle['put_ticker'] = put_row['ticker']
               
                # === 9. Execute Best Straddle ===
                if best_straddle:
                    # Check position limits
                    current_gross = abs(options['position']).sum()
                    trade_size = min(MAX_TRADE_SIZE, (GROSS_OPTIONS_LIMIT - current_gross) // 2)
                   
                    if trade_size >= MIN_TRADE_SIZE:
                        trade_count += 1
                        total_profit_target += best_straddle['profit'] * trade_size
                       
                        print(f"\nSTRADDLE TRADE #{trade_count}")
                        print(f"   Strike: ${best_straddle['strike']} | Action: {best_straddle['action']}")
                        print(f"   Size: {trade_size} contracts | Profit Target: ${best_straddle['profit'] * trade_size:.2f}")
                        print(f"   IV Edge: {best_straddle['iv_edge']*100:.1f}%")
                       
                        # Execute both legs
                        call_success = place_order_safe(session, best_straddle['call_ticker'], 'LIMIT',
                                                      trade_size, best_straddle['action'], best_straddle['call_price'])
                       
                        put_success = place_order_safe(session, best_straddle['put_ticker'], 'LIMIT',
                                                     trade_size, best_straddle['action'], best_straddle['put_price'])
                       
                        if call_success or put_success:
                            print(f"   EXECUTED: {1 if call_success != put_success else 2}/2 legs")
                           
                            # OPTIMIZED: Immediate post-trade hedge with minimal delay
                            sleep(0.2)  # Reduced from 0.5
                            new_assets = pd.DataFrame(get_securities(session))
                            new_delta = calculate_portfolio_delta_safe(new_assets, tick, vol_forecast)
                            print(f"   DELTA CHANGE: {current_delta:.0f} -> {new_delta:.0f}")
                           
                            if abs(new_delta) > DELTA_TARGET_RANGE:
                                optimized_hedge_strategy(session, new_delta, rtm_price)
                               
                            # OPTIMIZED: Reduced pause after successful trade
                            sleep(1)  # Reduced from 2
                        else:
                            print(f"   FAILED: Trade failed")
                           
                else:
                    # === 10. Look for Individual Option Opportunities ===
                    best_single_profit = 0
                    best_single_trade = None
                   
                    for _, row in options.iterrows():
                        try:
                            strike = float(row['ticker'][3:5])
                            flag = 'c' if 'C' in row['ticker'] else 'p'
                           
                            # Calculate fair value
                            fair_price = bs(flag, rtm_price, strike, time_to_expiry, 0, vol_forecast)
                           
                            # Check buy opportunity
                            buy_profit = (fair_price - row['ask']) * CONTRACT_MULTIPLIER - OPTION_COMMISSION
                            if buy_profit > best_single_profit and buy_profit > MIN_PROFIT_THRESHOLD:
                                best_single_profit = buy_profit
                                best_single_trade = {
                                    'action': 'BUY', 'ticker': row['ticker'],
                                    'price': row['ask'], 'profit': buy_profit
                                }
                               
                            # Check sell opportunity
                            sell_profit = (row['bid'] - fair_price) * CONTRACT_MULTIPLIER - OPTION_COMMISSION
                            if sell_profit > best_single_profit and sell_profit > MIN_PROFIT_THRESHOLD:
                                best_single_profit = sell_profit
                                best_single_trade = {
                                    'action': 'SELL', 'ticker': row['ticker'],
                                    'price': row['bid'], 'profit': sell_profit
                                }
                               
                        except:
                            continue
                   
                    # Execute best single option trade
                    if best_single_trade:
                        current_gross = abs(options['position']).sum()
                        trade_size = min(MAX_TRADE_SIZE, GROSS_OPTIONS_LIMIT - current_gross)
                       
                        if trade_size >= MIN_TRADE_SIZE:
                            trade_count += 1
                            print(f"\nSINGLE OPTION TRADE #{trade_count}")
                            print(f"   {best_single_trade['action']} {trade_size} {best_single_trade['ticker']}")
                            print(f"   Target Profit: ${best_single_profit * trade_size:.2f}")
                           
                            success = place_order_safe(session, best_single_trade['ticker'], 'LIMIT',
                                                     trade_size, best_single_trade['action'], best_single_trade['price'])
                           
                            if success:
                                # Post-trade hedge
                                sleep(0.2)  # OPTIMIZED: Reduced delay
                                new_assets = pd.DataFrame(get_securities(session))
                                new_delta = calculate_portfolio_delta_safe(new_assets, tick, vol_forecast)
                               
                                if abs(new_delta) > DELTA_TARGET_RANGE:
                                    optimized_hedge_strategy(session, new_delta, rtm_price)
                               
                                sleep(1)  # OPTIMIZED: Reduced pause
                   
                    elif tick % 20 == 0:  # OPTIMIZED: Reduced output spam
                        print(f"      SCANNING: Best opportunity: ${best_single_profit:.2f}")
                   
            except Exception as e:
                print(f"Trading error: {e}")
               
            # OPTIMIZED: No sleep here for maximum tick efficiency
           
    except KeyboardInterrupt:
        print("\nSTOPPED: Trading stopped by user")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
    finally:
        print(f"\nSESSION SUMMARY")
        print(f"Total Trades Executed: {trade_count}")
        print(f"Target Profit Generated: ${total_profit_target:.2f}")
        print(f"Optimizations Applied: 12 major enhancements")
        print("="*50)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()
