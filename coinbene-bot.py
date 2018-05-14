#!/usr/bin/env python
# -*- coding:utf-8 -*-
#author:xuanzhi

import requests
import json
import time
import hashlib
import decimal
import math
import types
import random
from optparse import OptionParser

# create a new context for this task
ctx = decimal.Context()

# 20 digits should be enough for everyone :D
ctx.prec = 20

def float_to_str(f):
    """
    Convert the given float to a string,
    without resorting to scientific notation
    """
    d1 = ctx.create_decimal(repr(f))
    return format(d1, 'f')



BASE_API = 'https://api.coinbene.com/v1/'
BTC_USD_API = 'https://api.cryptowat.ch/markets/kraken/btcusd/price'

DEFAULT_HEADER = {}


proxies = {
        }


class Client_Coinbene():
    def __init__(self, apikey, secretkey):
        self._public_key = str(apikey)
        self._private_key = str(secretkey)
        self.sessn = requests.Session()
        self.adapter = requests.adapters.HTTPAdapter(pool_connections=5,
                pool_maxsize=5, max_retries=5)
        self.sessn.mount('http://', self.adapter)
        self.sessn.mount('https://', self.adapter)
        self._exchange_name = 'coinbene'
        self.order_list = []

    def signature(self, message):
        content = message
        #print(content)
        signature = hashlib.md5(content.encode('utf-8')).hexdigest().lower() # 32位md5算法进行加密签名
        return signature

    def signedRequest(self, method, path, params:dict):

        # create signature:

        _timestamp = str(int(time.time()*1000))   #时间戳，精确到毫秒
        params['timestamp'] = _timestamp
        params['apiid'] = self._public_key
        params['secret'] = self._private_key
        param = ''
        for key in sorted(params.keys()):
            #print(key)
            param += key.upper() + '=' + str(params.get(key)).upper() + '&'
        param = param.rstrip(' & ')
        #print(param) 
        signature = self.signature(message=param)
        #print(signature)
        params['sign'] = str(signature)
        del params['secret']
        #print(params)
        resp = self.sessn.request(method,BASE_API+path,headers=None,data=None,params=params,proxies=proxies)
        data = json.loads(resp.content)
        return data

    def get_btc_usd_price(self):
        resp = self.sessn.request("GET",BTC_USD_API,headers=None,data=None,params=None,proxies=proxies)
        data = json.loads(resp.content)
        return data['result']['price']


    def ticker(self,symbol):
        symbol = symbol.replace('_','').lower()
        params = {'symbol':symbol}
        data = self.signedRequest(method="GET",path ='market/ticker',params=params)['ticker']
        data[0]['last_usd_equiv'] = float_to_str(float(data[0]['last'])*float(self.get_btc_usd_price()))
        return data[0]

    def depth(self,symbol,depth=100):    #默认盘口深度为10
        symbol = symbol.replace('_','').lower()
        params = {'symbol':symbol,'depth':depth}
        data = self.signedRequest(method="GET",path ='market/orderbook',params=params)['orderbook']
        asks,bids = [],[] 
        for item in data['asks']:
            asks.append([item['price'],item['quantity']])
        for item in data['bids']:
            bids.append([item['price'],item['quantity']])
        return {'asks':asks,'bids':bids}

    def highest_ask(self, symbol):
        asks = self.depth(symbol)['asks']
        quantity = float(0)
        price = float(0)
        for item in asks:
            if float(item[0]) > price:
                price = float(item[0])
                quantity = float(item[1])
        return {'price':float_to_str(price),'price_usd':float_to_str(float(price)*self.get_btc_usd_price()),'quantity':quantity,'total':(quantity*price),'total_usd':(quantity*price*self.get_btc_usd_price())}

    def lowest_ask(self, symbol):
        asks = self.depth(symbol)['asks']
        #print(asks)
        quantity = float(0)
        price = float(999999)
        for item in asks:
            if float(item[0]) < price:
                price = float(item[0])
                quantity = float(item[1])
        return {'price':float_to_str(price),'price_usd':float_to_str(float(price)*self.get_btc_usd_price()),'quantity':quantity,'total':(quantity*price),'total_usd':(quantity*price*self.get_btc_usd_price())}

    def cost_to_buy_all(self, symbol, depth=500):
        asks = self.depth(symbol, depth)['asks']
        quantity = float(0)
        cost = float(0)
        for item in asks:
            quantity += float(item[1])
            cost += (float(item[0]) * float(item[1]))
        return {'cost':cost,'quantity':quantity,'cost_usd':(cost*self.get_btc_usd_price())}

    def balance(self,symbol=None):
        if symbol is not None:
            symbol = symbol.upper()
        params = {'account':'exchange'}
        data = self.signedRequest(method="POST",path ='trade/balance',params=params)['balance']
        available = []
        frozen = []
        total = []
        for item in data:
            if symbol is not None:
                if item['asset'] == symbol:
                    return item
                key = item['asset']
                available.append({key:item['available']})
                frozen.append({key:item['reserved']})
                total.append({key:item['total']})
        tem = {'total':total,'available':available,'frozen':frozen}
        if symbol is not None:
            print("ERROR")
            return
        return tem

    def trade(self,trade_type,price,amount,symbol,retry_count=0): 
        symbol = symbol.replace('_','').lower()
        '''
        trade_type:only buy-limit/sell-limit
        '''
        params = {
                'price':price,
                'quantity':float(amount),
                'symbol':symbol,
                'type':trade_type
        }
        data = self.signedRequest(method="POST",path ='trade/order/place',params=params)#['orderid']
        if 'orderid' not in data:
            if 'description' in data:
                if 'System busy.' in data['description']:
                    if retry_count == 4:
                        print("Trying a random amount")
                        return self.trade(trade_type, price, str(random.randint(1,float(amount))), symbol, retry_count)
                    if retry_count == 5:
                        return data
                    retry_count += 1
                    print("Retrying")
                    return self.trade(trade_type, price, amount, symbol, retry_count)
            return data
        self.order_list.append(data['orderid'])
        data['price_usd'] = float(self.get_btc_usd_price())*float(params['price'])
        data['total_usd'] = float(data['price_usd'])*float(params['quantity'])
        data['note'] = "This is just a cost estimate, please wait till order is filled to know actual cost"
        return data

    def buy_lowest_ask(self,symbol,amount=None):
        lowest_ask = self.lowest_ask(symbol)
        balance = float(self.balance('btc')['available'])
        if amount is not None:
            order = client.trade('buy-limit',lowest_ask['price'],amount,symbol)
            return order
        if balance is None:
            print("ERROR")
            return
        if balance > float(lowest_ask['total']):
            print("Attempting to buy the full quantity of the lowest ask")
            order = client.trade('buy-limit',lowest_ask['price'],lowest_ask['quantity'],symbol)
            return order
        amount = math.floor(balance / float(lowest_ask['price']))
        if amount > 0:
            print("Attempting to buy " + float_to_str(amount))
            order = client.trade('buy-limit',lowest_ask['price'],float_to_str(amount),symbol)
            return order
        print("Not able to buy any")
        return

    def buy_highest_ask(self,symbol,amount=None):
        highest_ask = self.find_highest_price(symbol)
        if highest_ask is None:
            print("ERROR")
            return
        balance = float(self.balance('btc')['available'])
        if amount is not None:
            order = client.trade('buy-limit',highest_ask['price'],amount,symbol)
            return order
        if balance is None:
            print("ERROR")
            return
        if balance > float(highest_ask['total']):
            print("Attempting to buy the full quantity of the highest ask")
            order = client.trade('buy-limit',highest_ask['price'],highest_ask['quantity'],symbol)
            return order
        amount = math.floor(balance / float(highest_ask['price']))
        if amount > 0:
            print("Attempting to buy " + float_to_str(amount))
            order = client.trade('buy-limit',highest_ask['price'],float_to_str(amount),symbol)
            return order
        print("Not able to buy any")
        return

    def find_highest_price(self,symbol,amount=float(1)):
        asks = self.depth(symbol, depth=100)['asks']
        quantity = float(0)
        price = float(0)
        for i in range(len(asks)-1, 0, -1):
            order = client.trade('buy-limit',asks[i][0],float_to_str(amount),symbol)
            if "orderid" in order:
                price = float(asks[i][0])
                quantity = float(asks[i][1])
                print("Highest asks available is: " + float_to_str(price))
                print(order)
                return {'price':float_to_str(price),'price_usd':float_to_str(float(price)*self.get_btc_usd_price()),'quantity':quantity,'total':(quantity*price),'total_usd':(quantity*price*self.get_btc_usd_price())}
            if "status" in order:
                if order['description'] is "Out of price limit.":
                    print(float_to_str(asks[i][0]) + " is too high")
        return

    def order_info(self,order_id):
        orderid = order_id.replace('_','')
        params = {'orderid':orderid}
        data = self.signedRequest(method="POST",path ='trade/order/info',params=params)['order']
        return data

    def cancel_order(self,order_id):
        orderid = order_id.replace('_','')
        params = {'orderid':orderid}
        data = self.signedRequest(method="POST",path ='trade/order/cancel',params=params)
        return data

    def cancel_all(self,orderid_list):
        for i in orderid_list:
            self.cancel_order(i)
        return 'Cancel all orders!'

    def open_orders(self,symbol):
        symbol = symbol.replace('_','').lower()
        params = {'symbol':symbol}
        data = self.signedRequest(method="POST",path ='trade/order/open-orders',params=params)['orders']
        if 'result' not in data:
            print("No open orders")
            return data
        for item in data['result']:
            self.order_list.append(item['orderid'])
        return data

    def get_btc_usd_balance(self):
        btc_balance = self.balance('btc')
        btc_balance['usd_equiv'] = float(btc_balance['available'])*float(self.get_btc_usd_price())
        duc_balance = self.balance('duc')
        return {'btc_balance':btc_balance['available'], 'btc_usd':float_to_str(btc_balance['usd_equiv']), 'duc_balance':duc_balance['available']}

    def status(self):
        pass

if __name__ == "__main__":
    apikey = "180401174418572961449"
    secretkey = "09f6e584feec4f309ad2ae46d0244435" 
    default_symbol = 'ducbtc'

    parser = OptionParser(usage="usage: %prog [options]")
    parser.add_option("--print_balance",
            action="store_true", dest="print_balance", default=False,
            help="Print balance of DUC and BTC wallet")
    parser.add_option("--print_lowest_bid", action="store_true", dest="print_lowest_bid", default=False,
            help="Print the lowest bid and the quantity")
    parser.add_option("--print_highest_bid", action="store_true", dest="print_highest_bid", default=False,
            help="Print the highest bid and the quantity")
    parser.add_option("--print_lowest_ask", action="store_true", dest="print_lowest_ask", default=False,
            help="Print the lowest ask and the quantity")
    parser.add_option("--print_highest_ask", action="store_true", dest="print_highest_ask", default=False,
            help="Print the highest ask and the quantity")
    parser.add_option("--print_total_cost", action="store_true", dest="print_total_cost", default=False,
            help="Print the total cost and quantity of supply")
    parser.add_option("--print_ticker", action="store_true", dest="print_ticker", default=False,
            help="Print ticker info")
    parser.add_option("--print_bids", action="store_true", dest="print_bids", default=False,
            help="Print current bids")
    parser.add_option("--print_asks", action="store_true", dest="print_asks", default=False,
            help="Print current asks")
    parser.add_option("--print_open_orders", action="store_true", dest="print_open_orders", default=False,
            help="Print open orders")
    parser.add_option("--cancel_open_orders", action="store_true", dest="cancel_open_orders", default=False,
            help="Cancel open orders")
    parser.add_option("--buy_lowest_ask", action="store_true", dest="buy_lowest_ask", default=False,
            help="Buy the lowest ask and the quantity")
    parser.add_option("--buy_highest_ask", action="store_true", dest="buy_highest_ask", default=False,
            help="Buy the highest ask and the quantity")
    parser.add_option("--find_highest_price", action="store_true", dest="find_highest_price", default=False,
            help="Find the highest price that coins can be bought at, will purchase .001 coin")
    parser.add_option("--api_key", dest="api_key", default="180401174418572961449",
            help="API Key")
    parser.add_option("--maintain_price", dest="maintain_price",
            help="API Key")
    parser.add_option("--buy_limit", dest="buy_limit", 
            help="Buy limit ['price','amount'] or 'price' to buy max")
    parser.add_option("--api_secret", dest="api_secret", default="09f6e584feec4f309ad2ae46d0244435",
            help="API Secret")
    parser.add_option("--symbol", dest="symbol", default=default_symbol,
            help="Trading Pair Symbol")
    parser.add_option("-q", "--quiet", action="store_true", dest="quiet", default=False,
            help="Suppress most messages")

    (options, args) = parser.parse_args()

    client = Client_Coinbene(options.api_key,options.api_secret)
    if options.print_balance:
        print(client.get_btc_usd_balance())
    if options.print_lowest_bid:
        print("Lowest Bid:")
        print(client.lowest_bid(options.symbol))
    if options.print_highest_bid:
        print("Highest Bid:")
        print(client.highest_bid(options.symbol))
    if options.print_bids:
        print("Bids:")
        print(client.depth(options.symbol)['bids'])
    if options.print_lowest_ask:
        print("Lowest Ask:")
        print(client.lowest_ask(options.symbol))
    if options.print_highest_ask:
        print("Highest Ask:")
        print(client.highest_ask(options.symbol))
    if options.print_total_cost:
        print("Total Supply Cost:")
        print(client.cost_to_buy_all(options.symbol))
    if options.print_asks:
        print("Asks:")
        print(client.depth(options.symbol)['asks'])
    if options.buy_limit is not None:
        print("Putting in buy limit")
        print(options.buy_limit)
        if isinstance(options.buy_limit, str):
            amount = float(client.get_btc_usd_balance()['btc_balance'])/float(options.buy_limit) 
            if amount > 0:
                print(client.trade('buy-limit',options.buy_limit,amount,options.symbol))
            else:
                print("ERROR: not enough funds to put in buy-limit")
        else:
            print(client.trade('buy-limit',options.buy_limit[0],options.buy_limit[1],options.symbol))
    if options.buy_lowest_ask:
        print("Buying Lowest Ask:")
        print(client.buy_lowest_ask(options.symbol))
    if options.find_highest_price:
        print("Trying to find the highest asks price")
        print(client.find_highest_price(options.symbol))
    if options.buy_highest_ask:
        print("Buying Highest Ask:")
        print(client.buy_highest_ask(options.symbol))
    if options.cancel_open_orders:
        print("Cancelling Below Orders:")
        print(client.open_orders(options.symbol))
        print(client.cancel_all(client.order_list))
    if options.print_open_orders:
        print(client.open_orders(options.symbol))
    if options.print_ticker:
        print(client.ticker(options.symbol))
    if options.maintain_price is not None:
        print("Attempting to maintain price at " + str(options.maintain_price) + " " + options.symbol)
        while True:
            lowest_ask_price = client.lowest_ask(options.symbol)
            print(lowest_ask_price)
            break
