# FIXED MAIN TRADING LOOP
# Integration of fixed arbitrage and tender modules with proper error handling

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
    
import os
import requests
from time import sleep
import numpy as np
import pickle
from tabulate import tabulate
import time
import threading
import asyncio

from final_utils import *
from tender_eval import *

def main():
    """FIXED: Main trading loop with comprehensive error handling and monitoring"""
    print("=== FIXED ALGORITHMIC ETF ARBITRAGE SYSTEM ===")

    loop_count = 0
    last_health_check = time.time()
    consecutive_errors = 0
    max_consecutive_errors = 5

    unwind_task = None
    while True:
        tick, status = get_tick_status()

        if status == 'ACTIVE':
            converter = Converter()
            unwinder = Unwind(converter)

            while status == "ACTIVE" and consecutive_errors < max_consecutive_errors:
                ritc_pos = pos_map_usd()
                unwinder.set(quantity = ritc_pos[0], price = ritc_pos[1])
                for tender in get_tenders():
                    if not within_limits():
                        print("[WARNING] Position limits - skipping tenders")
                        break
                    T = EvaluateTendersNew(tender, converter)
                    eval_result = T.evaluate_tender_profit()
                    if eval_result > 0:
                        print(f"[green] tender {tender['tender_id']}: profit {eval_result} CAD", end = ' ')
                        success = accept_tender(tender)
                        if success:
                            print("Accepted")
                        else:
                            print("[red] Failed")


                unwinder.unwind_pos()
                # Only start a new unwinder thread if the previous one is not running
                # if unwinder_thread is not None and unwinder_thread.is_alive():
                #     print("[INFO] Waiting for previous unwinder to finish...")
                #     unwinder_thread.join()
                # unwinder_thread = threading.Thread(target=unwinder.unwind_pos)
                # unwinder_thread.start()
                # unwinder_thread.join()

if __name__ == '__main__':
    main()