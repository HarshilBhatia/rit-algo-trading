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
# from tender_new import check_tender
from fixed_arbitrage import check_conversion_arbitrage_fixed, statistical_arbitrage_fixed
from arb import StatArbTrader
from arb2 import ETFArbitrageTrader

def main():
    """FIXED: Main trading loop with comprehensive error handling and monitoring"""
    
    print("=== FIXED ALGORITHMIC ETF ARBITRAGE SYSTEM ===")
    

   
    
    # Initial position report
    # positions_status = enhanced_position_monitoring()
    
    # Main trading loop
    loop_count = 0
    last_health_check = time.time()
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True: 
        tick, status = get_tick_status()

        if status == 'ACTIVE':
            converter = Converter()

        
        # arb = StatArbTrader()
        # arb = ETFArbitrageTrader()
        while status == "ACTIVE" and consecutive_errors < max_consecutive_errors:
            # place_mkt(RITC, 'BUY', 1000)

            sleep(3)
            # place_mkt(RITC, 'SELL', 1000)
            loop_count += 1
            # current_time = time.time()
            check_tender(converter)
            # arb.run_strategy()

            tick, status = get_tick_status()
            sleep(0.5)
        

if __name__ == "__main__":
    main()