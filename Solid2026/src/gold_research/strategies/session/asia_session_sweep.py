"""
Asia Session Sweep Strategy.

Hypothesis: The Asian session frequently sweeps pre-session swing highs or lows
(stop-hunting retail participants) before reversing. A 15m candle that wicks
through the marked level but closes back inside signals a Market Structure Shift
(MSS), providing a clean 1:2 R:R entry back into the pre-Asia range.

Original spec: M15 range marking + M1 MSS entry.
Backtesting approximation: 15m only (single-TF). The M1 MSS (close through
structure) is approximated by a 15m candle that wicks past the level but
closes back inside — the smallest granularity available in the live dataset.

Session timing (UTC, approximate EST / UTC-5):
  Range build   : 21:00 – 00:59 UTC  (NY after-hours / pre-Asia consolidation)
  Entry window  : 01:00 – 04:59 UTC  (Asia session / NY 8 PM – midnight ET)
  Expired       : 05:00+ UTC          (no entry → session invalidated)

Entry rules:
  SHORT : bar.high > range_high  AND  bar.close < range_high
            → wick sweeps liquidity above, close rejects → bearish MSS
  LONG  : bar.low  < range_low   AND  bar.close > range_low
            → wick sweeps liquidity below, close rejects → bullish MSS

Stop-loss  : Above sweep wick high (shorts) / below sweep wick low (longs)
             plus a small percentage buffer (sl_buffer_pct).
Take-profit: Fixed R:R from entry (default 1:2).

Invalidation:
  - Candle closes fully outside the range on either side → session expired.
  - UTC hour reaches 05:00 without a valid entry → session expired.
  - Opposite level breached before entry → session expired.
"""
from typing import Optional

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.position import Position

from src.gold_research.strategies.base.exit_base import ExitBase
from src.gold_research.strategies.base.signal_base import SignalBase, SignalIntent
from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig
from src.gold_research.strategies.common.entries import MarketEntryExecutor
from src.gold_research.strategies.common.sizing import DynamicRiskSizer


# ---------------------------------------------------------------------------
# Exit: Fixed Risk:Reward TP / SL
# ---------------------------------------------------------------------------

class FixedRRTPSLExit(ExitBase):
    """
    Exits a position when either the take-profit or stop-loss level is touched,
    checked against bar high/low (intra-bar touch detection).

    Usage:
        exit = FixedRRTPSLExit(rr=2.0)
        exit.arm(entry_price, sl_price, direction)   # called after entry
        exit.should_exit(bar, position)              # called each bar
    """

    def __init__(self, rr: float = 2.0) -> None:
        self.rr = rr
        self.sl_level: Optional[float] = None
        self.tp_level: Optional[float] = None
        self.direction: Optional[int] = None

    def arm(self, entry: float, sl: float, direction: int) -> None:
        """Set TP/SL levels from entry price, stop price and trade direction."""
        risk = abs(entry - sl)
        self.sl_level = sl
        self.direction = direction
        if direction == 1:   # long:  TP above entry
            self.tp_level = entry + self.rr * risk
        else:                # short: TP below entry
            self.tp_level = entry - self.rr * risk

    def disarm(self) -> None:
        """Clear state after a trade exits (TP or SL hit)."""
        self.sl_level = None
        self.tp_level = None
        self.direction = None

    def should_exit(self, bar: Bar, position: Optional[Position] = None) -> bool:
        if self.sl_level is None or position is None:
            return False

        bar_high = float(bar.high)
        bar_low = float(bar.low)

        if self.direction == 1:    # long: SL below, TP above
            if bar_low <= self.sl_level or bar_high >= self.tp_level:
                self.disarm()
                return True
        else:                      # short: SL above, TP below
            if bar_high >= self.sl_level or bar_low <= self.tp_level:
                self.disarm()
                return True

        return False


# ---------------------------------------------------------------------------
# Signal: Pre-Asia Range + Sweep + MSS Detection
# ---------------------------------------------------------------------------

class AsiaSweepSignal(SignalBase):
    """
    Per-session state machine.

    Lifecycle per trading day:
      1. IDLE           : UTC hours 05–20 (London/NY daytime — ignored)
      2. BUILDING RANGE : UTC hours 21–00 (accumulate swing high/low)
      3. ENTRY WINDOW   : UTC hours 01–04 (detect sweep + MSS candle)
      4. EXPIRED        : hour ≥ 05 without trade, or level fully broken
    """

    _RANGE_HOURS = frozenset([21, 22, 23, 0])
    _ENTRY_HOURS = frozenset([1, 2, 3, 4])

    def __init__(self, sl_buffer_pct: float = 0.001) -> None:
        """
        Args:
            sl_buffer_pct: Fractional buffer above wick high (short SL) or
                           below wick low (long SL). Default 0.1% of price.
        """
        self.sl_buffer_pct = sl_buffer_pct

        # Session state — fully reset per session day
        self.session_key: Optional[str] = None
        self.range_high: float = float("-inf")
        self.range_low: float = float("inf")
        self.range_bars_seen: int = 0
        self.range_ready: bool = False
        self.traded_today: bool = False
        self.session_expired: bool = False
        self.in_entry_window: bool = False

        # Metadata from last emitted signal (for exit arming)
        self.last_sl: Optional[float] = None
        self.last_entry: Optional[float] = None
        self.last_direction: Optional[int] = None

    # ------------------------------------------------------------------

    def _compute_session_key(self, dt: pd.Timestamp) -> Optional[str]:
        """
        Map a UTC timestamp to a session-day string.
        Hours 21–23 belong to today; hours 0–4 belong to yesterday.
        Returns None for irrelevant hours (05–20 UTC).
        """
        h = dt.hour
        if h >= 20:
            return dt.strftime("%Y-%m-%d")
        if h < 5:
            return (dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        return None  # daytime — ignored

    def _reset_session(self, key: str) -> None:
        self.session_key = key
        self.range_high = float("-inf")
        self.range_low = float("inf")
        self.range_bars_seen = 0
        self.range_ready = False
        self.traded_today = False
        self.session_expired = False
        self.in_entry_window = False
        self.last_sl = None
        self.last_entry = None
        self.last_direction = None

    # ------------------------------------------------------------------

    def update(self, bar: Bar) -> None:
        """Advance internal state machine for the incoming bar."""
        dt = pd.to_datetime(bar.ts_event, unit="ns", utc=True)
        h = dt.hour
        sk = self._compute_session_key(dt)

        if sk is None:
            return  # Daytime bar — ignore

        if self.session_key != sk:
            self._reset_session(sk)

        bar_high = float(bar.high)
        bar_low = float(bar.low)

        # Accumulate range during pre-Asia consolidation (21:00–00:59 UTC)
        if h in self._RANGE_HOURS:
            self.range_high = max(self.range_high, bar_high)
            self.range_low = min(self.range_low, bar_low)
            self.range_bars_seen += 1
            if self.range_bars_seen >= 2:
                self.range_ready = True

        # Track entry-window state transitions
        if h in self._ENTRY_HOURS:
            self.in_entry_window = True
        elif h >= 5 and self.in_entry_window and not self.traded_today:
            self.session_expired = True

    # ------------------------------------------------------------------

    def generate(self, bar: Bar) -> Optional[SignalIntent]:
        """Return a SignalIntent on sweep + MSS, or None if no setup."""
        if not self.range_ready:
            return None
        if self.traded_today or self.session_expired:
            return None

        dt = pd.to_datetime(bar.ts_event, unit="ns", utc=True)
        if dt.hour not in self._ENTRY_HOURS:
            return None

        bar_high = float(bar.high)
        bar_low = float(bar.low)
        bar_close = float(bar.close)

        # Invalidation: full close outside the range on either side
        if bar_close > self.range_high:
            self.session_expired = True
            return None
        if bar_close < self.range_low:
            self.session_expired = True
            return None

        # --- SHORT: wick sweeps range_high, close rejects below → bearish MSS ---
        if bar_high > self.range_high and bar_close < self.range_high:
            sl = bar_high * (1.0 + self.sl_buffer_pct)
            self.traded_today = True
            self.last_sl = sl
            self.last_entry = bar_close
            self.last_direction = -1
            return SignalIntent(
                direction=-1,
                entry_price=bar_close,
                stop_price=sl,
                metadata={
                    "sweep_level": self.range_high,
                    "range_low": self.range_low,
                    "session": self.session_key,
                },
            )

        # --- LONG: wick sweeps range_low, close rejects above → bullish MSS ---
        if bar_low < self.range_low and bar_close > self.range_low:
            sl = bar_low * (1.0 - self.sl_buffer_pct)
            self.traded_today = True
            self.last_sl = sl
            self.last_entry = bar_close
            self.last_direction = 1
            return SignalIntent(
                direction=1,
                entry_price=bar_close,
                stop_price=sl,
                metadata={
                    "sweep_level": self.range_low,
                    "range_high": self.range_high,
                    "session": self.session_key,
                },
            )

        return None


# ---------------------------------------------------------------------------
# Config and Strategy
# ---------------------------------------------------------------------------

class AsiaSweepConfig(GoldStrategyConfig):
    sl_buffer_pct: float = 0.001  # 0.1% above/below sweep wick for SL
    rr: float = 2.0               # Take-profit at rr × risk distance from entry


class AsiaSweep(GoldStrategy):
    """
    Asia Session Sweep — framework-native NautilusTrader strategy.

    Marks the pre-Asia (21:00–01:00 UTC) 15m range, then during the Asia
    entry window (01:00–05:00 UTC) fires on sweep + MSS rejection candles.
    Exits via fixed R:R TP/SL checked on bar high/low.
    """

    def __init__(self, config: AsiaSweepConfig) -> None:
        super().__init__(config)
        self.cfg = config

    def setup_components(self) -> None:
        self.signal_generator = AsiaSweepSignal(self.cfg.sl_buffer_pct)
        self.entry_logic = MarketEntryExecutor()
        self.exit_logic = FixedRRTPSLExit(self.cfg.rr)
        self.position_sizer = DynamicRiskSizer()

    def update_state(self, bar: Bar) -> None:
        self.signal_generator.update(bar)

    def evaluate_entries(self, bar: Bar) -> None:
        """Override to arm TP/SL exit immediately after order submission."""
        if self.regime_filter and not self.regime_filter.is_active(bar):
            return

        signal = self.signal_generator.generate(bar)
        if signal is None:
            return

        qty = 1.0
        if self.position_sizer:
            qty = self.position_sizer.calculate_size(signal, bar, self)

        if self.entry_logic:
            self.entry_logic.execute(signal, qty, bar, self)
            # Arm exit with TP/SL derived from this signal's entry and stop
            self.exit_logic.arm(signal.entry_price, signal.stop_price, signal.direction)
