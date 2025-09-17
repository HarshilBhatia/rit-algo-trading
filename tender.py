from utils import *
import time


class EvaluateTenders():

    def __init__(self, tender, converter):
        self.positions = {} 
        self.stock_pos, self.etf_pos = 0,0 
        self.tender = tender
        self.action = tender['action']
        self.price = tender['price']
        self.quantity = tender['quantity']
        self.converter = converter 
        
        pass

    # 
    def evaluate_tender_profit(self, usd = None, bull = None, bear = None, ritc = None):

        # TODO: The idea here will be -- evaulate cost (ETF) / individual + conv per bid / ask. 
        # Then rank them -- and calculate the expected payout till we reach the quantity. 

        # TODO: Think how you'll unwind this position. 


        if usd == None: 
            bull = best_bid_ask_entire_depth(BULL)
            bear = best_bid_ask_entire_depth(BEAR)
            ritc  = best_bid_ask_entire_depth(RITC)
            usd = best_bid_ask_entire_depth(USD)   





        ritc_asks , ritc_bids = ritc['asks'], ritc['bids']


        # i want to compute the direct profit at each bid and ask level. 

        if self.action == 'SELL':  # You sell RITC, go short
            for level in ritc_asks:
                profit = level['quantity'] * (self.p_tender - level['price'])
                self.positions.append({'type': 'ETF', 'level_price': level['price'], 'level_qty': level['quantity'], 'profit': profit / level['quantity'],'profit_with_q': profit})
        elif self.action == 'BUY':  # You buy RITC, go long, need to sell at bid levels
            for level in ritc_bids:
                profit = level['quantity'] * (level['price'] - self.p_tender)
                self.positions.append({'type': 'ETF', 'level_price': level['price'], 'level_qty': level['quantity'],  'profit': profit / level['quantity'], 'profit_with_q': profit})


        self.positions_stocks = [] 
        bull_asks , bull_bids = bull['asks'], bull['bids']
        bear_asks , bear_bids = bear['asks'], bear['bids']

        # if self.action == 'SELL':
        #     for level_bull, level_bear in zip(bull_asks, bear_asks):
        #         q = min(level_bull['quantity'], level_bear['quantity']) # incorrect, ideally need to propogate down. 
        #         profit = q* (self.price - (level_bull['price'] + level_bear['price'])) - CONVERTER_COST * q / 10000 # this should be per 10000.
        #         self.positions.append({'type': 'STOCK',
        #                             'level_price ': level_bull['price'] + level_bear['price'],
        #                             'level_qty': q,
        #                             'profit': profit / (q),
        #                             'profit_with_q': profit})
                
        # elif self.action == 'BUY':
        #     for level_bull, level_bear in zip(bull_bids, bear_bids):
        #         q = min(level_bull['quantity'], level_bear['quantity']) # incorrect, ideally need to propogate down. 
        #         # this profit is wrong, doesn't account for usd / cad conversion.
        #         profit = q* ((level_bull['price'] + level_bear['price'])  - self.p_tender) - CONVERTER_COST # this should be per 10000.
        #         self.positions.append({
        #                             'type': 'STOCK',
        #                             'level_price ': level_bull['price'] + level_bear['price'],
        #                             'level_qty': q,
        #                             'profit': profit / (q),
        #                             'profit_with_q': profit})


        self.positions.sort(key=lambda x: x['profit'], reverse=True)

        net_profit = 0
        q_left = self.quantity

        for p in self.positions:
            if q_left >= p['level_qty']:
                q_left -= p['level_qty']
                net_profit += p['level_qty'] * p['profit']
                if p['type'] == 'STOCK':
                    self.stock_pos += p['level_qty']
                elif p['type'] == 'ETF':
                    self.etf_pos += p['level_qty']
            else:
                q_left = 0 
                net_profit +=  q_left * p['profit']

        print("Profit:", net_profit)

        profitable = net_profit > 0

        return {
            'profitable': profitable,
            'profit': net_profit,
        }


    def accept_and_hedge_tender(self):
        
        # if buy tender
        usd_quantity = self.tender['price'] * self.etf_pos  # USD quantity to hedge -- based on ETF position.
        accept_tender(self.tender)
        # fx hedge
        # place_mkt(USD, tender['action'], usd_quantity)    
        # Place the tender order
        
        return True



    def unwind_tender_position(self, converter):

        unwind_qty = self.etf_pos

        # hedge transaction costs. 
        hedge_cost = unwind_qty * 0.02 




        # ETF unwind (direct)
        avg_price = []
        if self.action == 'SELL':  # You need to buy back RITC to close short
            # CHUNKS of 10k 
            place_mkt(USD, 'BUY', hedge_cost)  # Hedge the USD transaction cost

            for i in range(0, unwind_qty, MAX_SIZE_EQUITY):
                qty = min(MAX_SIZE_EQUITY, unwind_qty - i)
                resp = place_mkt(RITC, "BUY", qty)
                avg_price.append(resp['vwap'])
                unwind_qty -= qty
        else:  # action == 'BUY', you need to sell RITC to close long

            place_mkt(USD, 'BUY', hedge_cost)  # Hedge the USD transaction cost
            
            for i in range(0, unwind_qty, MAX_SIZE_EQUITY):
                qty = min(MAX_SIZE_EQUITY, unwind_qty - i)
                resp = place_mkt(RITC, "SELL", qty)
                avg_price.append(resp['vwap'])
                unwind_qty -= qty

        # Calculate average price
        if avg_price:
            avg_price = sum(avg_price) / len(avg_price)
        else:
            avg_price = 0

        # Sort by best (lowest) total_cost for BUY, highest for SELL
        # if action == 'SELL':
        #     unwind_options.sort(key=lambda x: x['total_cost'])
        # else:
        #     unwind_options.sort(key=lambda x: -x['total_cost'])

        # convert_later = 0
        # # Execute orders in ranked order until q_left is zero
        # for opt in unwind_options:
        #     if q_left <= 0:
        #         break
        #     qty = min(opt['qty'], q_left, MAX_SIZE_EQUITY)
        #     if qty <= 0:
        #         continue
        #     if opt['type'] == 'ETF':
        #         place_mkt(RITC, opt['action'], qty)
        #         print(f"Unwound {qty} RITC via ETF {opt['action']} at {opt['price']}")
        #     else:
        #         # Stocks + converter
        #         if opt['action'] == 'BUY':
        #             place_mkt(BULL, 'BUY', qty)
        #             place_mkt(BEAR, 'BUY', qty)
        #             print(f"Bought {qty} BULL & BEAR, then converted to RITC (manual step)")
        #         else:
        #             print(f"Redeemed {qty} RITC, then selling stocks (manual step)")
        #             place_mkt(BULL, 'SELL', qty)
        #             place_mkt(BEAR, 'SELL', qty)
        
        #         convert_later += qty

        #     q_left -= qty


        # print("[UPDATE] Conversion step pending for the qty", convert_later)

        # if opt['action'] == 'BUY' and convert_later > 0:
        #     converter.convert_bull_bear(convert_later)
        #     print(f"Converted {convert_later} BULL and BEAR via converter after buying stocks")


        # elif opt['action'] == 'SELL' and convert_later > 0:
        #     converter.convert_ritc(convert_later)
        #     print(f"Converted {convert_later} RITC via converter after redeeming RITC")


        # print("Unwind complete")


def check_tender(converter):

  
    
    # Tender handling
    tenders = get_tenders()
    unwinding_active = False  # Flag for later
    for tender in tenders:  # Prioritize by profit? Sort if multiple


        T = EvaluateTenders(tender, converter) 
        # tender_ids_eval.add(tender['tender_id'])

        eval_result = T.evaluate_tender_profit()

        print(f"Evaluated profit : {eval_result}")

        if eval_result['profitable'] > -1000000000:
            if T.accept_and_hedge_tender():
                print(f"Accepted tender ID {tender['tender_id']}, profit {eval_result['profit']:.2f}")
                T.unwind_tender_position()  # Trigger unwind
            else:
                print(f"Failed to accept tender ID {tender['tender_id']}")
        else:
            print(f"Rejected tender ID {tender['tender_id']}: Not profitable")




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

            