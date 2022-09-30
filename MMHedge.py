from dataclasses import dataclass
import numpy as np
import math

SECOND_IN_MIN = 60
MIN_IN_HOUR = 60
HOUR_IN_DAY = 24
DAY_IN_YEAR = 365
RISK_AVERSION_CO = 2
MIN_ORDER_BOOK_UNFILLED = 0.01
MAX_ORDER_BOOK_UNFILLED = 0.03

@dataclass
class Position:
    trade_type: str
    volume: float
    price: float
    direction: str

class MMHedge():
    def __init__(
        self,
        perp_value,
        opening_perp_pos,
        opening_hedge_pos,
        opening_cash,
        opening_oracle_price,
        maker_fee = 0.0002,
        warmup = 100,
        warmup_risk = 0.1, # Percent of cash willing to risk on warmup trades
        time_delta = 60, # Time between trades in seconds
        order_book_risk_cof = 1.5
    ):
        self.perp_value = perp_value
        self.perp_pos = opening_perp_pos
        self.hedge_pos = opening_hedge_pos
        self.cash = opening_cash
        self.opening_oracle_price = opening_oracle_price
        self.oracle_price = opening_oracle_price
        self.maker_fee = maker_fee
        self.warmup = warmup
        self.warmup_risk = warmup_risk
        self.time_delta = time_delta
        self.order_book_risk_cof = order_book_risk_cof
        self.total_order_size = 0
        self.strat_mean = 0
        self.trade_returns = []
        self.unfilled_history = []
        self.curr_wealth = self.__calc_wealth()

    def __calc_wealth(self):
        hedge_value = 0
        if self.hedge_pos > 0:
            hedge_value = self.oracle_price*self.hedge_pos
        else:
            hedge_value = self.hedge_pos*(self.oracle_price - self.opening_oracle_price) * -1
        
        return self.cash + self.perp_value + hedge_value 

    def __calc_mid_market_price(self):
        total_orders = self.num_bids + self.num_asks

        return (self.num_bids*self.bid_price + self.num_asks*self.ask_price) / total_orders 

    def __update_optimal_perp_delta(self):
        x = 1 - (self.ask_price + self.bid_price) / (2*self.oracle_price)
        if x < 0:
            self.optimal_perp_delta = self.hedge_pos \
                * (x - self.neg_fund_rate*self.time_delta / (SECOND_IN_MIN * MIN_IN_HOUR))
        elif x > 0:
            self.optimal_perp_delta = self.hedge_pos \
                * (x + self.pos_fund_rate*self.time_delta / (SECOND_IN_MIN * MIN_IN_HOUR))
        else:
            self.optimal_perp_delta = 0

    def __calc_strat_annualized(self):
        trades_per_year = SECOND_IN_MIN*MIN_IN_HOUR*HOUR_IN_DAY*DAY_IN_YEAR / self.time_delta

        return (1 + self.strat_mean)**trades_per_year

    def __calc_strat_var(self):
        return np.std(np.array(self.trade_returns))

    def __update__inventory_risk(self):
        if len(self.trade_returns) > self.warmup:
            self.inventory_risk = self.__calc_strat_annualized() / (2*self.__calc_strat_var()**2)
        else:
            self.inventory_risk = self.warmup_risk
        

    def __calc_reservation_price(self):
        mid_market_price = self.__calc_mid_market_price()

        self.__update_optimal_perp_delta()
        self.__update__inventory_risk()

        return mid_market_price - self.optimal_perp_delta*self.inventory_risk*self.volitility

    def __update_order_book_risk(self):
        if len(self.unfilled_history) > self.warmup:
            mean_unfilled = np.array(self.unfilled_history).mean()
            if mean_unfilled > MAX_ORDER_BOOK_UNFILLED:
                self.order_book_risk_cof += 0.01
            elif mean_unfilled < MIN_ORDER_BOOK_UNFILLED:
                self.order_book_risk_cof -= 0.01

    def __calc_spread(self):
        self.__update_order_book_risk()

        return self.inventory_risk*self.volitility**2 + \
            2/self.inventory_risk*math.log(1+self.inventory_risk/self.order_book_risk_cof)
    
    def __calc_total_offer(self, reservation_price):
        
        return self.inventory_risk*min(self.cash, 
            self.num_asks*reservation_price, 
            self.num_bids*reservation_price
        )

    def __calc_pos_sizes(self, total_offer_volume, bid_offer_price, ask_offer_price):
        bid_size = total_offer_volume / 2 + self.optimal_perp_delta
        ask_size = total_offer_volume / 2 - self.optimal_perp_delta
        trade_type = 'no_trade'

        if abs(self.optimal_perp_delta) > total_offer_volume:
            trade_type = 'market'
            if self.optimal_perp_delta > 0:
                bid_size = self.optimal_perp_delta
                ask_size = 0
            else:
                ask_size = abs(self.optimal_perp_delta)
                bid_size = 0
                
        elif ask_offer_price - bid_offer_price > self.maker_fee:
            trade_type = 'limit'
                
        elif abs(self.optimal_perp_delta) > 0:
            trade_type = 'limit'
            if self.optimal_perp_delta > 0:
                ask_size = 0
            else:
                bid_size = 0
                
        return trade_type, bid_size, ask_size

    def update_position(
        self, 
        oracle_price,
        ask_price,
        bid_price,
        num_bids,
        num_asks,
        perp_pos,
        volitility,
        neg_fund_rate,
        pos_fund_rate,
    ):     
        self.oracle_price = oracle_price
        self.ask_price = ask_price
        self.bid_price = bid_price
        self.num_bids = num_bids
        self.num_asks = num_asks
        self.perp_pos = perp_pos
        self.volitility = volitility
        self.neg_fund_rate = neg_fund_rate
        self.pos_fund_rate = pos_fund_rate

        reservation_price = self.__calc_reservation_price()
        optimal_spread = self.__calc_spread()

        bid_offer_price = reservation_price - optimal_spread/2
        ask_offer_price = reservation_price + optimal_spread/2

        total_offer_volume = self.__calc_total_offer(reservation_price)

        trade_type, bid_size, ask_size = self.__calc_pos_sizes(
            total_offer_volume, 
            bid_offer_price, 
            ask_offer_price
        )

        short_position = Position(
            trade_type, 
            ask_size,
            ask_offer_price,
            'short' 
        )
        if short_position.trade_type != "no_trade":
            self.total_order_size = ask_size
        else:
            self.total_order_size = 0

        long_position = Position(
            trade_type, 
            bid_size,
            bid_offer_price,
            'long' 
        )
        if long_position.trade_type != "no_trade":
            self.total_order_size += bid_size

        return [short_position, long_position]

    def __update_trade_returns(self):
        new_wealth = self.__calc_wealth()
        trade_return = (new_wealth - self.curr_wealth) / self.curr_wealth
        self.curr_wealth = new_wealth

        self.strat_mean = (self.strat_mean*len(self.trade_returns) + trade_return) / \
            (len(self.trade_returns) + 1)
        self.trade_returns.append(trade_return)

    def update_returns(
        self, 
        unfilled_perp_size,
        perp_value,
        cash
    ):
        self.perp_value = perp_value
        self.cash = cash
        pct_unfilled = unfilled_perp_size / self.total_order_size
        self.unfilled_history.append(pct_unfilled)
        self.__update_trade_returns()

    def get_time_delta(self):
        return self.time_delta