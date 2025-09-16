from utils import *
import time

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
            # profits_stocks.append({'level_price_bull': level_bull['price'], 'level_qty_bull': level_bull['quantity'], 
            #                        'level_price_bear': level_bear['price'], 'level_qty_bear': level_bear['quantity'],
            #                        'profit': profit})
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
                # 'level_price_bull': level_bull['price'],  
                                #    'level_price_bear': level_bear['price'], 
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

    convert_later = 0
    # Execute orders in ranked order until q_left is zero
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
                print(f"Bought {qty} BULL & BEAR, then converted to RITC (manual step)")
            else:
                print(f"Redeemed {qty} RITC, then selling stocks (manual step)")
                place_mkt(BULL, 'SELL', qty)
                place_mkt(BEAR, 'SELL', qty)
    
            convert_later += qty

        q_left -= qty


    print("[UPDATE] Conversion step pending for the qty", convert_later)

    if opt['action'] == 'BUY' and convert_later > 0:
        convert_bull_bear(convert_later)
        print(f"Converted {convert_later} BULL and BEAR via converter after buying stocks")


    elif opt['action'] == 'SELL' and convert_later > 0:
        convert_ritc(convert_later)
        print(f"Converted {convert_later} RITC via converter after redeeming RITC")


    print("Unwind complete")
