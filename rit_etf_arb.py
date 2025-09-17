# RIT Algorithmic ETF Arbitrage Case - Complete Solution
# Rotman BMO Finance Research and Trading Lab, University of Toronto (C)
# Enhanced version with comprehensive arbitrage strategies

import os
import requests
from time import sleep
import numpy as np
import pandas as pd
from tabulate import tabulate
import time
from collections import defaultdict
import threading
import queue

# =========================================================================================
# === CONFIGURATION AND CONSTANTS ===
# =========================================================================================

# API Configuration
API = "http://localhost:9999/v1"
API_KEY = "PA83Q8EP"  # Replace with your actual API key
HDRS = {"X-API-key": API_KEY}

# Market Instruments
CAD = "CAD"
USD = "USD"
BULL = "BULL"
BEAR = "BEAR"
RITC = "RITC"

# Trading Parameters
FEE_MKT = 0.02          # Market order fee per share
REBATE_LMT = 0.01       # Limit order rebate per share
MAX_SIZE_EQUITY = 10000 # Max order size for stocks/ETF
MAX_SIZE_FX = 2500000   # Max order size for FX

# Risk Limits
MAX_LONG_NET = 30000
MAX_SHORT_NET = -30000
MAX_GROSS = 100000

# Arbitrage Thresholds
ARB_THRESHOLD_MIN = 15.0        # Minimum profit threshold CAD
TENDER_PROFIT_MIN = 100.0       # Minimum tender profit threshold
CONVERSION_COST = 1500          # Converter cost in CAD
CONVERTER_BATCH = 10000         # Converter batch size

# Trading Strategy Parameters
AGGRESSIVE_HEDGING = True
POSITION_SIZING_AGGRESSIVE = 0.8
SLIPPAGE_BUFFER = 0.01
LIQUIDITY_THRESHOLD = 1000

# Session Management
session = requests.Session()
session.headers.update(HDRS)

# Global state tracking
position_cache = {}
market_data_cache = {}
last_update_time = 0

# =========================================================================================
# === CORE API FUNCTIONS ===
# =========================================================================================

def get_tick_status():
    """Get current tick and trading status"""
    try:
        resp = session.get(f"{API}/case")
        resp.raise_for_status()
        data = resp.json()
        return data["tick"], data["status"]
    except Exception as e:
        print(f"Error getting tick status: {e}")
        return None, "STOPPED"

def get_securities():
    """Get all securities data"""
    try:
        resp = session.get(f"{API}/securities")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error getting securities: {e}")
        return []

def get_order_book(ticker, depth=5):
    """Get order book for a specific ticker"""
    try:
        resp = session.get(f"{API}/securities/book", params={"ticker": ticker, "limit": depth})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error getting order book for {ticker}: {e}")
        return {"bids": [], "asks": []}

def get_positions():
    """Get current positions"""
    try:
        securities = get_securities()
        positions = {s["ticker"]: int(s.get("position", 0)) for s in securities}
        # Ensure all tickers are present
        for ticker in [CAD, USD, BULL, BEAR, RITC]:
            positions.setdefault(ticker, 0)
        return positions
    except Exception as e:
        print(f"Error getting positions: {e}")
        return {CAD: 0, USD: 0, BULL: 0, BEAR: 0, RITC: 0}

def place_market_order(ticker, action, quantity):
    """Place market order"""
    try:
        if quantity <= 0:
            return None
            
        resp = session.post(f"{API}/orders", params={
            "ticker": ticker,
            "type": "MARKET",
            "quantity": int(quantity),
            "action": action
        })
        
        if resp.ok:
            result = resp.json()
            print(f"SUCCESS: {action} {quantity} {ticker} @ {result.get('vwap', 'MARKET')}")
            return result
        else:
            print(f"ERROR: Failed to place order {ticker} {action} {quantity}: {resp.text}")
            return None
            
    except Exception as e:
        print(f"Exception placing order: {e}")
        return None

def place_limit_order(ticker, action, quantity, price):
    """Place limit order"""
    try:
        if quantity <= 0 or price <= 0:
            return None
            
        resp = session.post(f"{API}/orders", params={
            "ticker": ticker,
            "type": "LIMIT",
            "quantity": int(quantity),
            "action": action,
            "price": round(price, 4)
        })
        
        if resp.ok:
            result = resp.json()
            print(f"LIMIT: {action} {quantity} {ticker} @ {price}")
            return result
        else:
            print(f"ERROR: Failed to place limit order: {resp.text}")
            return None
            
    except Exception as e:
        print(f"Exception placing limit order: {e}")
        return None

def get_tenders():
    """Get active tender offers"""
    try:
        resp = session.get(f"{API}/tenders")
        resp.raise_for_status()
        offers = resp.json()
        return [offer for offer in offers if offer.get('ticker') == RITC]
    except Exception as e:
        print(f"Error getting tenders: {e}")
        return []

def accept_tender(tender_id, price=None):
    """Accept a tender offer"""
    try:
        if price is not None:
            resp = session.post(f"{API}/tenders/{tender_id}", params={"price": price})
        else:
            resp = session.post(f"{API}/tenders/{tender_id}")
        return resp.ok
    except Exception as e:
        print(f"Error accepting tender: {e}")
        return False

# =========================================================================================
# === CONVERTER CLASS ===
# =========================================================================================

class Converter:
    """Handles ETF creation and redemption operations"""
    
    def __init__(self):
        self.creation_id = None
        self.redemption_id = None
        self.initialize_leases()
    
    def get_leases(self):
        """Get current leases"""
        try:
            resp = session.get(f"{API}/leases")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error getting leases: {e}")
            return []
    
    def open_leases(self):
        """Open converter leases"""
        try:
            # Open ETF-Creation lease
            resp = session.post(f"{API}/leases", params={"ticker": "ETF-Creation"})
            if not resp.ok:
                print(f"Failed to open ETF-Creation: {resp.text}")
                
            # Open ETF-Redemption lease
            resp = session.post(f"{API}/leases", params={"ticker": "ETF-Redemption"})
            if not resp.ok:
                print(f"Failed to open ETF-Redemption: {resp.text}")
                
            print("Converter leases opened")
            
        except Exception as e:
            print(f"Exception opening leases: {e}")
    
    def initialize_leases(self):
        """Initialize converter leases"""
        leases = self.get_leases()
        
        if not leases:
            self.open_leases()
            sleep(2)
            leases = self.get_leases()
        
        for lease in leases:
            if lease['ticker'] == 'ETF-Creation':
                self.creation_id = lease['id']
            elif lease['ticker'] == 'ETF-Redemption':
                self.redemption_id = lease['id']
                
        print(f"Converter initialized: Creation={self.creation_id}, Redemption={self.redemption_id}")
    
    def convert_stocks_to_etf(self, quantity):
        """Convert BULL+BEAR to RITC (ETF Creation)"""
        if not self.creation_id:
            print("ETF-Creation lease not available")
            return False
            
        try:
            conversion_fee_usd = int(CONVERSION_COST * quantity / CONVERTER_BATCH)
            
            resp = session.post(f"{API}/leases/{self.creation_id}", params={
                "from1": "BULL", 
                "quantity1": int(quantity),
                "from2": "BEAR", 
                "quantity2": int(quantity),
                "from3": "USD", 
                "quantity3": conversion_fee_usd
            })
            
            if resp.ok:
                print(f"CONVERSION: Created {quantity} RITC from BULL+BEAR")
                return True
            else:
                print(f"Failed ETF creation: {resp.text}")
                return False
                
        except Exception as e:
            print(f"Exception in ETF creation: {e}")
            return False
    
    def convert_etf_to_stocks(self, quantity):
        """Convert RITC to BULL+BEAR (ETF Redemption)"""
        if not self.redemption_id:
            print("ETF-Redemption lease not available")
            return False
            
        try:
            conversion_fee_usd = int(CONVERSION_COST * quantity / CONVERTER_BATCH)
            
            resp = session.post(f"{API}/leases/{self.redemption_id}", params={
                "from1": "RITC", 
                "quantity1": int(quantity),
                "from2": "USD", 
                "quantity2": conversion_fee_usd
            })
            
            if resp.ok:
                print(f"CONVERSION: Redeemed {quantity} RITC to BULL+BEAR")
                return True
            else:
                print(f"Failed ETF redemption: {resp.text}")
                return False
                
        except Exception as e:
            print(f"Exception in ETF redemption: {e}")
            return False

# =========================================================================================
# === MARKET DATA ANALYSIS ===
# =========================================================================================

class MarketAnalyzer:
    """Analyzes market data for arbitrage opportunities"""
    
    def __init__(self):
        self.last_prices = {}
        self.spreads = {}
        self.depths = {}
    
    def update_market_data(self):
        """Update market data for all instruments"""
        try:
            for ticker in [USD, BULL, BEAR, RITC]:
                book = get_order_book(ticker, depth=10)
                
                if book["bids"] and book["asks"]:
                    bid = float(book["bids"][0]["price"])
                    ask = float(book["asks"][0]["price"])
                    
                    self.last_prices[ticker] = {
                        "bid": bid,
                        "ask": ask,
                        "mid": (bid + ask) / 2,
                        "spread": ask - bid
                    }
                    
                    # Calculate total depth
                    bid_depth = sum(int(level["quantity"]) for level in book["bids"])
                    ask_depth = sum(int(level["quantity"]) for level in book["asks"])
                    
                    self.depths[ticker] = {
                        "bid_depth": bid_depth,
                        "ask_depth": ask_depth,
                        "total_depth": bid_depth + ask_depth
                    }
                    
                    # Store full book
                    self.spreads[ticker] = book
                    
        except Exception as e:
            print(f"Error updating market data: {e}")
    
    def get_etf_fair_value(self):
        """Calculate ETF fair value in USD"""
        try:
            if USD not in self.last_prices or BULL not in self.last_prices or BEAR not in self.last_prices:
                return None
                
            # Fair value = (BULL + BEAR) / USD_rate
            bull_cad = self.last_prices[BULL]["mid"]
            bear_cad = self.last_prices[BEAR]["mid"]
            usd_rate = self.last_prices[USD]["mid"]  # CAD per USD
            
            basket_value_cad = bull_cad + bear_cad
            fair_value_usd = basket_value_cad / usd_rate
            
            return fair_value_usd
            
        except Exception as e:
            print(f"Error calculating fair value: {e}")
            return None
    
    def get_arbitrage_opportunities(self):
        """Identify arbitrage opportunities"""
        opportunities = []
        
        try:
            self.update_market_data()
            
            if RITC not in self.last_prices:
                return opportunities
                
            fair_value = self.get_etf_fair_value()
            if fair_value is None:
                return opportunities
                
            ritc_bid = self.last_prices[RITC]["bid"]
            ritc_ask = self.last_prices[RITC]["ask"]
            
            # Opportunity 1: ETF undervalued (buy ETF, sell basket)
            if ritc_ask < fair_value:
                profit_per_share = fair_value - ritc_ask - (FEE_MKT * 3) - (CONVERSION_COST / CONVERTER_BATCH)
                if profit_per_share > ARB_THRESHOLD_MIN / CONVERTER_BATCH:
                    opportunities.append({
                        "type": "buy_etf_sell_basket",
                        "profit_per_share": profit_per_share,
                        "etf_price": ritc_ask,
                        "fair_value": fair_value,
                        "max_quantity": min(
                            self.depths[RITC]["ask_depth"],
                            self.depths[BULL]["bid_depth"],
                            self.depths[BEAR]["bid_depth"]
                        )
                    })
            
            # Opportunity 2: ETF overvalued (sell ETF, buy basket)  
            if ritc_bid > fair_value:
                profit_per_share = ritc_bid - fair_value - (FEE_MKT * 3) - (CONVERSION_COST / CONVERTER_BATCH)
                if profit_per_share > ARB_THRESHOLD_MIN / CONVERTER_BATCH:
                    opportunities.append({
                        "type": "sell_etf_buy_basket",
                        "profit_per_share": profit_per_share,
                        "etf_price": ritc_bid,
                        "fair_value": fair_value,
                        "max_quantity": min(
                            self.depths[RITC]["bid_depth"],
                            self.depths[BULL]["ask_depth"],
                            self.depths[BEAR]["ask_depth"]
                        )
                    })
            
        except Exception as e:
            print(f"Error finding arbitrage opportunities: {e}")
        
        return opportunities
    
    def check_position_limits(self, ritc_change=0, bull_change=0, bear_change=0):
        """Check if projected position changes would violate limits"""
        try:
            positions = get_positions()
            
            # Calculate projected positions
            proj_ritc = positions[RITC] + ritc_change
            proj_bull = positions[BULL] + bull_change
            proj_bear = positions[BEAR] + bear_change
            
            # Calculate gross and net (ETF has 2x multiplier)
            gross = abs(proj_bull) + abs(proj_bear) + 2 * abs(proj_ritc)
            net = proj_bull + proj_bear + 2 * proj_ritc
            
            return (gross <= MAX_GROSS and 
                   MAX_SHORT_NET <= net <= MAX_LONG_NET)
                   
        except Exception as e:
            print(f"Error checking position limits: {e}")
            return False

# =========================================================================================
# === ARBITRAGE EXECUTION ENGINE ===
# =========================================================================================

class ArbitrageEngine:
    """Executes arbitrage strategies"""
    
    def __init__(self, converter):
        self.converter = converter
        self.analyzer = MarketAnalyzer()
        self.active_hedges = []
    
    def execute_arbitrage(self, opportunity):
        """Execute an arbitrage opportunity"""
        try:
            arb_type = opportunity["type"]
            max_qty = opportunity["max_quantity"]
            
            # Calculate optimal trade size
            trade_size = min(
                max_qty,
                int(MAX_SIZE_EQUITY * POSITION_SIZING_AGGRESSIVE),
                CONVERTER_BATCH  # Align with converter batches
            )
            
            if trade_size < 100:  # Minimum viable trade
                return False
                
            # Check position limits
            if arb_type == "buy_etf_sell_basket":
                if not self.analyzer.check_position_limits(ritc_change=trade_size, 
                                                         bull_change=-trade_size, 
                                                         bear_change=-trade_size):
                    print("Position limits would be violated")
                    return False
                    
                return self.execute_buy_etf_sell_basket(trade_size, opportunity)
                
            elif arb_type == "sell_etf_buy_basket":
                if not self.analyzer.check_position_limits(ritc_change=-trade_size,
                                                         bull_change=trade_size,
                                                         bear_change=trade_size):
                    print("Position limits would be violated")
                    return False
                    
                return self.execute_sell_etf_buy_basket(trade_size, opportunity)
                
        except Exception as e:
            print(f"Error executing arbitrage: {e}")
            return False
    
    def execute_buy_etf_sell_basket(self, quantity, opportunity):
        """Execute: Buy ETF, Sell BULL+BEAR, Convert"""
        try:
            print(f"\nEXECUTING BUY ETF ARBITRAGE - Quantity: {quantity}")
            print(f"Expected profit: ${opportunity['profit_per_share'] * quantity:.2f}")
            
            # Step 1: Buy RITC
            ritc_order = place_market_order(RITC, "BUY", quantity)
            if not ritc_order:
                return False
                
            ritc_price = ritc_order.get("vwap", opportunity["etf_price"])
            
            # Step 2: Hedge USD exposure from ETF purchase
            usd_needed = ritc_price * quantity
            hedge_order = place_market_order(USD, "SELL", usd_needed)
            
            # Step 3: Sell BULL and BEAR (synthetic short of basket)
            bull_order = place_market_order(BULL, "SELL", quantity)
            bear_order = place_market_order(BEAR, "SELL", quantity)
            
            if not bull_order or not bear_order:
                print("Failed to execute basket leg")
                # Should implement rollback here
                return False
                
            # Step 4: Convert RITC to BULL+BEAR to cover short positions
            if not self.converter.convert_etf_to_stocks(quantity):
                print("Conversion failed - positions may be unbalanced")
                return False
            
            # Calculate actual profit
            bull_price = bull_order.get("vwap", 0)
            bear_price = bear_order.get("vwap", 0)
            basket_proceeds = (bull_price + bear_price) * quantity
            etf_cost = ritc_price * quantity
            
            # Account for FX hedge
            if hedge_order:
                fx_rate = hedge_order.get("vwap", 1)
                etf_cost_cad = etf_cost * fx_rate
            else:
                etf_cost_cad = etf_cost * opportunity.get("usd_rate", 1.3)
                
            gross_profit = basket_proceeds - etf_cost_cad
            net_profit = gross_profit - (quantity * FEE_MKT * 3) - CONVERSION_COST
            
            print(f"ARBITRAGE COMPLETED:")
            print(f"  Gross profit: ${gross_profit:.2f}")
            print(f"  Net profit: ${net_profit:.2f}")
            print(f"  Profit per share: ${net_profit/quantity:.4f}")
            
            return True
            
        except Exception as e:
            print(f"Error in buy ETF arbitrage: {e}")
            return False
    
    def execute_sell_etf_buy_basket(self, quantity, opportunity):
        """Execute: Sell ETF, Buy BULL+BEAR, Convert"""
        try:
            print(f"\nEXECUTING SELL ETF ARBITRAGE - Quantity: {quantity}")
            print(f"Expected profit: ${opportunity['profit_per_share'] * quantity:.2f}")
            
            # Step 1: Buy BULL and BEAR
            bull_order = place_market_order(BULL, "BUY", quantity)
            bear_order = place_market_order(BEAR, "BUY", quantity)
            
            if not bull_order or not bear_order:
                print("Failed to buy basket")
                return False
                
            # Step 2: Convert BULL+BEAR to RITC
            if not self.converter.convert_stocks_to_etf(quantity):
                print("Conversion failed")
                return False
                
            # Step 3: Sell RITC
            ritc_order = place_market_order(RITC, "SELL", quantity)
            if not ritc_order:
                print("Failed to sell ETF")
                return False
                
            ritc_price = ritc_order.get("vwap", opportunity["etf_price"])
            
            # Step 4: Hedge USD exposure from ETF sale
            usd_received = ritc_price * quantity
            hedge_order = place_market_order(USD, "BUY", usd_received)
            
            # Calculate actual profit
            bull_price = bull_order.get("vwap", 0)
            bear_price = bear_order.get("vwap", 0)
            basket_cost = (bull_price + bear_price) * quantity
            
            if hedge_order:
                fx_rate = hedge_order.get("vwap", 1)
                etf_proceeds_cad = usd_received * fx_rate
            else:
                etf_proceeds_cad = usd_received * opportunity.get("usd_rate", 1.3)
                
            gross_profit = etf_proceeds_cad - basket_cost
            net_profit = gross_profit - (quantity * FEE_MKT * 3) - CONVERSION_COST
            
            print(f"ARBITRAGE COMPLETED:")
            print(f"  Gross profit: ${gross_profit:.2f}")
            print(f"  Net profit: ${net_profit:.2f}")
            print(f"  Profit per share: ${net_profit/quantity:.4f}")
            
            return True
            
        except Exception as e:
            print(f"Error in sell ETF arbitrage: {e}")
            return False

# =========================================================================================
# === TENDER OFFER HANDLER ===
# =========================================================================================

class TenderHandler:
    """Handles tender offer evaluation and execution"""
    
    def __init__(self, converter):
        self.converter = converter
        self.analyzer = MarketAnalyzer()
        self.processed_tenders = set()
    
    def evaluate_tender(self, tender):
        """Evaluate profitability of a tender offer"""
        try:
            tender_id = tender["tender_id"]
            if tender_id in self.processed_tenders:
                return None
                
            action = tender["action"]  # BUY or SELL
            price = tender["price"]    # USD
            quantity = tender["quantity"]
            
            print(f"\nEVALUATING TENDER {tender_id}: {action} {quantity} @ ${price}")
            
            # Get current market data
            self.analyzer.update_market_data()
            
            if RITC not in self.analyzer.last_prices:
                return None
                
            # Calculate best execution paths
            paths = self.calculate_execution_paths(tender)
            
            if not paths:
                return None
                
            # Find most profitable path
            best_path = max(paths, key=lambda x: x["net_profit"])
            
            if best_path["net_profit"] > TENDER_PROFIT_MIN:
                best_path["tender"] = tender
                return best_path
            else:
                print(f"Tender not profitable: ${best_path['net_profit']:.2f}")
                return None
                
        except Exception as e:
            print(f"Error evaluating tender: {e}")
            return None
    
    def calculate_execution_paths(self, tender):
        """Calculate different ways to execute and unwind tender"""
        paths = []
        action = tender["action"]
        price = tender["price"]
        quantity = tender["quantity"]
        
        try:
            # Path 1: Direct ETF market execution
            if action == "SELL":  # We sell RITC to tender, need to buy from market
                if RITC in self.analyzer.last_prices:
                    market_price = self.analyzer.last_prices[RITC]["ask"]
                    profit = (price - market_price) * quantity
                    paths.append({
                        "method": "direct_etf",
                        "gross_profit": profit,
                        "net_profit": profit - quantity * FEE_MKT,
                        "market_price": market_price,
                        "feasible": self.analyzer.depths[RITC]["ask_depth"] >= quantity
                    })
                    
            else:  # We buy RITC from tender, need to sell to market
                if RITC in self.analyzer.last_prices:
                    market_price = self.analyzer.last_prices[RITC]["bid"]
                    profit = (market_price - price) * quantity
                    paths.append({
                        "method": "direct_etf",
                        "gross_profit": profit,
                        "net_profit": profit - quantity * FEE_MKT,
                        "market_price": market_price,
                        "feasible": self.analyzer.depths[RITC]["bid_depth"] >= quantity
                    })
            
            # Path 2: Synthetic execution via basket + conversion
            fair_value = self.analyzer.get_etf_fair_value()
            if fair_value:
                if action == "SELL":
                    # Create RITC from basket, sell to tender
                    bull_price = self.analyzer.last_prices[BULL]["ask"]
                    bear_price = self.analyzer.last_prices[BEAR]["ask"]
                    basket_cost_cad = (bull_price + bear_price) * quantity
                    usd_rate = self.analyzer.last_prices[USD]["ask"]
                    
                    proceeds_usd = price * quantity
                    proceeds_cad = proceeds_usd * usd_rate
                    
                    gross_profit = proceeds_cad - basket_cost_cad
                    net_profit = gross_profit - quantity * FEE_MKT * 3 - CONVERSION_COST
                    
                    paths.append({
                        "method": "basket_conversion",
                        "gross_profit": gross_profit,
                        "net_profit": net_profit,
                        "basket_cost": basket_cost_cad,
                        "feasible": (self.analyzer.depths[BULL]["ask_depth"] >= quantity and
                                   self.analyzer.depths[BEAR]["ask_depth"] >= quantity)
                    })
                    
                else:  # BUY tender
                    # Buy from tender, convert to basket, sell basket
                    bull_price = self.analyzer.last_prices[BULL]["bid"]
                    bear_price = self.analyzer.last_prices[BEAR]["bid"]
                    basket_proceeds_cad = (bull_price + bear_price) * quantity
                    usd_rate = self.analyzer.last_prices[USD]["bid"]
                    
                    cost_usd = price * quantity
                    cost_cad = cost_usd * usd_rate
                    
                    gross_profit = basket_proceeds_cad - cost_cad
                    net_profit = gross_profit - quantity * FEE_MKT * 3 - CONVERSION_COST
                    
                    paths.append({
                        "method": "basket_conversion",
                        "gross_profit": gross_profit,
                        "net_profit": net_profit,
                        "basket_proceeds": basket_proceeds_cad,
                        "feasible": (self.analyzer.depths[BULL]["bid_depth"] >= quantity and
                                   self.analyzer.depths[BEAR]["bid_depth"] >= quantity)
                    })
            
        except Exception as e:
            print(f"Error calculating execution paths: {e}")
        
        return [path for path in paths if path["feasible"]]
    
    def execute_tender(self, evaluation):
        """Execute tender offer"""
        try:
            tender = evaluation["tender"]
            method = evaluation["method"]
            
            # Accept the tender first
            if not accept_tender(tender["tender_id"], tender.get("price")):
                print(f"Failed to accept tender {tender['tender_id']}")
                return False
                
            self.processed_tenders.add(tender["tender_id"])
            
            print(f"EXECUTING TENDER via {method}")
            
            if method == "direct_etf":
                return self.execute_direct_etf(tender, evaluation)
            elif method == "basket_conversion":
                return self.execute_basket_conversion(tender, evaluation)
            else:
                print(f"Unknown execution method: {method}")
                return False
                
        except Exception as e:
            print(f"Error executing tender: {e}")
            return False
    
    def execute_direct_etf(self, tender, evaluation):
        """Execute tender via direct ETF market trades"""
        try:
            action = tender["action"]
            quantity = tender["quantity"]
            price = tender["price"]
            
            if action == "SELL":
                # We're short RITC from tender, need to buy from market
                market_order = place_market_order(RITC, "BUY", quantity)
                if market_order:
                    # Hedge the USD exposure
                    usd_exposure = price * quantity
                    hedge_order = place_market_order(USD, "SELL", usd_exposure)
                    print(f"Tender hedge: SELL ${usd_exposure:.2f} USD")
                    return True
            else:
                # We're long RITC from tender, need to sell to market
                market_order = place_market_order(RITC, "SELL", quantity)
                if market_order:
                    # Hedge the USD exposure
                    usd_exposure = price * quantity
                    hedge_order = place_market_order(USD, "BUY", usd_exposure)
                    print(f"Tender hedge: BUY ${usd_exposure:.2f} USD")
                    return True
                    
            return False
            
        except Exception as e:
            print(f"Error in direct ETF execution: {e}")
            return False
    
    def execute_basket_conversion(self, tender, evaluation):
        """Execute tender via basket trading and conversion"""
        try:
            action = tender["action"]
            quantity = tender["quantity"]
            price = tender["price"]
            
            if action == "SELL":
                # Create RITC from basket to fulfill tender
                # Step 1: Buy basket
                bull_order = place_market_order(BULL, "BUY", quantity)
                bear_order = place_market_order(BEAR, "BUY", quantity)
                
                if not bull_order or not bear_order:
                    print("Failed to buy basket for tender")
                    return False
                
                # Step 2: Convert to RITC
                if not self.converter.convert_stocks_to_etf(quantity):
                    print("Failed to convert basket to ETF")
                    return False
                
                # Step 3: Hedge USD proceeds from tender
                usd_proceeds = price * quantity
                hedge_order = place_market_order(USD, "SELL", usd_proceeds)
                
            else:  # BUY tender
                # Convert received RITC to basket and sell
                # Step 1: Convert RITC to basket
                if not self.converter.convert_etf_to_stocks(quantity):
                    print("Failed to convert ETF to basket")
                    return False
                
                # Step 2: Sell basket
                bull_order = place_market_order(BULL, "SELL", quantity)
                bear_order = place_market_order(BEAR, "SELL", quantity)
                
                if not bull_order or not bear_order:
                    print("Failed to sell basket from tender")
                    return False
                
                # Step 3: Hedge USD cost of tender
                usd_cost = price * quantity
                hedge_order = place_market_order(USD, "BUY", usd_cost)
            
            return True
            
        except Exception as e:
            print(f"Error in basket conversion execution: {e}")
            return False
    
    def process_tenders(self):
        """Process all available tenders"""
        try:
            tenders = get_tenders()
            
            for tender in tenders:
                evaluation = self.evaluate_tender(tender)
                if evaluation:
                    print(f"PROFITABLE TENDER FOUND: ${evaluation['net_profit']:.2f}")
                    if self.execute_tender(evaluation):
                        print("Tender executed successfully")
                    else:
                        print("Tender execution failed")
                        
        except Exception as e:
            print(f"Error processing tenders: {e}")

# =========================================================================================
# === MAIN TRADING ENGINE ===
# =========================================================================================

def main():
    """Main trading loop"""
    print("="*80)
    print("RIT ALGORITHMIC ETF ARBITRAGE BOT - ENHANCED VERSION")
    print("="*80)
    print("Initializing systems...")
    
    # Initialize components
    converter = Converter()
    arbitrage_engine = ArbitrageEngine(converter)
    tender_handler = TenderHandler(converter)
    
    print("Systems initialized. Starting trading loop...")
    
    tick_count = 0
    last_status_print = 0
    
    try:
        while True:
            tick, status = get_tick_status()
            
            if status != "ACTIVE":
                print(f"Trading stopped. Status: {status}")
                break
                
            tick_count += 1
            
            # Print status every 10 ticks
            if tick_count - last_status_print >= 10:
                positions = get_positions()
                print(f"\nTick {tick} - Positions: BULL={positions[BULL]}, BEAR={positions[BEAR]}, RITC={positions[RITC]}, USD={positions[USD]}")
                last_status_print = tick_count
            
            try:
                # 1. Check for arbitrage opportunities
                opportunities = arbitrage_engine.analyzer.get_arbitrage_opportunities()
                
                for opp in opportunities:
                    print(f"ARBITRAGE OPPORTUNITY: {opp['type']} - Profit/share: ${opp['profit_per_share']:.4f}")
                    if arbitrage_engine.execute_arbitrage(opp):
                        print("Arbitrage executed successfully")
                    else:
                        print("Arbitrage execution failed")
                
                # 2. Process tender offers
                tender_handler.process_tenders()
                
            except Exception as e:
                print(f"Error in trading loop: {e}")
                
            # Brief pause to prevent API overload
            sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nTrading interrupted by user")
    except Exception as e:
        print(f"Critical error in main loop: {e}")
    finally:
        # Final position report
        final_positions = get_positions()
        print("\nFINAL POSITIONS:")
        for ticker, position in final_positions.items():
            print(f"  {ticker}: {position}")
        print("="*80)

if __name__ == "__main__":
    main()