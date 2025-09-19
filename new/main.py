# FIXED MAIN TRADING LOOP
# Integration of fixed arbitrage and tender modules with proper error handling

import os
import requests
from time import sleep
import numpy as np
import pickle
from tabulate import tabulate
import time

from final_utils import *

# Import the fixed modules
from tender_eval import check_tender
from fixed_arbitrage import check_conversion_arbitrage_fixed, statistical_arbitrage_fixed

def enhanced_position_monitoring():
    """Enhanced position monitoring with detailed reporting"""
    positions = positions_map()
    
    print(f"\n=== POSITION MONITOR ===")
    
    # Calculate position metrics
    bull_pos = positions.get(BULL, 0)
    bear_pos = positions.get(BEAR, 0) 
    ritc_pos = positions.get(RITC, 0)
    usd_pos = positions.get(USD, 0)
    cad_pos = positions.get(CAD, 0)
    
    # Calculate limits
    gross_exposure = abs(bull_pos) + abs(bear_pos) + 2 * abs(ritc_pos)
    net_exposure = bull_pos + bear_pos + 2 * ritc_pos
    
    # print(f"Positions: BULL={bull_pos}, BEAR={bear_pos}, RITC={ritc_pos}")
    # print(f"FX: USD={usd_pos:.2f}, CAD={cad_pos:.2f}")
    # print(f"Gross: {gross_exposure}/{MAX_GROSS} ({gross_exposure/MAX_GROSS*100:.1f}%)")
    # print(f"Net: {net_exposure} (limits: {MAX_SHORT_NET} to {MAX_LONG_NET})")
    
    # Risk warnings
    risk_level = "LOW"
    if gross_exposure > MAX_GROSS * 0.7:
        risk_level = "MEDIUM"
    if gross_exposure > MAX_GROSS * 0.9:
        risk_level = "HIGH"
        
    # print(f"Risk Level: {risk_level}")
    
    return {
        'positions': positions,
        'gross': gross_exposure,
        'net': net_exposure,
        'risk_level': risk_level,
        'within_limits': within_limits()
    }

def emergency_position_flatten():
    """Emergency position flattening with comprehensive cleanup"""
    print("\n[EMERGENCY] Flattening all positions...")
    
    positions = positions_map()
    
    # Flatten positions in order of liquidity
    for ticker in [RITC, BULL, BEAR, USD]:
        pos = positions.get(ticker, 0)
        if abs(pos) > 0:
            action = "SELL" if pos > 0 else "BUY"
            
            # Use smaller chunks for emergency flattening
            chunk_size = min(abs(pos), 1000)
            remaining = abs(pos)
            
            while remaining > 0:
                current_chunk = min(chunk_size, remaining)
                result = place_mkt(ticker, action, current_chunk)
                
                if result:
                    print(f"✓ Emergency {action}: {current_chunk} {ticker}")
                    remaining -= current_chunk
                else:
                    print(f"✗ Failed emergency {action}: {current_chunk} {ticker}")
                    break
                
                sleep(0.2)
    
    print("[EMERGENCY] Position flattening complete")

def comprehensive_health_check():
    """Comprehensive system health check"""
    try:
        # Test API connectivity
        tick, status = get_tick_status()
        
        # Test market data availability
        test_tickers = [BULL, BEAR, RITC, USD]
        market_health = True
        
        for ticker in test_tickers:
            bid, ask, _, _ = best_bid_ask(ticker)
            if bid <= 0 or ask >= 1e12:
                print(f"[WARNING] Poor market data for {ticker}")
                market_health = False
        
        # Test position access
        positions = positions_map()
        
        # Test converter access (if possible)
        converter_health = True
        try:
            leases = get_leases()
            if leases.status_code != 200:
                converter_health = False
        except:
            converter_health = False
            
        health_report = {
            'api_status': status,
            'market_health': market_health, 
            'position_access': len(positions) >= 0,
            'converter_health': converter_health
        }
        
        overall_health = all(health_report.values())
        
        print(f"=== HEALTH CHECK ===")
        print(f"API Status: {status}")
        print(f"Market Data: {'✓' if market_health else '✗'}")
        print(f"Position Access: {'✓' if health_report['position_access'] else '✗'}")
        print(f"Converter: {'✓' if converter_health else '✗'}")
        print(f"Overall: {'HEALTHY' if overall_health else 'ISSUES'}")
        
        return overall_health
        
    except Exception as e:
        print(f"[ERROR] Health check failed: {e}")
        return False

def adaptive_strategy_selection(positions, market_conditions):
    """Select trading strategy based on positions and market conditions"""
    
    # Check current exposure levels
    gross = positions['gross']
    risk_level = positions['risk_level']
    
    # Strategy selection logic
    strategies = []
    
    # Conservative approach if high risk
    if risk_level == "HIGH":
        print("[STRATEGY] HIGH RISK - Focus on position reduction")
        strategies = ['emergency_flatten'] 
        
    elif risk_level == "MEDIUM":
        print("[STRATEGY] MEDIUM RISK - Limited arbitrage only")
        strategies = ['statistical_arb']
        
    else:  # LOW risk
        print("[STRATEGY] LOW RISK - Full strategy suite")
        strategies = ['conversion_arb', 'tender_eval', 'statistical_arb']
    
    return strategies

def main_fixed():
    """FIXED: Main trading loop with comprehensive error handling and monitoring"""
    
    print("=== FIXED ALGORITHMIC ETF ARBITRAGE SYSTEM ===")
    print("Features: Complete Position Unwinding + Fixed Currency Conversion + Robust Error Handling")
    
    # Initial health check
    if not comprehensive_health_check():
        print("[ERROR] System health check failed - aborting")
        return
    
    # Initialize converter
    try:
        converter = Converter()
        print("✓ Converter initialized")
    except Exception as e:
        print(f"[ERROR] Converter initialization failed: {e}")
        return
    
    # Initial position report
    # positions_status = enhanced_position_monitoring()
    
    # Main trading loop
    loop_count = 0
    last_health_check = time.time()
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    tick, status = get_tick_status()
    
    while status == "ACTIVE" and consecutive_errors < max_consecutive_errors:
        loop_count += 1
        current_time = time.time()
        check_tender(converter)
        tick, status = get_tick_status()
        sleep(0.5)
        
        # try:
            # Periodic health check
            # if current_time - last_health_check > 60:  # Every minute
            #     if not comprehensive_health_check():
            #         print("[WARNING] Health check failed")
            #         consecutive_errors += 1
            #         sleep(5)
            #         continue
            #     else:
            #         consecutive_errors = 0  # Reset error counter on success
            #     last_health_check = current_time
            
            # # Enhanced position monitoring 
            # positions_status = enhanced_position_monitoring()
            
            # # Emergency position management
            # if not positions_status['within_limits']:
            #     print("[ALERT] Position limits exceeded!")
            #     emergency_position_flatten()
            #     sleep(2)
            #     tick, status = get_tick_status()
            #     continue
            
            # # Adaptive strategy selection
            # # strategies = adaptive_strategy_selection(positions_status, {})
            # strategies = 'tender_eval'

            # check_tender(converter)
            
            # Execute selected strategies
            # for strategy in strategies:
            #     if strategy == 'conversion_arb':
            #         print(f"\n--- Strategy: Conversion Arbitrage ---")
            #         try:
            #             check_conversion_arbitrage_fixed(converter)
            #         except Exception as e:
            #             print(f"[ERROR] Conversion arbitrage failed: {e}")
                        
            #     elif strategy == 'statistical_arb':
            #         print(f"\n--- Strategy: Statistical Arbitrage ---") 
            #         try:
            #             statistical_arbitrage_fixed()
            #         except Exception as e:
            #             print(f"[ERROR] Statistical arbitrage failed: {e}")
                        
            #     elif strategy == 'tender_eval':
            #         print(f"\n--- Strategy: Tender Evaluation ---")
            #         try:
            #             check_tender(converter)
            #         except Exception as e:
            #             print(f"[ERROR] Tender evaluation failed: {e}")
                        
            #     elif strategy == 'emergency_flatten':
            #         emergency_position_flatten()
                
            #     # Brief pause between strategies
            #     sleep(0.5)
            
            # Adaptive sleep based on market activity and risk level
            # base_sleep = 1.0
            
            # if positions_status['risk_level'] == "HIGH":
            #     sleep_duration = base_sleep * 3  # Slower when high risk
            # elif positions_status['risk_level'] == "MEDIUM": 
            #     sleep_duration = base_sleep * 2  # Moderate pace
            # else:
            #     sleep_duration = base_sleep  # Normal pace
                
            # sleep(sleep_duration)
            
            # # Update status
            # tick, status = get_tick_status()
            
            # # Reset error counter on successful loop
            # consecutive_errors = 0
            
        # except KeyboardInterrupt:
        #     print("\n[INTERRUPT] Graceful shutdown initiated...")
        #     emergency_position_flatten()
        #     break
            
        # except Exception as e:
        #     consecutive_errors += 1
        #     print(f"[ERROR] Main loop exception ({consecutive_errors}/{max_consecutive_errors}): {e}")
            
        #     if consecutive_errors >= max_consecutive_errors:
        #         print("[CRITICAL] Too many consecutive errors - emergency shutdown")
        #         emergency_position_flatten()
        #         break
                
        #     sleep(2)
        #     tick, status = get_tick_status()
    
    # Final cleanup and reporting
    print(f"\n=== TRADING SESSION COMPLETE ===")
    print(f"Total loops: {loop_count}")
    print(f"Final status: {status}")
    
    final_positions = enhanced_position_monitoring()
    
    if any(abs(pos) > 1 for pos in final_positions['positions'].values()):
        print("[WARNING] Non-zero positions remaining")
        emergency_position_flatten()
    else:
        print("✓ All positions flat")
    
    print("=== SYSTEM SHUTDOWN COMPLETE ===")

if __name__ == "__main__":
    main_fixed()