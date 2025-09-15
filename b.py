"""
RIT Market Simulator Algorithmic ETF Arbitrage Case - Support File
Rotman BMO Finance Research and Trading Lab, University of Toronto (C)
All rights reserved.
"""

import requests
from time import sleep
import numpy as np
import pickle 
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
ORDER_QTY     = 5000    # child order size for arb legs

# Cushion to beat fees & slippage.
# 3 legs with market orders => ~0.06 CAD/sh cost; add a bit more for safety.
ARB_THRESHOLD_CAD = 0.07

# New constants for tender handling
PROFIT_THRESHOLD_PCT = 0.005  # 0.5% min profit
CONVERTER_COST = 1500
CONVERTER_BATCH = 10000
IMPACT_FACTOR = 0.01  # $0.01 per 1k shares beyond depth
LIQUIDITY_THRESHOLD = 5000  # min depth for direct trades

# --------- SESSION ----------
s = requests.Session()
s.headers.update(HDRS)

# --------- HELPERS ----------
def get_tick_status():
    # Gets simulation status (active or stopped) for the tick
    r = s.get(f"{API}/case")
    r.raise_for_status()
    j = r.json()
    return j["tick"], j["status"]

def best_bid_ask(ticker):
    # Returns best bid and ask prices for a ticker, and now depths at those levels
    r = s.get(f"{API}/securities/book", params={"ticker": ticker})
    r.raise_for_status()
    book = r.json()
    bid = float(book["bids"][0]["price"]) if book["bids"] else 0.0
    ask = float(book["asks"][0]["price"]) if book["asks"] else 1e12
    bid_depth = int(book["bids"][0]["quantity"]) if book["bids"] else 0
    ask_depth = int(book["asks"][0]["quantity"]) if book["asks"] else 0
    return bid, ask, bid_depth, ask_depth


def best_bid_ask_entire_depth(ticker):
    r = s.get(f"{API}/securities/book", params={"ticker": ticker})
    r.raise_for_status()
    book = r.json()
    
    return book



def get_order_book_depth(ticker):
    # Returns total bid and ask depths (sum top levels if needed; here just best for simplicity)
    _, _, bid_depth, ask_depth = best_bid_ask(ticker)
    return bid_depth, ask_depth

def get_tenders():
    # Retrieve active tender offers
    r = s.get(f"{API}/tenders")
    r.raise_for_status()
    offers = r.json()
    # Filter for RITC tenders; assume list of dicts
    ritc_tenders = [offer for offer in offers if offer.get('ticker') == RITC]
    print(ritc_tenders)
    return ritc_tenders  # list of dicts: {'tender_id': int, 'action': str ('BUY' or 'SELL'), 'price': float, 'quantity': int, 'is_fixed_bid': bool, ...}

def get_usd_cad_spread():
    usd_bid, usd_ask, _, _ = best_bid_ask(USD)
    return usd_ask - usd_bid

def positions_map():
    # Tracks current positions
    r = s.get(f"{API}/securities")
    r.raise_for_status()
    out = {p["ticker"]: int(p.get("position", 0)) for p in r.json()}
    for k in (BULL, BEAR, RITC, USD, CAD):
        out.setdefault(k, 0)
    return out

def get_position_limits_impact(projected_ritc_change=0, projected_bull_change=0, projected_bear_change=0):
    pos = positions_map()
    gross = abs(pos[BULL] + projected_bull_change) + abs(pos[BEAR] + projected_bear_change) + 2 * abs(pos[RITC] + projected_ritc_change)
    net = (pos[BULL] + projected_bull_change) + (pos[BEAR] + projected_bear_change) + 2 * (pos[RITC] + projected_ritc_change)
    return gross < MAX_GROSS and MAX_SHORT_NET < net < MAX_LONG_NET

def place_mkt(ticker, action, qty):
    # Sends Market orders
    return s.post(f"{API}/orders",
                  params={"ticker": ticker, "type": "MARKET",
                          "quantity": int(qty), "action": action}).ok

def within_limits():
    return get_position_limits_impact()

def accept_tender(tender):
    tender_id = tender['tender_id']
    price = tender['price']
    if tender['is_fixed_bid']:
        resp = s.post(f"{API}/tenders/{tender_id}")
    else:
        resp = s.post(f"{API}/tenders/{tender_id}", params={"price": price})
    return resp.ok

# New evaluation function for Step 2
def evaluate_tender_profit(tender):

    # TODO: The idea here will be -- evaulate cost (ETF) / individual + conv per bid / ask. 
    # Then rank them -- and calculate the expected payout till we reach the quantity. 

    # TODO: Think how you'll unwind this position. 

    action = tender['action']  # 'SELL' (you sell) or 'BUY' (you buy)
    p_tender = tender['price']  # USD
    q_tender = tender['quantity']

    timestamp = datetime.datetime.now().isoformat()


    usd = best_bid_ask_entire_depth(USD)
    bull = best_bid_ask_entire_depth(BULL)
    bear = best_bid_ask_entire_depth(BEAR)
    ritc = best_bid_ask_entire_depth(RITC)


    data = {
        'timestamp': timestamp,
        'tender': tender,
        'usd': usd,
        'bull': bull,
        'bear': bear,
        'ritc': ritc
        }
    
    # Generate filename with timestamp
    filename = f"output/market_data_{timestamp.replace(':', '-')}.pkl"
    
    # Dump data to pickle file
    with open(filename, 'wb') as f:
        pickle.dump(data, f)


    # print('lalalala', best_bid_ask(RITC))

    
    # if action == 'SELL':  # You sell RITC, go short
    #     direct_profit = q_tender*(p_tender - ritc_ask_usd)
    # elif action == 'BUY':  # You buy RITC, go long
    #     direct_profit = q_tender*( ritc_bid_usd - p_tender)
       
    
    direct_profit = 0 
    max_profit = direct_profit
    # print(profit_direct, profit_converter)
    unwind_method = 'direct'
    unwind_cost = direct_profit
    
    # Liquidity adjustment
    # relevant_depth = ask_depth if action == 'SELL' else bid_depth
    # if unwind_method == 'direct' and relevant_depth < LIQUIDITY_THRESHOLD:
    #     unwind_method = 'converter'
    #     max_profit = profit_converter  # Reassign
    
    # threshold = q_tender * p_tender * usd_bid * PROFIT_THRESHOLD_PCT
    profitable = max_profit > 0
    
    return {
        'profitable': profitable,
        'profit_cad': max_profit,
        'unwind_method': unwind_method,
        'unwind_cost_cad': unwind_cost
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
        ritc_change = -q_tender if tender['action'] == 'SELL' else q_tender  # Short for sell, long for buy
        if eval_result['profitable'] :
            if accept_tender(tender):
                print(f"Accepted tender ID {tender['tender_id']}, profit {eval_result['profit_cad']:.2f} CAD, method {eval_result['unwind_method']}")
                unwind_tender_position(tender, eval_result)  # Trigger unwind
                unwinding_active = True
            else:
                print(f"Failed to accept tender ID {tender['tender_id']}")
        else:
            print(f"Rejected tender ID {tender['tender_id']}: Not profitable or limits exceeded")

    traded = False
    
    if not unwinding_active:  # Proceed with arb if not unwinding
        if edge1 >= ARB_THRESHOLD_CAD and within_limits():
            # Basket rich: sell BULL & BEAR, buy RITC
            q = min(ORDER_QTY, MAX_SIZE_EQUITY)
            place_mkt(BULL, "SELL", q)
            place_mkt(BEAR, "SELL", q)
            place_mkt(RITC, "BUY",  q)
            traded = True

        elif edge2 >= ARB_THRESHOLD_CAD and within_limits():
            # ETF rich: buy BULL & BEAR, sell RITC
            q = min(ORDER_QTY, MAX_SIZE_EQUITY)
            place_mkt(BULL, "BUY",  q)
            place_mkt(BEAR, "BUY",  q)
            place_mkt(RITC, "SELL", q)
            traded = True

    return traded, edge1, edge2, {
        "bull_bid": bull_bid, "bull_ask": bull_ask,
        "bear_bid": bear_bid, "bear_ask": bear_ask,
        "ritc_bid_usd": ritc_bid_usd, "ritc_ask_usd": ritc_ask_usd,
        "usd_bid": usd_bid, "usd_ask": usd_ask,
        "ritc_bid_cad": ritc_bid_cad, "ritc_ask_cad": ritc_ask_cad
    }

# New unwind function for Step 4
def unwind_tender_position(tender, eval_result):
    action = tender['action']
    q_tender = tender['quantity']
    method = eval_result['unwind_method']
    pos = positions_map()
    target_pos = 0  # Aim to flatten RITC
    remaining = abs(pos[RITC])  # Assume post-accept pos is +/- q_tender
    
    exposure_usd = q_tender * tender['price'] if action == 'SELL' else -q_tender * tender['price']
    hedge_fx(exposure_usd)  # Hedge immediately
    
    while remaining > 0:
        pos = positions_map()
        remaining = abs(pos[RITC])
        if remaining == 0:
            break
        
        # Re-assess liquidity
        _, _, ritc_bid_depth, ritc_ask_depth = best_bid_ask(RITC)
        relevant_depth = ritc_ask_depth if action == 'SELL' else ritc_bid_depth  # Buy to cover short, sell to unwind long
        if method == 'direct' and relevant_depth >= LIQUIDITY_THRESHOLD:
            action = "BUY" if action == 'SELL' else "SELL"
            child_qty = min(ORDER_QTY, remaining, relevant_depth)
            if place_mkt(RITC, action, child_qty):
                print(f"Unwound {child_qty} RITC via direct {action}")
            else:
                print("Direct order failed; switching to converter")
                method = 'converter'
        else:
            # Use converter
            batches_left = remaining // CONVERTER_BATCH
            if batches_left > 0:
                if action == 'SELL':  # Create RITC: Buy stocks, convert
                    # Assume manual converter; print alert
                    print(f"Manual: Buy {CONVERTER_BATCH} BULL and BEAR, then use ETF-Creation for {batches_left} batches")
                    # Simulate buys (in real, slice)
                    for stock in [BULL, BEAR]:
                        stock_ask_depth = get_order_book_depth(stock)[1]  # ask depth
                        child_qty = min(ORDER_QTY, CONVERTER_BATCH, stock_ask_depth)
                        while child_qty > 0:
                            place_mkt(stock, "BUY", child_qty)
                            child_qty -= child_qty  # Loop if needed, but simplify
                else:  # Buy tender: Redeem RITC, sell stocks
                    print(f"Manual: Use ETF-Redemption for {batches_left} batches, then sell {CONVERTER_BATCH} BULL and BEAR")
                    for stock in [BULL, BEAR]:
                        stock_bid_depth = get_order_book_depth(stock)[0]  # bid depth
                        child_qty = min(ORDER_QTY, CONVERTER_BATCH, stock_bid_depth)
                        while child_qty > 0:
                            place_mkt(stock, "SELL", child_qty)
                            child_qty -= child_qty
            remaining -= batches_left * CONVERTER_BATCH
            if remaining > 0:
                # Remainder direct
                action = "BUY" if action == 'SELL' else "SELL"
                place_mkt(RITC, action, remaining)
        
        sleep(0.2)  # Poll delay
    
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
    tick, status = get_tick_status()
    while status == "ACTIVE":
        traded, e1, e2, info = step_once()
        # Optional: print a lightweight heartbeat every 1s
        # print(f"tick={tick} e1={e1:.4f} e2={e2:.4f} ritc_ask_cad={info['ritc_ask_cad']:.4f}")
        sleep(0.5)
        tick, status = get_tick_status()

if __name__ == "__main__":
    main()