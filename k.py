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


# New evaluation function for Step 2
def evaluate_tender_profit(tender, usd, bull, bear, ritc):

    # TODO: The idea here will be -- evaulate cost (ETF) / individual + conv per bid / ask. 
    # Then rank them -- and calculate the expected payout till we reach the quantity. 

    # TODO: Think how you'll unwind this position. 


    t_start = time.time()
    action = tender['action']  # 'SELL' (you sell) or 'BUY' (you buy)
    p_tender = tender['price']  # USD
    q_tender = tender['quantity']

    ritc_asks , ritc_bids = ritc['asks'], ritc['bids']
    profits = [] 

    # i want to compute the direct profit at each bid and ask level. 

    if action == 'SELL':  # You sell RITC, go short
        for level in ritc_asks:
            profit = level['quantity'] * (p_tender - level['price'])
            profits.append({'type': 'E', 'level_price': level['price'], 'level_qty': level['quantity'], 'profit': profit / level['quantity'],'profit_with_q': profit})
    elif action == 'BUY':  # You buy RITC, go long, need to sell at bid levels
        for level in ritc_bids:
            profit = level['quantity'] * (level['price'] - p_tender)
            profits.append({'type': 'E', 'level_price': level['price'], 'level_qty': level['quantity'],  'profit': profit / level['quantity'], 'profit_with_q': profit})


    profits_stocks = [] 
    bull_asks , bull_bids = bull['asks'], bull['bids']
    bear_asks , bear_bids = bear['asks'], bear['bids']

    if action == 'SELL':
        for level_bull, level_bear in zip(bull_asks, bear_asks):
            q = min(level_bull['quantity'], level_bear['quantity']) # incorrect, ideally need to propogate down. 
            profit = q* (p_tender - (level_bull['price'] + level_bear['price'])) - CONVERTER_COST * q / 10000 # this should be per 10000.
            profits.append({'type': 'S',
                                   'level_price ': level_bull['price'] + level_bear['price'],
                                   'level_qty': q,
                                   'profit': profit / (q),
                                   'profit_with_q': profit})
            
    elif action == 'BUY':
        for level_bull, level_bear in zip(bull_bids, bear_bids):
            q = min(level_bull['quantity'], level_bear['quantity']) # incorrect, ideally need to propogate down. 
            profit = q* ((level_bull['price'] + level_bear['price'])  - p_tender) - CONVERTER_COST # this should be per 10000.
            profits.append({
                                'type': 'S',
                                   'level_price ': level_bull['price'] + level_bear['price'],
                                   'level_qty': q,
                                   'profit': profit / (q),
                                   'profit_with_q': profit})


    # print("Profits at each level via stocks, with the adjusted conversion cost")

    profits.sort(key=lambda x: x['profit'], reverse=True)

    net_profit = 0 
    q_left = q_tender 
    for p in profits:
        if q_left >= p['level_qty']:
            q_left -= p['level_qty']
            net_profit += p['level_qty'] * p['profit']
        else:
            q_left = 0 
            net_profit +=  q_left * p['profit']

    
    print("Profit:", net_profit, time.time() - t_start)

    # merge the 2 points 

    # threshold = q_tender * p_tender * usd_bid * PROFIT_THRESHOLD_PCT
    profitable = net_profit > 0

    return {
        'profitable': profitable,
        'profit': net_profit,
    }

# --------- CORE LOGIC ----------
def step_once():
    # Get executable prices (updated with depths)
    bull_bid, bull_ask, bull_bid_depth, bull_ask_depth = best_bid_ask(BULL)
    bear_bid, bear_ask, bear_bid_depth, bear_ask_depth = best_bid_ask(BEAR)
    ritc_bid_usd, ritc_ask_usd, ritc_bid_depth, ritc_ask_depth = best_bid_ask(RITC)
    usd_bid, usd_ask, _, _ = best_bid_ask(USD)   # USD quoted in CAD (USD/CAD)

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
        eval_result = evaluate_tender_profit(tender)

        print(f"Evaluated profit : {eval_result}")

        q_tender = tender['quantity']
        if eval_result['profitable'] :
            if accept_tender(tender):
                print(f"Accepted tender ID {tender['tender_id']}, profit {eval_result['profit_cad']:.2f} CAD, method {eval_result['unwind_method']}")
                unwind_tender_position(tender, eval_result)  # Trigger unwind
                unwinding_active = True
            else:
                print(f"Failed to accept tender ID {tender['tender_id']}")
        else:
            print(f"Rejected tender ID {tender['tender_id']}: Not profitable or limits exceeded")



    # traded = False
    
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

def unwind_tender_position(tender, eval_result):
    action = tender['action']
    q_left = tender['quantity']

    # Get fresh books
    ritc_book = best_bid_ask_entire_depth(RITC)
    bull_book = best_bid_ask_entire_depth(BULL)
    bear_book = best_bid_ask_entire_depth(BEAR)

    unwind_options = []

    # ETF unwind (direct)
    if action == 'SELL':  # You need to buy back RITC to close short
        for level in ritc_book['asks']:
            unwind_options.append({
                'type': 'ETF',
                'price': level['price'],
                'qty': level['quantity'],
                'action': 'BUY',
                'total_cost': level['price'] * level['quantity']
            })
    else:  # action == 'BUY', you need to sell RITC to close long
        for level in ritc_book['bids']:
            unwind_options.append({
                'type': 'ETF',
                'price': level['price'],
                'qty': level['quantity'],
                'action': 'SELL',
                'total_cost': -level['price'] * level['quantity']
            })

    # Stocks + converter unwind
    if action == 'SELL':
        # Need to buy BULL and BEAR, then convert to RITC
        bull_asks = bull_book['asks']
        bear_asks = bear_book['asks']
        for bull_level, bear_level in zip(bull_asks, bear_asks):
            qty = min(bull_level['quantity'], bear_level['quantity'], CONVERTER_BATCH)
            if qty <= 0:
                continue
            total_price = bull_level['price'] + bear_level['price']
            total_cost = qty * total_price + CONVERTER_COST * (qty / CONVERTER_BATCH)
            unwind_options.append({
                'type': 'CONVERT',
                'price': total_price,
                'qty': qty,
                'action': 'BUY',
                'total_cost': total_cost
            })
    else:
        # Need to sell BULL and BEAR, after redeeming RITC
        bull_bids = bull_book['bids']
        bear_bids = bear_book['bids']
        for bull_level, bear_level in zip(bull_bids, bear_bids):
            qty = min(bull_level['quantity'], bear_level['quantity'], CONVERTER_BATCH)
            if qty <= 0:
                continue
            total_price = bull_level['price'] + bear_level['price']
            total_cost = -qty * total_price + CONVERTER_COST * (qty / CONVERTER_BATCH)
            unwind_options.append({
                'type': 'CONVERT',
                'price': total_price,
                'qty': qty,
                'action': 'SELL',
                'total_cost': total_cost
            })

    # Sort by best (lowest) total_cost for BUY, highest for SELL
    if action == 'SELL':
        unwind_options.sort(key=lambda x: x['total_cost'])
    else:
        unwind_options.sort(key=lambda x: -x['total_cost'])

    # Execute orders in ranked order until q_left is zero
    convert_later = 0  

    for opt in unwind_options:
        if q_left <= 0:
            break
        qty = min(opt['qty'], q_left, MAX_SIZE_EQUITY)
        if qty <= 0:
            continue
        if opt['type'] == 'ETF':
            place_mkt(RITC, opt['action'], qty)
            print(f"Unwound {qty} RITC via ETF {opt['action']} at {opt['price']}")
        else:
            # Stocks + converter
            if opt['action'] == 'BUY':
                place_mkt(BULL, 'BUY', qty)
                place_mkt(BEAR, 'BUY', qty)
                convert_later += qty
                # print(f"Bought {qty} BULL & BEAR, then converted to RITC (manual step)")
            else:
                # print(f"Redeemed {qty} RITC, then selling stocks (manual step)")
                convert_later += qty
                place_mkt(BULL, 'SELL', qty)
                place_mkt(BEAR, 'SELL', qty)
        q_left -= qty

    
    print("[UPDATE] Conversion step pending for the qty", convert_later)

    if opt['action'] == 'BUY' and convert_later > 0:
        convert_bull_bear(convert_later)
        print(f"Converted {convert_later} BULL and BEAR via converter after buying stocks")


    elif opt['action'] == 'SELL' and convert_later > 0:
        convert_ritc(convert_later)
        print(f"Converted {convert_later} RITC via converter after redeeming RITC")

    print("Unwind complete")

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

def main():
    resp = open_leases()

    tick, status = get_tick_status()

    while status == "ACTIVE":
        # traded, e1, e2, info = 
        step_once()
        # Optional: print a lightweight heartbeat every 1s
        # print(f"tick={tick} e1={e1:.4f} e2={e2:.4f} ritc_ask_cad={info['ritc_ask_cad']:.4f}")
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
                    evaluate_tender_profit(data['tender'], data['usd'], data['bull'], data['bear'], data['ritc'])
                    

    

if __name__ == "__main__":
    # main()

    test_tender_code()



"""

25.62


bid start 25.74 25.68



9.86 9.77
16.18 16.13

"""