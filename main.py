
import time
import logging
from datetime import datetime, timezone

from services.alpaca_service import AlpacaService
from services.trading_data_manager import TradingDataManager
from services.market_data_service import MarketDataService

from algorithm import make_decision


# ==================================================
# CONFIGURATION
# ==================================================

SYMBOLS = ["AAPL", "MSFT"]

TIMEFRAME = "1Min"
HISTORICAL_BARS = 250

POLL_INTERVAL = 30          # Seconds between cycles
CLOSED_MARKET_INTERVAL = 120

DRY_RUN = True              # False enables order execution

# Only allow BUY and SELL. Short selling is disabled.
ALLOW_SHORT_SELLING = False


# ==================================================
# LOGGING
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("trading.log", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)


# ==================================================
# INITIALIZE SERVICES
# ==================================================

broker = AlpacaService()

data_manager = TradingDataManager(
    broker=broker
)

market_data = MarketDataService()


# Remember the last processed bar for each symbol.
last_processed_bars = {}


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def get_value(data, key, default=None):
    """Read a field from either a dictionary or SDK object."""

    if isinstance(data, dict):
        return data.get(key, default)

    return getattr(data, key, default)


def get_latest_bar_timestamp(bars):
    """Get the timestamp of the most recent market bar."""

    if bars.empty:
        return None

    if "timestamp" in bars.columns:
        timestamp = bars["timestamp"].iloc[-1]
    else:
        timestamp = bars.index[-1]

    return str(timestamp)


# ==================================================
# MARKET STATUS
# ==================================================

def is_market_open():
    """Check the current Alpaca market clock."""

    clock = broker.get_market_clock()

    return bool(get_value(clock, "is_open", False))


# ==================================================
# REFRESH FINANCIAL DATA
# ==================================================

def refresh_financial_data():

    logger.info("Refreshing account and positions...")

    state = data_manager.refresh_financial_state()

    logger.info(
        "Account equity: %s",
        state["account"].get("equity")
    )

    logger.info(
        "Buying power: %s",
        state["account"].get("buying_power")
    )

    logger.info(
        "Open positions: %s",
        len(state["positions"])
    )

    logger.info("Synchronizing order history...")

    data_manager.sync_order_history()


# ==================================================
# UPDATE MARKET DATA AND INDICATORS
# ==================================================

def update_symbol_data(symbol):
    """
    Retrieve market bars, calculate indicators,
    and save market history.

    Returns True only when a new bar is available.
    """

    logger.info("Updating market data for %s", symbol)

    bars = market_data.get_bars(
        symbol=symbol,
        timeframe=TIMEFRAME,
        limit=HISTORICAL_BARS
    )

    if bars is None or bars.empty:
        logger.warning("No market data received for %s", symbol)
        return False

    latest_timestamp = get_latest_bar_timestamp(bars)

    if latest_timestamp is None:
        return False

    # Do not run the strategy twice on the same bar.
    if last_processed_bars.get(symbol) == latest_timestamp:
        logger.info("No new bar for %s", symbol)
        return False

    data_manager.update_market_data(
        symbol=symbol,
        timeframe=TIMEFRAME,
        bars=bars
    )

    last_processed_bars[symbol] = latest_timestamp

    logger.info("Indicators updated for %s", symbol)

    return True


# ==================================================
# EXECUTE ALGORITHM DECISION
# ==================================================

def execute_decision(decision):
    """
    Execute a decision returned by algorithm.py.

    Expected examples:

        {"action": "BUY", "symbol": "AAPL", "qty": 2}

        {"action": "SELL", "symbol": "AAPL", "qty": 2}

        {"action": "HOLD"}

    Orders require an explicit quantity.
    """

    if not isinstance(decision, dict):
        logger.error("Invalid decision: expected a dictionary")
        return

    action = str(decision.get("action", "WAIT")).upper()

    if action in ("WAIT", "HOLD", "NONE"):
        logger.info("Algorithm decided: %s", action)
        return

    symbol = decision.get("symbol")

    if not symbol:
        logger.error("Decision is missing symbol")
        return

    symbol = str(symbol).upper()

    if action not in ("BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER"):
        logger.warning("Unsupported action: %s", action)
        return

    if action in ("SELL_SHORT", "BUY_TO_COVER") and not ALLOW_SHORT_SELLING:
        logger.warning("Short selling is disabled")
        return

    try:
        qty = float(decision.get("qty", 0))
    except (TypeError, ValueError):
        logger.error("Invalid order quantity")
        return

    if qty <= 0:
        logger.error(
            "Decision for %s has no valid qty. Order not submitted.",
            symbol
        )
        return

    logger.info(
        "Algorithm decision: %s %s shares of %s",
        action,
        qty,
        symbol
    )

    if DRY_RUN:
        logger.warning(
            "DRY RUN: No order submitted. Decision: %s",
            decision
        )
        return

    if action == "BUY":
        result = broker.buy(symbol, qty)

    elif action == "SELL":
        result = broker.sell(symbol, qty)

    elif action == "SELL_SHORT":
        result = broker.sell_short(symbol, qty)

    elif action == "BUY_TO_COVER":
        result = broker.buy_to_cover(symbol, qty)

    logger.info("Order submitted: %s", result)


# ==================================================
# PROCESS ONE SYMBOL
# ==================================================

def process_symbol(symbol):

    # 1. Get new market data and calculate indicators.
    has_new_bar = update_symbol_data(symbol)

    if not has_new_bar:
        return

    # 2. Get the latest financial and indicator state.
    state = data_manager.get_current_state()

    # 3. Ask the algorithm what to do.
    decision = make_decision(
        state=state,
        symbol=symbol
    )

    logger.info("Decision for %s: %s", symbol, decision)

    # 4. Execute or simulate the decision.
    execute_decision(decision)


# ==================================================
# MAIN TRADING CYCLE
# ==================================================

def run_cycle():

    logger.info("Starting trading cycle")

    # Refresh account and positions first.
    refresh_financial_data()

    # Check market status.
    if not is_market_open():
        logger.info("Market is closed")
        return False

    # Process each ticker.
    for symbol in SYMBOLS:

        try:
            process_symbol(symbol)

        except Exception:
            logger.exception(
                "Error processing symbol %s",
                symbol
            )

    logger.info("Trading cycle completed")

    return True


# ==================================================
# EXPORT HISTORY
# ==================================================

def export_history():

    logger.info("Exporting trading history...")

    files = data_manager.export_all()

    for name, path in files.items():
        logger.info("%s exported to %s", name, path)


# ==================================================
# APPLICATION LOOP
# ==================================================

def main():

    logger.info("Trading system starting")
    logger.info("Dry run: %s", DRY_RUN)
    logger.info("Symbols: %s", SYMBOLS)

    # Initial account and order synchronization.
    try:
        refresh_financial_data()
    except Exception:
        logger.exception("Initial financial refresh failed")
        raise

    try:

        while True:

            try:
                market_open = run_cycle()

                if market_open:
                    time.sleep(POLL_INTERVAL)
                else:
                    time.sleep(CLOSED_MARKET_INTERVAL)

            except KeyboardInterrupt:
                raise

            except Exception:
                logger.exception("Trading cycle failed")
                time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")

    finally:

        try:
            # Final synchronization before exiting.
            refresh_financial_data()
            export_history()

        except Exception:
            logger.exception("Final synchronization/export failed")

        logger.info("Trading system stopped")


# ==================================================
# ENTRY POINT
# ==================================================

if __name__ == "__main__":
    main()
