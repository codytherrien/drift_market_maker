#include <vector>
#include <string>
#include <math.h>
#include <numeric>
#include <algorithm>
#include <pybind11/pybind11.h>

namespace py = pybind11;

int SECOND_IN_MIN = 60;
int MIN_IN_HOUR = 60;
int HOUR_IN_DAY = 24;
int DAY_IN_YEAR = 365;
int RISK_AVERSION_CO = 2;
float MIN_ORDER_BOOK_UNFILLED = 0.01;
float MAX_ORDER_BOOK_UNFILLED = 0.03;

struct TradeSizes {
    std::string trade_type;
    float bid_size;
    float ask_size;
};

struct Position {
    std::string trade_type;
    float volume;
    float price;
    std::string direction;
};

class MMHedge
{
private:
    float perp_value;
    float perp_pos;
    float hedge_pos;
    float cash;
    float opening_oracle_price;
    float oracle_price;
    float maker_fee;
    int warmup;
    float warmup_risk;
    int time_delta;
    float order_book_risk_cof;
    float total_order_size;
    std::vector<float> trade_returns;
    std::vector<float> unfilled_history;
    float curr_wealth;
    float ask_price;
    float bid_price;
    float num_bids;
    float num_asks;
    float volitility;
    float neg_fund_rate;
    float pos_fund_rate;
    float optimal_perp_delta;
    float inventory_risk;
    float strat_mean = 0;

    float calc_wealth(void);
    float calc_mid_market_price(void);
    void update_optimal_perp_delta(void);
    float calc_strat_annualized(void);
    float calc_strat_var(void);
    void update_inventory_risk(void);
    float calc_reservation_price(void);
    float calc_mean(std::vector<float> const &vec);
    void update_order_book_risk(void);
    float calc_spread(void);
    float calc_total_offer(float);
    TradeSizes calc_pos_sizes(const float&, const float&, const float&);
    void update_trade_returns(void);
public:
    MMHedge(
        const float &perp_value_,
        const float &opening_perp_price_,
        const float &opening_hedge_pos_,
        const float &opening_cash_,
        const float &opening_oracle_price_,
        const float &maker_fee_,
        const float &warmup_,
        const float &warmup_risk_,
        const int &time_delta_,
        const float &order_book_risk_cof_
    );
    
    std::vector<Position> update_position(
        const float &oracle_price_,
        const float &ask_price_,
        const float &bid_price_,
        const float &num_bids_,
        const float &num_asks_,
        const float &perp_pos_,
        const float &volitility_,
        const float &neg_fund_rate_,
        const float &pos_fund_rate_
    );

    void update_returns(
        const float &unfilled_perp_size,
        const float &perp_value_,
        const float &cash_
    );

    int get_time_delta(void);
};

float MMHedge::calc_wealth() {
    float hedge_value;
    if (hedge_pos > 0) {
        hedge_value = oracle_price*hedge_pos;
    } else {
        hedge_value = hedge_pos*(oracle_price - opening_oracle_price)* -1;
    }

    return cash + perp_value + hedge_value;
}

MMHedge::MMHedge(
    const float &perp_value_,
    const float &opening_perp_price_,
    const float &opening_hedge_pos_,
    const float &opening_cash_,
    const float &opening_oracle_price_,
    const float &maker_fee_,
    const float &warmup_,
    const float &warmup_risk_,
    const int &time_delta_,
    const float &order_book_risk_cof_
) {
    perp_value = perp_value_;
    perp_pos = opening_perp_price_;
    hedge_pos = opening_hedge_pos_;
    cash = opening_cash_;
    opening_oracle_price = opening_oracle_price_;
    oracle_price = opening_oracle_price_;
    maker_fee = maker_fee_;
    warmup = warmup_;
    warmup_risk = warmup_risk_;
    time_delta = time_delta_;
    order_book_risk_cof = order_book_risk_cof_;
    curr_wealth = calc_wealth();
}

float MMHedge::calc_mid_market_price() {
    float total_orders = num_bids + num_asks;

    return (num_bids*bid_price + num_asks*ask_price) / total_orders;
}

void MMHedge::update_optimal_perp_delta() {
    float x = 1 - (ask_price + bid_price) / (2*oracle_price);
    if (x < 0) {
        optimal_perp_delta = hedge_pos \
            * (x - neg_fund_rate*time_delta / (SECOND_IN_MIN*MIN_IN_HOUR));
    } else if (x > 0) {
        optimal_perp_delta = hedge_pos \
            * (x + pos_fund_rate*time_delta / (SECOND_IN_MIN*MIN_IN_HOUR));
    } else {
        optimal_perp_delta = 0;
    }
}

float MMHedge::calc_strat_annualized() {
    float trades_per_year = SECOND_IN_MIN*MIN_IN_HOUR*HOUR_IN_DAY*DAY_IN_YEAR / time_delta;

    return pow((1 + strat_mean), trades_per_year);
}

float MMHedge::calc_strat_var() {
    float accum = 0;
    for (auto const &trade : trade_returns) {
        accum += pow((strat_mean - trade), 2);
    }

    return sqrt(accum / static_cast<float>(trade_returns.size()) - 1.0);
}

void MMHedge::update_inventory_risk() {
    if (static_cast<float>(trade_returns.size()) > warmup) {
        inventory_risk = calc_strat_annualized() / (2*pow(calc_strat_var(), 2));
    } else {
        inventory_risk = warmup_risk;
    }
}

float MMHedge::calc_reservation_price() {
    float mid_market_price = calc_mid_market_price();
    
    update_optimal_perp_delta();
    update_inventory_risk();
    
    return mid_market_price - optimal_perp_delta*inventory_risk*volitility;
}

float MMHedge::calc_mean(std::vector<float> const &vec) {
    if (vec.empty()) {
        return 0;
    }

    float count = static_cast<float>(vec.size());
    return std::reduce(vec.begin(),vec.end()) / count;
}

void MMHedge::update_order_book_risk() {
    if (static_cast<float>(unfilled_history.size()) > warmup) {
        float mean_unfilled = calc_mean(unfilled_history);
        if (mean_unfilled > MAX_ORDER_BOOK_UNFILLED) {
            order_book_risk_cof += 0.01;
        } else if (mean_unfilled < MIN_ORDER_BOOK_UNFILLED) {
            order_book_risk_cof -= 0.01;
        }
    }
}

float MMHedge::calc_spread() {
    update_order_book_risk();

    float gamma_sig = inventory_risk*pow(volitility, 2);
    float gamma_log = log(1+inventory_risk/order_book_risk_cof)*2/inventory_risk;
    
    return gamma_sig + gamma_log;
}

float MMHedge::calc_total_offer(float reservation_price) {
    float risk_cat = std::min({cash, num_asks*reservation_price, num_bids*reservation_price});

    return inventory_risk*risk_cat;
}

TradeSizes MMHedge::calc_pos_sizes(
    const float &total_offer_volume,
    const float &bid_offer_price,
    const float &ask_offer_price
) {
    TradeSizes trade_sizes;
    trade_sizes.bid_size = total_offer_volume/2 + optimal_perp_delta;
    trade_sizes.ask_size = total_offer_volume/2 - optimal_perp_delta;
    trade_sizes.trade_type = "no_trade";

    if (abs(optimal_perp_delta) > total_offer_volume) {
        trade_sizes.trade_type = "market";
        if (optimal_perp_delta > 0) {
            trade_sizes.bid_size = optimal_perp_delta;
            trade_sizes.ask_size = 0;
        } else {
            trade_sizes.ask_size = abs(optimal_perp_delta);
            trade_sizes.bid_size = 0;
        }
    } else if (ask_offer_price - bid_offer_price > maker_fee) {
        trade_sizes.trade_type = "limit";
    } else if (abs(optimal_perp_delta) > 0) {
        trade_sizes.trade_type = "limit";
        if (optimal_perp_delta > 0) {
            trade_sizes.ask_size = 0;
        } else {
            trade_sizes.bid_size = 0;
        }
    }

    return trade_sizes;
}

std::vector<Position> MMHedge::update_position(
    const float &oracle_price_,
    const float &ask_price_,
    const float &bid_price_,
    const float &num_bids_,
    const float &num_asks_,
    const float &perp_pos_,
    const float &volitility_,
    const float &neg_fund_rate_,
    const float &pos_fund_rate_
) {
    oracle_price = oracle_price_;
    ask_price = ask_price_;
    bid_price = bid_price_;
    num_bids = num_bids_;
    num_asks = num_asks_;
    perp_pos = perp_pos_;
    volitility = volitility_;
    neg_fund_rate = neg_fund_rate_;
    pos_fund_rate = pos_fund_rate_;

    float reservation_price = calc_reservation_price();
    float optimal_spread = calc_spread();

    float bid_offer_price = reservation_price - optimal_spread/2;
    float ask_offer_price = reservation_price + optimal_spread/2;

    float total_offer_volume = calc_total_offer(reservation_price);
    TradeSizes trade_sizes = calc_pos_sizes(
        total_offer_volume,
        bid_offer_price,
        ask_offer_price
    );

    Position short_position;
    short_position.trade_type = trade_sizes.trade_type;
    short_position.volume = trade_sizes.ask_size;
    short_position.price = ask_offer_price;
    short_position.direction = "short";

    Position long_position;
    long_position.trade_type = trade_sizes.trade_type;
    long_position.volume = trade_sizes.bid_size;
    long_position.price = bid_offer_price;
    long_position.direction = "long";

    return std::vector<Position>{short_position, long_position};
}

void MMHedge::update_trade_returns() {
    float new_wealth = calc_wealth();
    float trade_return = (new_wealth - curr_wealth) / curr_wealth;
    curr_wealth = new_wealth;

    strat_mean = (strat_mean*static_cast<float>(trade_returns.size()) + trade_return) / \
        (static_cast<float>(trade_returns.size()) + 1);
    trade_returns.push_back(trade_return);
}

void MMHedge::update_returns(
    const float &unfilled_perp_size,
    const float &perp_value_,
    const float &cash_
) {
    perp_value = perp_value_;
    cash = cash_;
    float pct_unfilled = unfilled_perp_size / total_order_size;
    unfilled_history.push_back(pct_unfilled);
    update_trade_returns();
}

int MMHedge::get_time_delta() {
    return time_delta;
}

PYBIND11_MODULE(mmhedge_cpp, m) {
    py::class_<MMHedge>(m, "MMHedge")
        .def(py::init<
            const float &,
            const float &,
            const float &,
            const float &,
            const float &,
            const float &,
            const float &,
            const float &,
            const float &,
            const float &,
            const float &
        >())
        .def("update_position", &MMHedge::update_position)
        .def("update_returns", &MMHedge::update_position)
        .def("get_time_delta", &MMHedge::get_time_delta);
}