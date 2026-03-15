"""
OTE (Optimal Trade Entry) Tracker
===================================
ICT concept: after a directional leg (swing H → swing L or vice versa),
the OTE zone is the 62 %–79 % Fibonacci retracement of that leg.

  Bullish OTE (for longs):
    After a SH → SL drop, price retraces upward.
    OTE = SL + (SH - SL) * [0.62 … 0.79]

  Bearish OTE (for shorts):
    After a SL → SH rally, price retraces downward.
    OTE = SH - (SH - SL) * [0.62 … 0.79]

The output DataFrame mirrors df's index and has per-bar OTE state so it
can be overlaid on any chart or merged with other signal DataFrames.
"""

import numpy as np
import pandas as pd


OTE_LOW  = 0.62
OTE_HIGH = 0.79


# ── swing helpers ─────────────────────────────────────────────────────────────

def _find_swings(highs: np.ndarray, lows: np.ndarray, length: int):
    sh, sl = [], []
    n = len(highs)
    for i in range(length, n - length):
        if (highs[i] == highs[i - length : i + length + 1].max()
                and highs[i] > highs[i - 1]
                and highs[i] > highs[i + 1]):
            sh.append(i)
        if (lows[i] == lows[i - length : i + length + 1].min()
                and lows[i] < lows[i - 1]
                and lows[i] < lows[i + 1]):
            sl.append(i)
    return sh, sl


# ── public API ────────────────────────────────────────────────────────────────

def calculate_retracements(
    df: pd.DataFrame,
    swing_length: int = 10,
) -> pd.DataFrame:
    """
    Calculate OTE retracement state for every bar in df.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close, volume.  DatetimeIndex.
    swing_length : int
        Bars each side to confirm a pivot.

    Returns
    -------
    pd.DataFrame  (same index as df)
        Direction            : int   — 1 (bullish OTE leg) / -1 (bearish) / 0 (none)
        SwingHigh            : float — anchor swing high for current leg
        SwingLow             : float — anchor swing low  for current leg
        OTEHigh              : float — 79 % fib level
        OTELow               : float — 62 % fib level
        FIB705               : float — 70.5 % fib level
        CurrentRetracement   : float — retracement % (0–100) at this bar's close
        DeepestRetracement   : float — deepest retracement % seen so far in the leg
        InOTE                : bool  — True when CurrentRetracement ∈ [62, 79]
    """
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    n      = len(df)

    # output arrays
    direction   = np.zeros(n, dtype=np.int8)
    swing_high  = np.full(n, np.nan)
    swing_low   = np.full(n, np.nan)
    ote_hi      = np.full(n, np.nan)
    ote_lo      = np.full(n, np.nan)
    fib705      = np.full(n, np.nan)
    cur_ret     = np.full(n, np.nan)
    deep_ret    = np.full(n, np.nan)
    in_ote      = np.zeros(n, dtype=bool)

    sh_bars, sl_bars = _find_swings(highs, lows, swing_length)

    # Build unified time-ordered swing event list
    events = sorted(
        [(b, "H", float(highs[b])) for b in sh_bars] +
        [(b, "L", float(lows[b]))  for b in sl_bars],
        key=lambda x: x[0],
    )

    for k in range(len(events) - 1):
        b_a, t_a, l_a = events[k]
        b_b, t_b, l_b = events[k + 1]

        if t_a == "H" and t_b == "L":
            # Bearish leg → bullish retracement opportunity
            # OTE = 62–79% retracement measured FROM the swing high
            sh_lvl, sl_lvl = l_a, l_b
            move = sh_lvl - sl_lvl
            if move <= 0:
                continue
            dir_val = 1
            hi_ote  = sh_lvl - move * OTE_LOW
            lo_ote  = sh_lvl - move * OTE_HIGH
            f705    = sh_lvl - move * 0.705
            deepest = 0.0

            for j in range(b_b, min(b_b + swing_length * 20, n)):
                pct     = (closes[j] - sl_lvl) / move
                pct     = float(np.clip(pct, 0.0, 1.5))
                deepest = max(deepest, pct)

                direction[j]  = dir_val
                swing_high[j] = sh_lvl
                swing_low[j]  = sl_lvl
                ote_hi[j]     = hi_ote
                ote_lo[j]     = lo_ote
                fib705[j]     = f705
                cur_ret[j]    = round(pct * 100, 2)
                deep_ret[j]   = round(deepest * 100, 2)
                in_ote[j]     = lo_ote <= closes[j] <= hi_ote

                if closes[j] > sh_lvl:          # leg invalidated — price took the high
                    break

        elif t_a == "L" and t_b == "H":
            # Bullish leg → bearish retracement opportunity
            # OTE = 62–79% retracement measured FROM the swing low
            sl_lvl, sh_lvl = l_a, l_b
            move = sh_lvl - sl_lvl
            if move <= 0:
                continue
            dir_val = -1
            hi_ote  = sl_lvl + move * OTE_HIGH
            lo_ote  = sl_lvl + move * OTE_LOW
            f705    = sl_lvl + move * 0.705
            deepest = 0.0

            for j in range(b_b, min(b_b + swing_length * 20, n)):
                pct     = (sh_lvl - closes[j]) / move
                pct     = float(np.clip(pct, 0.0, 1.5))
                deepest = max(deepest, pct)

                direction[j]  = dir_val
                swing_high[j] = sh_lvl
                swing_low[j]  = sl_lvl
                ote_hi[j]     = hi_ote
                ote_lo[j]     = lo_ote
                fib705[j]     = f705
                cur_ret[j]    = round(pct * 100, 2)
                deep_ret[j]   = round(deepest * 100, 2)
                in_ote[j]     = lo_ote <= closes[j] <= hi_ote

                if closes[j] < sl_lvl:          # leg invalidated
                    break

    return pd.DataFrame({
        "Direction":          direction,
        "SwingHigh":          swing_high,
        "SwingLow":           swing_low,
        "OTEHigh":            ote_hi,
        "OTELow":             ote_lo,
        "FIB705":             fib705,
        "CurrentRetracement": cur_ret,
        "DeepestRetracement": deep_ret,
        "InOTE":              in_ote,
    }, index=df.index)


# ── demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng   = np.random.default_rng(17)
    n     = 400
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")

    # Create a price series with clear swing structure
    t    = np.linspace(0, 4 * np.pi, n)
    price = 100 + 5 * np.sin(t) + np.cumsum(rng.normal(0, 0.15, n))

    df = pd.DataFrame({
        "open":   price,
        "high":   price + np.abs(rng.normal(0, 0.3, n)),
        "low":    price - np.abs(rng.normal(0, 0.3, n)),
        "close":  price + rng.normal(0, 0.1, n),
        "volume": rng.integers(1000, 5000, n).astype(float),
    }, index=dates)
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"]  = df[["open", "close", "low"]].min(axis=1)

    result = calculate_retracements(df, swing_length=8)

    ote_bars = result[result["InOTE"]]
    bull_ote = result[(result["InOTE"]) & (result["Direction"] ==  1)]
    bear_ote = result[(result["InOTE"]) & (result["Direction"] == -1)]

    print(f"Total bars in OTE zone : {len(ote_bars)}")
    print(f"  Bullish OTE bars     : {len(bull_ote)}")
    print(f"  Bearish OTE bars     : {len(bear_ote)}")
    print()
    print(result[result["InOTE"]].head(10)[
        ["Direction", "SwingHigh", "SwingLow", "OTEHigh", "OTELow",
         "CurrentRetracement", "DeepestRetracement", "InOTE"]
    ].to_string())
