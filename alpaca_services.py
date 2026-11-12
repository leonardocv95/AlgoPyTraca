
import os

from dotenv import load_dotenv

from alpaca.trading.client import TradingClient

from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    TrailingStopOrderRequest,
    ReplaceOrderRequest,
    GetOrdersRequest,
    ClosePositionRequest,
    TakeProfitRequest,
    StopLossRequest
)

from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    QueryOrderStatus,
    OrderClass
)


load_dotenv()


class AlpacaService:

    def __init__(self):

        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not api_key or not secret_key:
            raise ValueError("Alpaca API credentials are missing.")

        self.client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper
        )

    # -----------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------

    @staticmethod
    def _to_dict(data):

        if isinstance(data, list):
            return [AlpacaService._to_dict(item) for item in data]

        if hasattr(data, "model_dump"):
            return data.model_dump(mode="json")

        return data

    @staticmethod
    def _time_in_force(value):
        return TimeInForce(value.lower())

    def _submit(self, request):
        result = self.client.submit_order(order_data=request)
        return self._to_dict(result)

    def _positions(self):
        return self.client.get_all_positions()

    def _find_position(self, symbol):
        symbol = symbol.upper()

        for position in self._positions():
            if position.symbol == symbol:
                return position

        return None

    # -----------------------------------------
    # BUY / SELL
    # -----------------------------------------

    def buy(self, symbol, qty, time_in_force="day"):
        """Buy shares at market price."""

        request = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=self._time_in_force(time_in_force)
        )

        return self._submit(request)

    def sell(self, symbol, qty, time_in_force="day"):
        """Sell shares from an existing long position."""

        position = self._find_position(symbol)

        if not position or position.side != "long":
            raise ValueError(f"No long position found for {symbol}.")

        if float(qty) > abs(float(position.qty)):
            raise ValueError("Sell quantity exceeds your long position.")

        request = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=self._time_in_force(time_in_force)
        )

        return self._submit(request)

    def sell_short(self, symbol, qty, time_in_force="day"):
        """Open a short position."""

        asset = self.client.get_asset(symbol.upper())
        account = self.client.get_account()

        if not account.shorting_enabled:
            raise ValueError("Short selling is not enabled on this account.")

        if not asset.shortable:
            raise ValueError(f"{symbol} is not currently shortable.")

        if self._find_position(symbol):
            raise ValueError(
                f"A position already exists for {symbol}. "
                "Check it before opening a short."
            )

        request = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=self._time_in_force(time_in_force)
        )

        return self._submit(request)

    def buy_to_cover(self, symbol, qty, time_in_force="day"):
        """Buy shares to reduce or close a short position."""

        position = self._find_position(symbol)

        if not position or position.side != "short":
            raise ValueError(f"No short position found for {symbol}.")

        if float(qty) > abs(float(position.qty)):
            raise ValueError("Cover quantity exceeds your short position.")

        request = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=self._time_in_force(time_in_force)
        )

        return self._submit(request)

    # -----------------------------------------
    # BUY / SELL BY DOLLAR AMOUNT
    # -----------------------------------------

    def buy_notional(self, symbol, amount):
        """Buy using a dollar amount instead of share quantity."""

        request = MarketOrderRequest(
            symbol=symbol.upper(),
            notional=amount,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        return self._submit(request)

    def sell_notional(self, symbol, amount):
        """Sell using a dollar amount from a long position."""

        position = self._find_position(symbol)

        if not position or position.side != "long":
            raise ValueError(f"No long position found for {symbol}.")

        request = MarketOrderRequest(
            symbol=symbol.upper(),
            notional=amount,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY
        )

        return self._submit(request)

    # -----------------------------------------
    # LIMIT ORDERS
    # -----------------------------------------

    def limit_order(
        self,
        symbol,
        qty,
        side,
        limit_price,
        time_in_force="day"
    ):

        request = LimitOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide(side.lower()),
            limit_price=limit_price,
            time_in_force=self._time_in_force(time_in_force)
        )

        return self._submit(request)

    # -----------------------------------------
    # STOP ORDERS
    # -----------------------------------------

    def stop_order(
        self,
        symbol,
        qty,
        side,
        stop_price,
        time_in_force="day"
    ):

        request = StopOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide(side.lower()),
            stop_price=stop_price,
            time_in_force=self._time_in_force(time_in_force)
        )

        return self._submit(request)

    # -----------------------------------------
    # STOP LIMIT ORDERS
    # -----------------------------------------

    def stop_limit_order(
        self,
        symbol,
        qty,
        side,
        stop_price,
        limit_price,
        time_in_force="day"
    ):

        request = StopLimitOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide(side.lower()),
            stop_price=stop_price,
            limit_price=limit_price,
            time_in_force=self._time_in_force(time_in_force)
        )

        return self._submit(request)

    # -----------------------------------------
    # TRAILING STOP
    # -----------------------------------------

    def trailing_stop(
        self,
        symbol,
        qty,
        side,
        trail_percent=None,
        trail_price=None
    ):

        if (trail_percent is None) == (trail_price is None):
            raise ValueError(
                "Provide either trail_percent or trail_price, not both."
            )

        request = TrailingStopOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide(side.lower()),
            time_in_force=TimeInForce.GTC,
            trail_percent=trail_percent,
            trail_price=trail_price
        )

        return self._submit(request)

    # -----------------------------------------
    # BRACKET ORDER
    # -----------------------------------------

    def bracket_order(
        self,
        symbol,
        qty,
        side,
        take_profit,
        stop_loss
    ):
        """Submit entry order with take-profit and stop-loss legs."""

        request = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide(side.lower()),
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(
                limit_price=take_profit
            ),
            stop_loss=StopLossRequest(
                stop_price=stop_loss
            )
        )

        return self._submit(request)

    # -----------------------------------------
    # ACCOUNT INFORMATION
    # -----------------------------------------

    def get_account(self):
        return self._to_dict(self.client.get_account())

    def get_buying_power(self):
        account = self.client.get_account()
        return float(account.buying_power)

    def get_account_balance(self):
        account = self.client.get_account()

        return {
            "cash": account.cash,
            "equity": account.equity,
            "buying_power": account.buying_power,
            "portfolio_value": account.portfolio_value
        }

    # -----------------------------------------
    # POSITIONS
    # -----------------------------------------

    def get_positions(self):
        return self._to_dict(self._positions())

    def get_position(self, symbol):
        position = self._find_position(symbol)

        if not position:
            return None

        return self._to_dict(position)

    def close_position(self, symbol, qty=None):
        """Close an entire position or a specified quantity."""

        options = (
            ClosePositionRequest(qty=qty)
            if qty is not None
            else None
        )

        result = self.client.close_position(
            symbol.upper(),
            close_options=options
        )

        return self._to_dict(result)

    def close_all_positions(self, cancel_orders=False):
        result = self.client.close_all_positions(
            cancel_orders=cancel_orders
        )

        return self._to_dict(result)

    # -----------------------------------------
    # ORDER MANAGEMENT
    # -----------------------------------------

    def get_orders(self, status="all"):
        request = GetOrdersRequest(
            status=QueryOrderStatus(status.lower())
        )

        return self._to_dict(
            self.client.get_orders(filter=request)
        )

    def get_order(self, order_id):
        return self._to_dict(
            self.client.get_order_by_id(order_id)
        )

    def cancel_order(self, order_id):
        return self.client.cancel_order_by_id(order_id)

    def cancel_all_orders(self):
        return self._to_dict(self.client.cancel_orders())

    def replace_order(self, order_id, **changes):
        """Modify an existing order using supported Alpaca fields."""

        request = ReplaceOrderRequest(**changes)

        result = self.client.replace_order_by_id(
            order_id,
            order_data=request
        )

        return self._to_dict(result)

    # -----------------------------------------
    # ASSETS / MARKET STATUS
    # -----------------------------------------

    def get_asset(self, symbol):
        return self._to_dict(
            self.client.get_asset(symbol.upper())
        )

    def get_all_assets(self):
        return self._to_dict(
            self.client.get_all_assets()
        )

    def get_market_clock(self):
        return self._to_dict(
            self.client.get_clock()
        )
