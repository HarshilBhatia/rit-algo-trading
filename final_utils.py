import os
import requests
from time import sleep
import numpy as np
import pickle
from tabulate import tabulate
import time
from rich import print

API = "http://localhost:9999/v1"
API_KEY = "PA83Q8EP"  # <-- your key
HDRS = {"X-API-key": API_KEY}  # change to X-API-Key if your server needs it
import datetime

# Tickers
CAD = "CAD"  # currency instrument quoted in CAD
USD = "USD"  # price of 1 USD in CAD (i.e., USD/CAD)
BULL = "BULL"  # stock in CAD
BEAR = "BEAR"  # stock in CAD
RITC = "RITC"  # ETF quoted in USD

# Per problem statement
FEE_MKT = 0.02  # $/share (market)
REBATE_LMT = 0.01  # $/share (passive) - not used in this baseline
MAX_SIZE_EQUITY = 10000  # per order for BULL/BEAR/RITC
MAX_SIZE_FX = 2500000  # per order for CAD/USD

# Basic risk guardrails (adjusted for better profitability)
MAX_LONG_NET = 200000
MAX_SHORT_NET = -200000
MAX_GROSS = 300000
ORDER_QTY = 5000  # child order size for arb legs

# IMPROVED: Dynamic threshold calculation instead of static
BASE_ARB_THRESHOLD_CAD = 0.04  # Reduced from 0.07 for better opportunity capture
MIN_TENDER_PROFIT_CAD = 1000  # Minimum tender profit (was -100000!)

# Enhanced constants for advanced strategies
PROFIT_THRESHOLD_PCT = 0.002  # 0.2% min profit (reduced from 0.5%)
CONVERTER_COST = 1500
CONVERTER_BATCH = 10000
IMPACT_FACTOR = 0.005  # Reduced impact factor for better execution
LIQUIDITY_THRESHOLD = 3000  # Reduced for more aggressive trading
VOLATILITY_WINDOW = 10  # Price observations for volatility calculation

# NEW: Advanced strategy parameters
VOLATILITY_MULTIPLIER = 2.0  # Volatility-based threshold adjustment
EXECUTION_DELAY = 0.1  # Seconds between execution chunks
MAX_SLIPPAGE_BPS = 20  # Maximum acceptable slippage in basis points

# --------- SESSION ----------
s = requests.Session()
s.headers.update(HDRS)

# NEW: Price history storage for volatility calculation
price_history = {BULL: [], BEAR: [], RITC: [], USD: []}

# --------- HELPERS ----------
def get_tick_status():
    r = s.get(f"{API}/case")
    r.raise_for_status()
    j = r.json()
    return j["tick"], j["status"]

def best_bid_ask(ticker):
    r = s.get(f"{API}/securities/book", params={"ticker": ticker})
    r.raise_for_status()
    book = r.json()
    bid = float(book["bids"][0]["price"]) if book["bids"] else 0.0
    ask = float(book["asks"][0]["price"]) if book["asks"] else 1e12
    bid_depth = int(book["bids"][0]["quantity"]) if book["bids"] else 0
    ask_depth = int(book["asks"][0]["quantity"]) if book["asks"] else 0
    
    # NEW: Store price for volatility calculation
    if bid > 0 and ask < 1e12:
        mid_price = (bid + ask) / 2
        price_history[ticker].append(mid_price)
        if len(price_history[ticker]) > VOLATILITY_WINDOW:
            price_history[ticker].pop(0)
    
    return bid, ask, bid_depth, ask_depth


def get_top_level_price_and_qty(ticker, action):
    """
    Returns the price and quantity at the top of the book for the given action.
    For 'SELL', returns best bid; for 'BUY', returns best ask.
    """
    # t = time.time() 
    book = best_bid_ask_entire_depth(ticker)
    # print(time.time() - t, 'exec time')
    if action == 'SELL':
        levels = book['bids']
    else:
        levels = book['asks']
    if not levels:
        return None, 0
    top = levels[0]
    return top['price'], top['quantity']
# ...existing code...


def best_bid_ask_entire_depth(ticker):
    r = s.get(f"{API}/securities/book", params={"ticker": ticker})
    r.raise_for_status()
    book = r.json()
    return book

# NEW: Advanced volatility calculation
def calculate_volatility(ticker):
    """Calculate rolling volatility for dynamic thresholding"""
    if len(price_history[ticker]) < 3:
        return 0.02  # Default volatility
    
    prices = np.array(price_history[ticker])
    returns = np.diff(prices) / prices[:-1]
    volatility = np.std(returns) if len(returns) > 0 else 0.02
    return max(0.001, volatility)  # Minimum volatility floor

# NEW: Dynamic arbitrage threshold calculation
def get_dynamic_arb_threshold():
    """Calculate volatility-adjusted arbitrage threshold"""
    bull_vol = calculate_volatility(BULL)
    bear_vol = calculate_volatility(BEAR)
    ritc_vol = calculate_volatility(RITC)
    
    avg_vol = (bull_vol + bear_vol + ritc_vol) / 3
    dynamic_threshold = BASE_ARB_THRESHOLD_CAD * (1 + VOLATILITY_MULTIPLIER * avg_vol)
    
    return max(BASE_ARB_THRESHOLD_CAD, min(0.15, dynamic_threshold))

# IMPROVED: Enhanced order book sweep that considers different depths
def calculate_sweep_cost_and_max_qty(ticker, action, desired_quantity):
    """Calculate sweep cost and determine maximum feasible quantity based on available liquidity"""
    book = best_bid_ask_entire_depth(ticker)
    levels = book['bids'] if action == 'SELL' else book['asks']
    
    if not levels:
        return float('inf'), 0
    
    total_cost = 0
    total_available = 0
    
    # Calculate total available liquidity and cumulative cost
    for level in levels:
        level_qty = level['quantity']
        level_price = level['price']
        
        if total_available + level_qty <= desired_quantity:
            # This entire level can be consumed
            total_cost += level_qty * level_price
            total_available += level_qty
        else:
            # Partial consumption of this level
            remaining_needed = desired_quantity - total_available
            total_cost += remaining_needed * level_price
            total_available += remaining_needed
            break
    
    if total_available == 0:
        return float('inf'), 0
        
    avg_price = total_cost / total_available
    return avg_price, total_available

# Legacy function for backward compatibility
def calculate_sweep_cost(ticker, action, quantity):
    """Legacy wrapper for backward compatibility"""
    avg_price, available = calculate_sweep_cost_and_max_qty(ticker, action, quantity)
    return avg_price, available

# NEW: Get maximum tradeable quantity across all paths
def get_max_feasible_quantities(action, desired_quantity):
    """Determine maximum feasible quantities for both ETF and Stock paths"""
    
    # ETF Path - check RITC liquidity
    if action == 'SELL':
        # We need to BUY back RITC
        _, etf_max_qty = calculate_sweep_cost_and_max_qty(RITC, 'BUY', desired_quantity)
    else:
        # We need to SELL RITC
        _, etf_max_qty = calculate_sweep_cost_and_max_qty(RITC, 'SELL', desired_quantity)
    
    # Stock Path - check BULL and BEAR liquidity (limited by the smaller one)
    if action == 'SELL':
        # We need to BUY back stocks
        _, bull_max_qty = calculate_sweep_cost_and_max_qty(BULL, 'BUY', desired_quantity)
        _, bear_max_qty = calculate_sweep_cost_and_max_qty(BEAR, 'BUY', desired_quantity)
    else:
        # We need to SELL stocks
        _, bull_max_qty = calculate_sweep_cost_and_max_qty(BULL, 'SELL', desired_quantity)
        _, bear_max_qty = calculate_sweep_cost_and_max_qty(BEAR, 'SELL', desired_quantity)
    
    stock_max_qty = min(bull_max_qty, bear_max_qty)
    
    return etf_max_qty, stock_max_qty

def get_order_book_depth(ticker):
    book = best_bid_ask_entire_depth(ticker)
    bid_depth = sum(level['quantity'] for level in book['bids'])  
    ask_depth = sum(level['quantity'] for level in book['asks'])
    return bid_depth, ask_depth

def get_tenders():
    r = s.get(f"{API}/tenders")
    r.raise_for_status()
    offers = r.json()
    ritc_tenders = [offer for offer in offers if offer.get('ticker') == RITC]
    return ritc_tenders

def get_usd_cad_spread():
    usd_bid, usd_ask, _, _ = best_bid_ask(USD)
    return usd_ask - usd_bid



def positions_map():
    r = s.get(f"{API}/securities")
    r.raise_for_status()
    out = {p["ticker"]: int(p.get("position", 0)) for p in r.json()}
    for k in (BULL, BEAR, RITC, USD, CAD):
        out.setdefault(k, 0)
    return out


def get_order_status(_id):
    return s.get(f"{API}/orders/{_id}")


def cancel_order(_id):
    return s.delete(f"{API}/orders/{_id}")

def get_position_limits_impact(projected_ritc_change=0, projected_bull_change=0, projected_bear_change=0):
    pos = positions_map()
    gross = abs(pos[BULL] + projected_bull_change) + abs(pos[BEAR] + projected_bear_change) + 2 * abs(pos[RITC] + projected_ritc_change)
    net = (pos[BULL] + projected_bull_change) + (pos[BEAR] + projected_bear_change) + 2 * (pos[RITC] + projected_ritc_change)


    return gross < MAX_GROSS and MAX_SHORT_NET < net < MAX_LONG_NET

# IMPROVED: Smart order placement with retry logic

def place_limit(ticker,action, qty, price):
    return s.post(f"{API}/orders",
                         params={"ticker": ticker, "type": "LIMIT",
                               "quantity": int(qty), "action": action, "price":price}).json()

def place_mkt(ticker, action, qty):
    """Enhanced market order placement with error handling"""
    if qty <= 0:
        return {'vwap': 0}
        
    max_retries = 3
    for attempt in range(max_retries):
        try:
            order = s.post(f"{API}/orders",
                         params={"ticker": ticker, "type": "MARKET",
                               "quantity": int(qty), "action": action})
            
            if order.ok:
                return order.json()
            else:
                print(f"[WARNING] Order attempt {attempt+1} failed: {order.text}")
                if attempt < max_retries - 1:
                    sleep(0.1)
                    
        except Exception as e:
            print(f"[ERROR] Exception in order placement: {e}")
            if attempt < max_retries - 1:
                sleep(0.1)
    
    print(f"[ERROR] All order attempts failed: {ticker} {action} {qty}")
    return {'vwap': 0}

def within_limits():
    pos = positions_map()
    gross = abs(pos[BULL]) + abs(pos[BEAR]) + 2 * abs(pos[RITC])  # FIXED: Include RITC multiplier
    net = pos[BULL] + pos[BEAR] + 2 * pos[RITC]
    return (gross < MAX_GROSS) and (MAX_SHORT_NET < net < MAX_LONG_NET)

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

# IMPROVED: Smart FX hedging with chunking
def fx_hedge(action, qty):
    """Enhanced FX hedging with optimal execution"""
    if qty <= 0:
        return
        
    base_qty = qty
    chunk_size = min(MAX_SIZE_FX, qty)
    
    while qty > 0:
        current_chunk = min(chunk_size, qty)
        place_mkt(USD, action, current_chunk)
        qty -= current_chunk
        if qty > 0:
            sleep(EXECUTION_DELAY)  # Brief pause to avoid market impact
    
    print(f"Hedged FX: {action} {abs(base_qty):.2f} USD")

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
            sleep(2)
            leases = get_leases()
        self.init_paths(leases)

    def convert_ritc(self, qty_ritc, itr=0):
        if qty_ritc == 0:  # FIXED: was qty instead of qty_ritc
            return None
        endpoint = f"{API}/leases/{self.redemption_id}"
        resp = s.post(endpoint, params={"from1": "RITC", "quantity1": int(qty_ritc), 
                                      "from2": "USD", "quantity2": int(1500*qty_ritc // 10000)})
        if not resp.ok:
            print(f"[RETRY]", end=' ')
            if itr < 10:
                sleep(1.5)
                return self.convert_ritc(qty_ritc, itr + 1)  # FIXED: added return
        return resp

    def convert_bull_bear(self, qty, itr=0):
        if qty == 0:
            return None
        endpoint = f"{API}/leases/{self.creation_id}"
        resp = s.post(endpoint, params={"from1": "BULL", "quantity1": int(qty), 
                                      "from2": "BEAR", "quantity2": int(qty), 
                                      "from3": "USD", "quantity3": int(1500*qty // 10000)})
        if not resp.ok:
            print(f"[RETRY]", end=' ')
            if itr < 10:
                sleep(1.5)
                return self.convert_bull_bear(qty, itr + 1)  # FIXED: added return
        return resp




# def _conversion_fee(self, qty):
#     return 1500 * (qty / CONVERTER_BATCH)

if __name__ == '__main__':
    print(get_position_limits_impact(85000))
