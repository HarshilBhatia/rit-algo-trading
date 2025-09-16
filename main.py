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

API = "http://localhost:9990/v1"

API_KEY = "PA83Q8EP"                     # <-- your key
HDRS = {"X-API-key": API_KEY}          # change to X-API-Key if your server needs it
import datetime

# Tickers
CAD  = "CAD"    # currency instrument quoted in CAD
USD  = "USD"    # price of 1 USD in CAD (i.e., USD/CAD)
BULL = "BULL"   # stock in CAD
BEAR = "BEAR"   # stock in CAD
RITC = "RITC"   # ETF quoted in USD

# Per problem statement
FEE_MKT = 0.02           # $/share (market)
REBATE_LMT = 0.01        # $/share (passive) - not used in this baseline
MAX_SIZE_EQUITY = 10000 # per order for BULL/BEAR/RITC
MAX_SIZE_FX = 2500000  # per order for CAD/USD

# Basic risk guardrails (adjust as needed)
MAX_LONG_NET  = 25000
MAX_SHORT_NET = -25000
MAX_GROSS     = 500000
ORDER_QTY     = 10000    # child order size for arb legs

# Cushion to beat fees & slippage.
# 3 legs with market orders => ~0.06 CAD/sh cost; add a bit more for safety.
ARB_THRESHOLD_CAD = 0.07

# New constants for tender handling
PROFIT_THRESHOLD_PCT = 0.005  # 0.5% min profit
CONVERTER_COST = 1500
CONVERTER_BATCH = 10000
IMPACT_FACTOR = 0.01  # $0.01 per 1k shares beyond depth
LIQUIDITY_THRESHOLD = 5000  # min depth for direct trades


tender_ids_eval = set() 


# --------- SESSION ----------
s = requests.Session()
s.headers.update(HDRS)


# New evaluation function for Step 2

# --------- CORE LOGIC ----------
def step_once():
    # Get executable prices (updated with depths)
    bull_bid, bull_ask, bull_bid_depth, bull_ask_depth = best_bid_ask(BULL)
    bear_bid, bear_ask, bear_bid_depth, bear_ask_depth = best_bid_ask(BEAR)
    ritc_bid_usd, ritc_ask_usd, ritc_bid_depth, ritc_ask_depth = best_bid_ask(RITC)
    usd_bid, usd_ask, _, _ = best_bid_ask(USD)   # USD quoted in CAD (USD/CAD)


    bull = best_bid_ask_entire_depth(BULL)
    bear = best_bid_ask_entire_depth(BEAR)
    ritc  = best_bid_ask_entire_depth(RITC)
    usd = best_bid_ask_entire_depth(USD)   

    # Convert RITC to CAD using USD book
    ritc_bid_cad = ritc_bid_usd * usd_bid
    ritc_ask_cad = ritc_ask_usd * usd_ask

    # Basket executable values in CAD
    basket_sell_value = bull_bid + bear_bid      # what we get if we SELL basket now
    basket_buy_cost   = bull_ask + bear_ask      # what we pay if we BUY basket now

    # Direction 1: Basket rich vs ETF
    # SELL basket (hit bids), BUY RITC in USD (lift ask) -> compare in CAD
    edge1 = basket_sell_value - ritc_ask_cad

    # Direction 2: ETF rich vs Basket
    # SELL RITC (hit bid in USD), BUY basket (lift asks) -> compare in CAD
    edge2 = ritc_bid_cad - basket_buy_cost
    
    # Tender handling
    tenders = get_tenders()
    unwinding_active = False  # Flag for later
    for tender in tenders:  # Prioritize by profit? Sort if multiple

        if tender['tender_id'] in tender_ids_eval:
            continue
        
        tender_ids_eval.add(tender['tender_id'])

        eval_result = tender.evaluate_tender_profit(tender, usd, bull,bear, ritc)

        print(tender)
        print(f"Evaluated profit : {eval_result}")

        q_tender = tender['quantity']
        if eval_result['profitable'] :
            if accept_tender(tender):
                print(f"Accepted tender ID {tender['tender_id']}, profit {eval_result['profit']:.2f}")
                tender.unwind_tender_position(tender, eval_result)  # Trigger unwind
                unwinding_active = True
            else:
                print(f"Failed to accept tender ID {tender['tender_id']}")
        else:
            print(f"Rejected tender ID {tender['tender_id']}: Not profitable")

    traded = False

    
    # check_conversion_arbitrage()

    # if not unwinding_active:  # Proceed with arb if not unwinding
    #     if edge1 >= ARB_THRESHOLD_CAD and within_limits():
    #         # Basket rich: sell BULL & BEAR, buy RITC
    #         q = min(ORDER_QTY, MAX_SIZE_EQUITY)
    #         place_mkt(BULL, "SELL", q)
    #         place_mkt(BEAR, "SELL", q)
    #         place_mkt(RITC, "BUY",  q)
    #         traded = True

    #     elif edge2 >= ARB_THRESHOLD_CAD and within_limits():
    #         # ETF rich: buy BULL & BEAR, sell RITC
    #         q = min(ORDER_QTY, MAX_SIZE_EQUITY)
    #         place_mkt(BULL, "BUY",  q)
    #         place_mkt(BEAR, "BUY",  q)
    #         place_mkt(RITC, "SELL", q)
    #         traded = True

    # return traded, edge1, edge2, {
    #     "bull_bid": bull_bid, "bull_ask": bull_ask,
    #     "bear_bid": bear_bid, "bear_ask": bear_ask,
    #     "ritc_bid_usd": ritc_bid_usd, "ritc_ask_usd": ritc_ask_usd,
    #     "usd_bid": usd_bid, "usd_ask": usd_ask,
    #     "ritc_bid_cad": ritc_bid_cad, "ritc_ask_cad": ritc_ask_cad
    # }

# New unwind function for Step 4

# New FX hedge function
def hedge_fx(exposure_usd):
    if exposure_usd == 0:
        return
    action = "BUY" if exposure_usd > 0 else "SELL"
    qty = abs(exposure_usd)  # Adjust units if needed (API may require integers)
    child_qty = min(MAX_SIZE_FX, qty)
    while qty > 0:
        place_mkt(USD, action, child_qty)
        qty -= child_qty
    print(f"Hedged FX: {action} {abs(exposure_usd)} USD")

def check_conversion_arbitrage():
    # Get best prices
    bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
    bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
    ritc_bid_usd, ritc_ask_usd, _, _ = best_bid_ask(RITC)
    usd_bid, usd_ask, _, _ = best_bid_ask(USD)

    # Convert ETF prices to CAD

    q = ORDER_QTY

    # Direction 1: Convert basket to ETF (buy basket, convert, sell ETF)
    basket_cost = basket_to_etf_value(bull_ask, bear_ask, q) #  bought 
    etf_proceeds = ritc_bid_usd * q #
    profit1 = etf_proceeds - basket_cost # USD 
    # need to hedge FX

    # Direction 2: Convert ETF to basket (buy ETF, convert, sell basket)
    etf_cost = etf_to_basket_value(ritc_ask_usd, q) # 
    basket_proceeds = (bull_bid + bear_bid) * q
    profit2 = basket_proceeds - etf_cost  # CAD
    # need to hedge FD

    
    # Place trades if profitable
    if profit1 > 2000 and within_limits():
        # Buy basket, convert, sell ETF
        print(f"Basket→ETF profit: {profit1:.2f} for {q} shares")

        place_mkt(BULL, "BUY", q)
        place_mkt(BEAR, "BUY", q)
        # Conversion simulated here; in real system, call conversion API
        # print(out.json())
        place_mkt(RITC, "SELL", q)
        out = convert_bull_bear(q)

        print("[ARBITRAGE] Basket -> ETF")
        # exit()


    elif profit2 > 2000 and within_limits():
        # Buy ETF, convert, sell basket
        print(f"ETF→Basket profit: {profit2:.2f} CAD for {q} shares")

        place_mkt(RITC, "BUY", q)
        # Conversion simulated here; in real system, call conversion API
        print(out.json())
        place_mkt(BULL, "SELL", q)
        place_mkt(BEAR, "SELL", q)

        out = convert_ritc(q)

        print("[ARBITRAGE] ETF -> Basket")
        # exit()

# Example usage in main loop:
def main():
    resp = open_leases()
    tick, status = get_tick_status()
    while status == "ACTIVE":
        check_conversion_arbitrage()
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
                    tenders.evaluate_tender_profit(data['tender'], data['usd'], data['bull'], data['bear'], data['ritc'])
                    

    

if __name__ == "__main__":
    # main()

    main()



"""

25.62


bid start 25.74 25.68
I want you to implement the following--

whenever im buying the bull / bear or RITC then converting and then selling, there is FX risk because bull / bear are in CAD while RITC is in USD.

So i need you to hedge the currently whenever we buy / sell because the conversion takes 1-2s to execute.


9.86 9.77
16.18 16.13

"""