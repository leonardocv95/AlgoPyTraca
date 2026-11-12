# services/trading_data_manager.py

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import numpy as np


class TradingDataManager:

    def __init__(self, broker, db_path="data/trading_history.db"):
        """
        broker:
            Instance of your AlpacaService.

        db_path:
            Location of the SQLite database.
        """

        self.broker = broker
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Current information available to the algorithm.
        self.account = {}
        self.positions = []
        self.indicators = {}
        self.last_updated = None

        self._create_tables()

    # --------------------------------------------------
    # DATABASE
    # --------------------------------------------------

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):

        with self._connect() as conn:

            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at TEXT NOT NULL,
                    account_json TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS position_snapshots (
                    snapshot_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    position_json TEXT NOT NULL,
                    PRIMARY KEY (snapshot_id, symbol)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_indicators (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    indicators_json TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS order_history (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    qty TEXT,
                    filled_qty TEXT,
                    filled_avg_price TEXT,
                    status TEXT,
                    submitted_at TEXT,
                    filled_at TEXT,
                    order_json TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    qty TEXT,
                    filled_qty TEXT,
                    filled_avg_price TEXT,
                    status TEXT,
                    submitted_at TEXT,
                    filled_at TEXT,
                    trade_json TEXT NOT NULL
                )
            """)

    @staticmethod
    def _to_dict(value):
        """Convert an SDK model or dictionary into a dictionary."""

        if isinstance(value, dict):
            return value

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")

        return vars(value)

    @staticmethod
    def _json(value):
        """Serialize values that may contain dates or SDK objects."""

        return json.dumps(value, default=str)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    # --------------------------------------------------
    # ACCOUNT AND POSITIONS
    # --------------------------------------------------

    def refresh_financial_state(self):
        """
        Fetch the latest account and positions from Alpaca.

        Saves a historical snapshot and updates the
        in-memory state used by the algorithm.
        """

        account = self._to_dict(self.broker.get_account())

        positions = [
            self._to_dict(position)
            for position in self.broker.get_positions()
        ]

        captured_at = self._now()

        with self._connect() as conn:

            cursor = conn.execute("""
                INSERT INTO account_snapshots (
                    captured_at,
                    account_json
                )
                VALUES (?, ?)
            """, (captured_at, self._json(account)))

            snapshot_id = cursor.lastrowid
            
            
            for position in positions:

                conn.execute("""
                    INSERT INTO position_snapshots (
                        snapshot_id,
                        symbol,
                        position_json
                    )
                    VALUES (?, ?, ?)
                """, (
                    snapshot_id,
                    position.get("symbol"),
                    self._json(position)
                ))

        # Update memory.
        self.account = account
        self.positions = positions
        self.last_updated = captured_at

        return self.get_current_state()

    def get_current_state(self):
        """
        Returns the current financial information
        for the trading algorithm.
        """

        return {
            "account": self.account,
            "positions": self.positions,
            "indicators": self.indicators,
            "last_updated": self.last_updated
        }

    def get_position(self, symbol):
        """Get the current position for one ticker."""

        return next(
            (
                position
                for position in self.positions
                if position.get("symbol") == symbol.upper()
            ),
            None
        )

    # --------------------------------------------------
    # TECHNICAL INDICATORS
    # --------------------------------------------------

    @staticmethod
    def calculate_indicators(bars):
        """
        Calculate technical indicators from OHLCV market data.

        Required columns:
            open, high, low, close, volume

        Returns:
            DataFrame containing original market data
            plus calculated indicators.
        """

        df = bars.copy()

        required = {"open", "high", "low", "close", "volume"}

        missing = required - set(df.columns)

        if missing:
            raise ValueError(
                f"Missing market data columns: {missing}"
            )

        for column in required:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Moving averages
        df["SMA_20"] = close.rolling(20).mean()
        df["SMA_50"] = close.rolling(50).mean()
        df["SMA_200"] = close.rolling(200).mean()

        df["EMA_9"] = close.ewm(
            span=9,
            adjust=False
        ).mean()

        df["EMA_21"] = close.ewm(
            span=21,
            adjust=False
        ).mean()

        df["EMA_50"] = close.ewm(
            span=50,
            adjust=False
        ).mean()

        # RSI - Relative Strength Index
        delta = close.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(
            alpha=1 / 14,
            min_periods=14,
            adjust=False
        ).mean()

        avg_loss = loss.ewm(
            alpha=1 / 14,
            min_periods=14,
            adjust=False
        ).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)

        df["RSI_14"] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = close.ewm(
            span=12,
            adjust=False
        ).mean()

        ema_26 = close.ewm(
            span=26,
            adjust=False
        ).mean()

        df["MACD"] = ema_12 - ema_26

        df["MACD_SIGNAL"] = df["MACD"].ewm(
            span=9,
            adjust=False
        ).mean()

        df["MACD_HIST"] = (
            df["MACD"] - df["MACD_SIGNAL"]
        )

        # Bollinger Bands
        middle = close.rolling(20).mean()
        std = close.rolling(20).std()

        df["BB_MIDDLE"] = middle
        df["BB_UPPER"] = middle + (2 * std)
        df["BB_LOWER"] = middle - (2 * std)

        # ATR - Average True Range
        previous_close = close.shift(1)

        true_range = pd.concat([
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs()
        ], axis=1).max(axis=1)

        df["ATR_14"] = true_range.ewm(
            alpha=1 / 14,
            min_periods=14,
            adjust=False
        ).mean()

        # Stochastic oscillator
        lowest_low = low.rolling(14).min()
        highest_high = high.rolling(14).max()

        denominator = (highest_high - lowest_low).replace(
            0, np.nan
        )

        df["STOCH_K"] = (
            (close - lowest_low) / denominator
        ) * 100

        df["STOCH_D"] = df["STOCH_K"].rolling(3).mean()

        # Volume indicators
        df["VOLUME_SMA_20"] = volume.rolling(20).mean()

        direction = np.sign(close.diff()).fillna(0)

        df["OBV"] = (direction * volume).cumsum()

        # VWAP over the supplied data window
        typical_price = (high + low + close) / 3

        cumulative_volume = volume.cumsum().replace(
            0, np.nan
        )

        df["VWAP"] = (
            (typical_price * volume).cumsum()
            / cumulative_volume
        )

        # Price performance
        df["RETURN_1"] = close.pct_change(1)
        df["RETURN_5"] = close.pct_change(5)
        df["RETURN_20"] = close.pct_change(20)

        return df

    # --------------------------------------------------
    # MARKET DATA AND INDICATOR HISTORY
    # --------------------------------------------------

    def update_market_data(self, symbol, timeframe, bars):
        """
        Calculate indicators and save both raw market
        data and indicators.

        symbol:
            Ticker, such as AAPL.

        timeframe:
            Bar interval, such as 1Min, 5Min, 1Day.

        bars:
            Pandas DataFrame containing OHLCV data.
            It must have a timestamp column or datetime index.
        """

        df = bars.copy()

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                utc=True
            )
        else:
            df["timestamp"] = pd.to_datetime(
                df.index,
                utc=True
            )

        df = df.sort_values("timestamp").reset_index(drop=True)

        result = self.calculate_indicators(df)

        symbol = symbol.upper()

        with self._connect() as conn:

            for _, row in result.iterrows():

                timestamp = row["timestamp"].isoformat()

                # Save original OHLCV data.
                conn.execute("""
                    INSERT OR REPLACE INTO market_bars (
                        symbol, timeframe, timestamp,
                        open, high, low, close, volume
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol,
                    timeframe,
                    timestamp,
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"]
                ))

                # Save calculated indicators.
                indicator_values = {}

                for column in result.columns:
                    if column in {
                        "timestamp", "open", "high",
                        "low", "close", "volume"
                    }:
                        continue

                    value = row[column]

                    indicator_values[column] = (
                        None if pd.isna(value) else float(value)
                    )

                conn.execute("""
                    INSERT OR REPLACE INTO market_indicators (
                        symbol, timeframe, timestamp,
                        indicators_json
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    symbol,
                    timeframe,
                    timestamp,
                    self._json(indicator_values)
                ))

        # Make the latest indicators available in memory.
        latest = result.iloc[-1]

        self.indicators[symbol] = {
            column: (
                None if pd.isna(latest[column])
                else float(latest[column])
            )
            for column in result.columns
            if column not in {
                "timestamp", "open", "high",
                "low", "close", "volume"
            }
        }

        return result

    def get_indicators(self, symbol):
        """Get the latest calculated indicators from memory."""

        return self.indicators.get(symbol.upper(), {})

    # --------------------------------------------------
    # ORDERS AND TRADE HISTORY
    # --------------------------------------------------

    def sync_order_history(self):
        """
        Synchronize Alpaca orders into SQLite.

        Orders with a positive filled quantity are also
        recorded in trade_history.
        """

        orders = self.broker.get_orders(status="all")

        with self._connect() as conn:

            for item in orders:

                order = self._to_dict(item)

                order_id = str(order.get("id"))

                if not order_id or order_id == "None":
                    continue

                order_data = (
                    order_id,
                    order.get("symbol"),
                    order.get("side"),
                    str(order.get("qty")),
                    str(order.get("filled_qty")),
                    str(order.get("filled_avg_price")),
                    order.get("status"),
                    order.get("submitted_at"),
                    order.get("filled_at"),
                    self._json(order)
                )

                conn.execute("""
                    INSERT OR REPLACE INTO order_history (
                        order_id, symbol, side, qty,
                        filled_qty, filled_avg_price,
                        status, submitted_at, filled_at,
                        order_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, order_data)

                filled_qty = order.get("filled_qty")

                try:
                    has_fill = float(filled_qty or 0) > 0
                except (ValueError, TypeError):
                    has_fill = False

                if has_fill:

                    conn.execute("""
                        INSERT OR REPLACE INTO trade_history (
                            order_id, symbol, side, qty,
                            filled_qty, filled_avg_price,
                            status, submitted_at, filled_at,
                            trade_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, order_data)

    def get_trade_history(self):
        """Return saved trades as a Pandas DataFrame."""

        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM trade_history ORDER BY submitted_at",
                conn
            )

    def get_order_history(self):
        """Return all saved orders as a Pandas DataFrame."""

        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM order_history ORDER BY submitted_at",
                conn
            )

    # --------------------------------------------------
    # EXPORT
    # --------------------------------------------------

    def export_trades_csv(self, file_path="exports/trades.csv"):

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self.get_trade_history().to_csv(
            path,
            index=False
        )

        return path

    def export_indicators_csv(
        self,
        symbol,
        timeframe,
        file_path=None
    ):
        """Export historical indicators for one ticker."""

        symbol = symbol.upper()

        if file_path is None:
            file_path = f"exports/{symbol}_{timeframe}_indicators.csv"

        with self._connect() as conn:
            df = pd.read_sql_query("""
                SELECT timestamp, indicators_json
                FROM market_indicators
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp
            """, conn, params=(symbol, timeframe))

        if not df.empty:
            values = df["indicators_json"].apply(json.loads)
            indicators = pd.json_normalize(values)

            df = pd.concat([
                df.drop(columns=["indicators_json"]),
                indicators
            ], axis=1)

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(path, index=False)

        return path