

from utils import * 


def check_conversion_arbitrage(converter):
    # Get best prices
    bull_bid, bull_ask, _, _ = best_bid_ask(BULL)
    bear_bid, bear_ask, _, _ = best_bid_ask(BEAR)
    ritc_bid_usd, ritc_ask_usd, _, _ = best_bid_ask(RITC)
    usd_bid, usd_ask, _, _ = best_bid_ask(USD)

    # Convert ETF prices to CAD

    # place_mkt(BEAR, "SELL", 10000)['vwap']
    # # place_mkt("USD", "BUY", 10000)
    # # place_mkt("USD", "SELL", 10000)
    # exit()

    q = ORDER_QTY  # Assumed 10,000

    # Direction 1: Basket → ETF
    basket_cost_cad = basket_to_etf_value(bull_ask, bear_ask, q)  # CAD
    etf_proceeds_cad = ritc_bid_usd * q * usd_bid  # USD to CAD
    profit1 = etf_proceeds_cad - basket_cost_cad - 1500  # CAD, including ETF-Creation cost

    # Direction 2: ETF → Basket
    etf_cost_cad = ritc_ask_usd * q * usd_ask  # CAD
    basket_proceeds = (bull_bid + bear_bid) * q  # CAD
    profit2 = basket_proceeds - etf_cost_cad - 1500  # CAD, including ETF-Redemption cost

    # Place trades if profitable
    if profit1 > 2000 and within_limits():
        try:
            br = place_mkt(BULL, "BUY", q)['vwap']  # CAD
            bl = place_mkt(BEAR, "BUY", q)['vwap']  # CAD
            out = converter.convert_bull_bear(q)  # ETF-Creation, $1,500 CAD
            r1 = place_mkt(RITC, "SELL", q)['vwap']  # USD
            print(f"[FX] Selling USD {q*r1}")
            usd = place_mkt("USD", "SELL", r1*q)['vwap']  # CAD per USD
            profit = q * (r1 * usd - bl - br) - 1500  # CAD
            print(f"Profit: {profit:.2f} CAD")
            print("[ARBITRAGE] Basket -> ETF")
        except Exception as e:
            print(f"Basket -> ETF trade failed: {e}")

    elif profit2 > 2000 and within_limits():
        try:
            r1 = place_mkt(RITC, "BUY", q)['vwap']  # USD
            print(f"[FX] Buying USD {q*r1}")
            usd = place_mkt("USD", "BUY", r1*q)['vwap']  # CAD per USD
            out = converter.convert_ritc(q)  # ETF-Redemption, $1,500 CAD
            bl = place_mkt(BULL, "SELL", q)['vwap']  # CAD
            br = place_mkt(BEAR, "SELL", q)['vwap']  # CAD
            profit = q * (bl + br - r1 * usd) - 1500  # CAD
            print(f"Profit: {profit:.2f} CAD")
            print("[ARBITRAGE] ETF -> Basket")
        except Exception as e:
            print(f"ETF -> Basket trade failed: {e}")
