import yaml
import os
import asyncio
from driftpy.clearing_house import ClearingHouse
from driftpy.clearing_house_user import ClearingHouseUser
from driftpy.math import market
from driftpy.types import PositionDirection
import time

async def main():
    with open("config.yaml", 'r') as stream:
        try:
            init_config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
        if init_config['build_type'] == "cpp":
            from mmhedge_cpp import MMHedge
            print("cpp build")
        elif init_config['build_type'] == "python":
            from MMHedge import MMHedge
            print("python build")
        else:
            print("ERROR: Invalid build type")

    os.environ['ANCHOR_WALLET'] = os.path.expanduser('~/.config/solana/<YOURWALLET>.json')

    ENV = 'devnet'
    drift_acct = await ClearingHouse.create_from_env(ENV)
    drift_user = ClearingHouseUser(drift_acct, drift_acct.program.provider.wallet.public_key)

    model = None
    while True:
        drift_user_acct_func = drift_user.get_user_account()
        
        # SOL Market is 0?
        perp_pos_func = drift_user.get_user_position(init_config['market_id'])
        perp_pos_func = drift_user.get_user_position(init_config['market_id'])
        perp_value_func = drift_user.get_position_value(init_config['market_id'])
        ## This isnt right needs actual market object not market id
        ## Didn't see a way to access market object in driftpy
        bid_price, ask_price = market.calculate_bid_ask_price(init_config['market_id'])
        
        ## The following 4 values appear to be available in the market AMM
        ## But didn't see the way to access data stored in the market AMM
        #neg_fund_rate = 
        #pos_fund_rate =
        #oracle_price = 
        #volitility = 
        #num_bids = 
        #num_asks =
        
        drift_user_acct = await drift_user_acct_func
        cash = (drift_user_acct.collateral/1e6)
        perp_pos = await perp_pos_func
        perp_value = await perp_value_func

        if model is None:
            model = MMHedge(
                perp_value = perp_value,
                opening_perp_pos = perp_pos,
                opening_hedge_pos = init_config['model_config']['opening_hedge_pos'],
                opening_cash = cash,
                opening_oracle_price = oracle_price,
                maker_fee = init_config['model_config']['maker_fee'],
                taker_fee = init_config['model_config']['taker_fee'],
                warmup = init_config['model_config']['warmup'],
                warmup_risk = init_config['model_config']['warmup_risk'],
                time_delta = init_config['model_config']['time_delta'],
                order_book_risk_cof = init_config['model_config']['order_book_risk_cof']
            )
        else:
            drift_user_acct = await drift_user.get_user_account()
            total_unfilled_order_amount = 0
            for order in drift_user_acct.orders:
                if order.status == 'open' and order.market_index == init_config['market_id']:
                    total_unfilled_order_amount += \
                        order.base_asset_amount - order.base_asset_amount
            
            ## TODO Cancel open orders
            ## As far as I can see there doesn't appear to be a way
            ## to cancel partially filled orders in driftpy
            model.update_returns(total_unfilled_order_amount)
        
        positions = model.update_position(
            oracle_price,
            ask_price,
            bid_price,
            num_bids,
            num_asks,
            perp_pos,
            volitility,
            neg_fund_rate,
            pos_fund_rate,
            perp_value,
            cash
        )

        pos_results = []
        for position in position:
            if position.trade_type != "no_trade":
                pos_results.append(drift_acct.open_position(
                    direction = PositionDirection.LONG() if position.direction == 'long' \
                        else PositionDirection.SHORT(),
                    amount = position.volume,
                    market_index = init_config['market_id'],
                    limit_price = position.price
                ))
        
        time.sleep(model.get_time_delta() - 1)
        await asyncio.gather(*pos_results)

if __name__ == "__main__":
    asyncio.run(main())