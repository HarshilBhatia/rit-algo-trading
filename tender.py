from utils import *
import time


class EvaluateTenders():

    def __init__(self, tender, converter):
        self.positions = []
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
                profit = level['quantity'] * (self.price - level['price'])
                self.positions.append({'type': 'ETF', 'level_price': level['price'], 'level_qty': level['quantity'], 'profit': profit / level['quantity'],'profit_with_q': profit})
        elif self.action == 'BUY':  # You buy RITC, go long, need to sell at bid levels
            for level in ritc_bids:
                profit = level['quantity'] * (level['price'] - self.price)
                self.positions.append({'type': 'ETF', 'level_price': level['price'], 'level_qty': level['quantity'],  'profit': profit / level['quantity'], 'profit_with_q': profit})


        self.positions_stocks = [] 
        bull_asks , bull_bids = bull['asks'], bull['bids']
        bear_asks , bear_bids = bear['asks'], bear['bids']

        if self.action == 'SELL':
            for level_bull, level_bear in zip(bull_asks, bear_asks):
                q = min(level_bull['quantity'], level_bear['quantity']) # incorrect, ideally need to propogate down. 
                profit = q* (self.price - (level_bull['price'] + level_bear['price'])) - conversion_cost(q) # this should be per 10000.
                self.positions.append({'type': 'STOCK',
                                    'level_price ': level_bull['price'] + level_bear['price'],
                                    'level_qty': q,
                                    'profit': profit / (q),
                                    'profit_with_q': profit})
                
        elif self.action == 'BUY':
            for level_bull, level_bear in zip(bull_bids, bear_bids):
                q = min(level_bull['quantity'], level_bear['quantity']) # incorrect, ideally need to propogate down. 
                # this profit is wrong, doesn't account for usd / cad conversion.
                profit = q* ((level_bull['price'] + level_bear['price'])  - self.price) - conversion_cost(q) # this should be per 10000.
                self.positions.append({
                                    'type': 'STOCK',
                                    'level_price ': level_bull['price'] + level_bear['price'],
                                    'level_qty': q,
                                    'profit': profit / (q),
                                    'profit_with_q': profit})


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
                net_profit +=  q_left * p['profit']
                if p['type'] == 'STOCK':
                    self.stock_pos += q_left
                elif p['type'] == 'ETF':
                    self.etf_pos += q_left

                q_left = 0 


        # print(tabulate(self.positions))

        print('vanilla profit:', net_profit)
        net_profit -= 0.02*self.etf_pos  + 0.02 * 2 * self.stock_pos# 
        print("Profit:", net_profit, 'etf pos:', self.etf_pos, 'stock pos', self.stock_pos)

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



    def unwind_tender_position(self):

        unwind_qty = self.etf_pos

        # hedge transaction costs. 
        hedge_cost = unwind_qty * 0.02 

        fx_hedge_conv = (self.quantity - self.etf_pos) * self.price  # USD quantity to hedge -- based on stock position.

        # ETF unwind (direct)
        avg_price = []
        if self.action == 'SELL':  # You need to buy back RITC to close short
            # CHUNKS of 10k 
            place_mkt(USD, "BUY", hedge_cost)  # Hedge the USD transaction cost
            place_mkt(USD, "SELL", fx_hedge_conv)  # Conversion remaining USD Hedge

            while unwind_qty > 0:
                qty = min(MAX_SIZE_EQUITY, unwind_qty)
                resp = place_mkt(RITC, "BUY", qty)
                avg_price.append(resp['vwap'])
                unwind_qty -= qty
                print(unwind_qty)

        else:  # action == 'BUY', you need to sell RITC to close long

            place_mkt(USD, "BUY", hedge_cost)  # Hedge the USD transaction cost
            place_mkt(USD, "BUY", fx_hedge_conv)  # Conversion remaining USD Hedge
            
            while unwind_qty > 0:
                qty = min(MAX_SIZE_EQUITY, unwind_qty)
                resp = place_mkt(RITC, "SELL", qty)
                avg_price.append(resp['vwap'])
                unwind_qty -= qty
                print(unwind_qty)


        # Calculate average price
        if avg_price:
            avg_price = sum(avg_price) / len(avg_price)
        else:
            avg_price = 0

        # convert_later = 0
        conv_unwind_qtf = self.stock_pos

        # IDEA -- FOR converter -- we don't need to instantly CONVERT right. We can WAIT
        # since all the USD is already hegded. Wait for what? -- wait for the random walk price
        # to make sense. Can also use this instead of current conversion pnl metric to determine 
        # if BEAR / BULL are undervalued or overvalued. 
        
        while conv_unwind_qtf > 0:
            qty = min(MAX_SIZE_EQUITY, conv_unwind_qtf)

            if self.action == 'SELL':
                place_mkt(BULL, 'BUY', qty)
                place_mkt(BEAR, 'BUY', qty)
                place_mkt(USD, 'BUY', 2*qty*0.02)  # transaction cost.
                print(f"Bought {qty} BULL & BEAR")
            else:
                print(f"Redeemed {qty} RITC, then selling stocks")
                place_mkt(BULL, 'SELL', qty)
                place_mkt(BEAR, 'SELL', qty)

                place_mkt(USD, 'BUY', 2*qty*0.02)  # transaction cost.
            
            conv_unwind_qtf -= qty

        conv_unwind_qtf = self.stock_pos
        while conv_unwind_qtf > 0:
            qty = min(MAX_SIZE_EQUITY, conv_unwind_qtf)

            if self.action == 'SELL':
                self.converter.convert_bull_bear(qty) # Convert BULL and BEAR to RITC
                place_mkt(USD, 'BUY',conversion_cost(qty))  # Hedge conversion cost
                print(f"[Converted] BB -> RITC")
            else:
                self.converter.convert_ritc(qty) # Convert RITC to BULL and BEAR
                place_mkt(USD, 'BUY',conversion_cost(qty))  # Hedge conversion cost
                print(f"[Converted] RITC -> BB ")
            
            conv_unwind_qtf -= qty

    
        # exit()
        


def check_tender(converter):

  
    
    # Tender handling
    tenders = get_tenders()
    unwinding_active = False  # Flag for later
    for tender in tenders:  # Prioritize by profit? Sort if multiple


        T = EvaluateTenders(tender, converter) 
        # tender_ids_eval.add(tender['tender_id'])

        eval_result = T.evaluate_tender_profit()

        print(f"Evaluated profit : {eval_result}")

        if eval_result['profit'] > 1000:
            if T.accept_and_hedge_tender():
                print(f"Accepted tender ID {tender['tender_id']}, profit {eval_result['profit']:.2f}")
                T.unwind_tender_position()  # Trigger unwind
            else:
                print(f"Failed to accept tender ID {tender['tender_id']}")
        else:
            print(f"Rejected tender ID {tender['tender_id']}: Not profitable")




# Testing code
def test_tender_code(converter = None):    

    # Iterate through all files in the directory
    for root, _, files in os.walk('output/'):
        for file in files:
            # Check if the file has a .pkl or .pickle extension
            if file.endswith(('.pkl', '.pickle')):
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
                    T = EvaluateTenders(data, converter) 
                    eval_result = T.evaluate_tender_profit()

            

if __name__ == '__main__':
    test_tender_code()