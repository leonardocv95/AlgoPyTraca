
# algorithm.py

TEST_QTY = 1


def make_decision(state, symbol):
    """
    Simple alternating BUY / SELL algorithm.

    BUY:
        When no long position exists.

    SELL:
        When a long position exists.

    WAIT:
        When an order is already pending.
    """

    symbol = symbol.upper()

    # Do not submit another order while one is pending.
    open_orders = state.get("open_orders", [])

    for order in open_orders:
        order_symbol = order.get("symbol")

        if (
            order_symbol == symbol
            and order.get("status") in (
                "new",
                "accepted",
                "pending_new",
                "partially_filled",
                "pending_cancel",
                "pending_replace"
            )
        ):
            return {
                "action": "WAIT",
                "reason": "An order is already pending"
            }

    # Find current position.
    positions = state.get("positions", [])

    position = next(
        (
            p for p in positions
            if p.get("symbol") == symbol
        ),
        None
    )

    # No position: BUY.
    if position is None:
        return {
            "action": "BUY",
            "symbol": symbol,
            "qty": TEST_QTY
        }

    current_qty = float(position.get("qty", 0))

    # Short position: do not interfere with it.
    if current_qty < 0:
        return {
            "action": "WAIT",
            "reason": "Short position detected"
        }

    # Long position: SELL one share.
    if current_qty > 0:
        return {
            "action": "SELL",
            "symbol": symbol,
            "qty": min(TEST_QTY, current_qty)
        }

    return {
        "action": "WAIT",
        "reason": "No actionable position"
    }
