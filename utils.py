import os 
import requests
from time import sleep
import numpy as np
import pickle 
from tabulate import tabulate
import time 


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
    order  =  s.post(f"{API}/orders",
                  params={"ticker": ticker, "type": "MARKET",
                          "quantity": int(qty), "action": action})

    print(order.json())
    return order.json()

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

def open_leases():
    try:
        resp = s.post(f"{API}/leases", params={"ticker": "ETF-Creation"})
        if not resp.ok:
            print(f"[ERROR] Failed to open ETF-Creation lease: {resp.status_code} {resp.text}")
        resp = s.post(f"{API}/leases", params={"ticker": "ETF-Redemption"})
        if not resp.ok:
            print(f"[ERROR] Failed to open ETF-Redemption lease: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[EXCEPTION] Exception in open_leases: {e}")

    print("[SUCCESS] Leases opened")



def conversion_cost(q):
    """Returns the conversion fee for q shares."""
    return 1500 * q / 10000

def basket_to_etf_value(bull_price, bear_price, q):
    """Total cost to convert basket to ETF for q shares."""
    return (bull_price + bear_price) * q + conversion_cost(q)

def etf_to_basket_value(etf_price, q):
    """Total cost to convert ETF to basket for q shares."""
    return etf_price * q + conversion_cost(q)


def get_leases():
    return s.get(f"{API}/leases")



class Converter():

    def __init__(self):
        self.creation_id = None
        self.redemption_id = None
        self.initialize_leases()
    
    def init_paths(self, leases):
        for lease in leases.json():
            if lease['ticker'] == 'ETF-Creation':
                self.creation_id = lease['id']
            elif lease['ticker'] == 'ETF-Redemption':
                self.redemption_id = lease['id']  


    def initialize_leases(self):
        leases = get_leases()

        if len(leases.json()) == 0:
            open_leases()
            sleep(2)  # Give some time for the leases to be established
        
        leases = get_leases()
        self.init_paths(leases)

        print("Current leases:", leases.json())

        
    def convert_ritc(self,qty_ritc):

        endpoint = f"{API}/leases/{self.redemption_id}"
        resp = s.post(endpoint, params = {"from1": "RITC", "quantity1": int(qty_ritc), "from2":"USD", "quantity2": int(1500*qty_ritc // 10000)})
        if not resp.ok:
            print(f"[ERROR] Failed to open ETF-Creation lease: {resp.status_code} {resp.text}")

        return resp

    def convert_bull_bear(self, qty):

        endpoint = f"{API}/leases/{self.creation_id}"
        resp = s.post(endpoint, params = {"from1": "BULL", "quantity1": int(qty), "from2":"BEAR", "quantity2": int(qty), "from3":"USD", "quantity3": int(1500*qty // 10000)})
        if not resp.ok:
            print(f"[ERROR] Failed to open ETF-Redemption lease: {resp.status_code} {resp.text}")
        
        return resp 
