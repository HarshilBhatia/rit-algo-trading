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
from tender import * 
from utils import *
from etf_arb import check_conversion_arbitrage
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



tender_ids_eval = set() 

# Example usage in main loop:
def main():
    # resp = open_leases()
    tick, status = get_tick_status()
    converter = Converter() # initializes the leases
    ps = positions_map()
    print(ps)
    
    while status == "ACTIVE":
        check_conversion_arbitrage(converter)
        check_tender(converter)
        sleep(0.5)
        tick, status = get_tick_status()
        

if __name__ == "__main__":
    main()

    # test_tender_code()



"""

25.62


bid start 25.74 25.68


9.86 9.77
16.18 16.13

"""