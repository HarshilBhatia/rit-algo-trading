"""
RIT Market Simulator Algorithmic ETF Arbitrage Case - Support File
Rotman BMO Finance Research and Trading Lab, University of Toronto (C)
All rights reserved.
"""
import os 
import requests
from time import sleep
import numpy as np
import pickle 
from tabulate import tabulate
import time 
import tender
from utils import *
from etf_arb import check_conversion_arbitrage
'''
If you are not familiar with Python or feeling a little bit rusty, highly recommend you to go through the following link:
    https://github.com/trekhleb/learn-python

If you have any question about REST APIs and outputs of code please read:
    https://realpython.com/api-integration-in-python/#http-methods
    https://rit.306w.ca/RIT-REST-API/1.0.3/?port=9999&key=Rotman#/

So bascially：
The core of this case is to design algorithmic trading strategies that exploit arbitrage opportunities between the ETF (RITC) 
and its underlying stocks (BULL and BEAR), while effectively using tender offers and conversion tools to avoid speculative risk
and maximize returns.
'''



tender_ids_eval = set() 


# --------- SESSION ----------
s = requests.Session()
s.headers.update(HDRS)


# New evaluation function for Step 2

# --------- CORE LOGIC ----------
def step_once():

    bull = best_bid_ask_entire_depth(BULL)
    bear = best_bid_ask_entire_depth(BEAR)
    ritc  = best_bid_ask_entire_depth(RITC)
    usd = best_bid_ask_entire_depth(USD)   

    # Tender handling
    tenders = get_tenders()
    unwinding_active = False  # Flag for later
    for tender in tenders:  # Prioritize by profit? Sort if multiple
        exit()

        if tender['tender_id'] in tender_ids_eval:
            continue
        
        tender_ids_eval.add(tender['tender_id'])

        eval_result = tender.evaluate_tender_profit(tender, usd, bull, bear, ritc)

        print(f"Evaluated profit : {eval_result}")

        if eval_result['profitable'] :
            if tender.accept_and_hedge_tender(tender):
                print(f"Accepted tender ID {tender['tender_id']}, profit {eval_result['profit']:.2f}")
                tender.unwind_tender_position(tender, eval_result)  # Trigger unwind
            else:
                print(f"Failed to accept tender ID {tender['tender_id']}")
        else:
            print(f"Rejected tender ID {tender['tender_id']}: Not profitable")



# New unwind function for Step 4

# New FX hedge function
def hedge_fx(exposure_usd):
    if exposure_usd == 0:
        return
    action = "BUY" if exposure_usd > 0 else "SELL"
    qty = abs(exposure_usd)  # Adjust units if needed (API may require integers)
    child_qty = min(MAX_SIZE_FX, qty)
    while qty > 0:
        out = place_mkt(USD, action, child_qty)
        print(out)
        qty -= child_qty
    print(f"Hedged FX: {action} {abs(exposure_usd)} USD")

# Example usage in main loop:
def main():
    # resp = open_leases()
    tick, status = get_tick_status()
    converter = Converter() # initializes the leases
    
    while status == "ACTIVE":
        check_conversion_arbitrage(converter)
        step_once()
        sleep(0.5)
        tick, status = get_tick_status()


def test_tender_code():
    

    # Iterate through all files in the directory
    for root, _, files in os.walk('output/'):
        for file in files:
            # Check if the file has a .pkl or .pickle extension
            if file.endswith(('.pkl', '.pickle')):
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
                    tender.evaluate_tender_profit(data['tender'], data['usd'], data['bull'], data['bear'], data['ritc'])
                    print(data['tender'])
                    

    

if __name__ == "__main__":
    main()

    # test_tender_code()



"""

25.62


bid start 25.74 25.68


9.86 9.77
16.18 16.13

"""