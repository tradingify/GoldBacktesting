"""
FVG (Fair Value Gap) Detector
==============================
ICT concept: 3-candle pattern where the middle candle creates a price gap
that price has not yet returned to fill.

  Bullish FVG : candle[i-1].high < candle[i+1].low  AND candle[i] is bullish
  Bearish FVG : candle[i-1].low  > candle[i+1].high AND candle[i] is bearish

Mitigation:
  Bullish — mitigated when a future bar's low <= fvg.top (price enters gap)
  Bearish — mitigated when a future bar's high >= fvg.bottom (price enters gap)
"""

import numpy as np
import pandas as pd


# ── helpers ──────────────────────────────────────────────────────────────────

def _join_consecutive(fvgs: list[dict]) -> list[dict]:
    """Merge adjacent same-direction FVGs whose price ranges overlap."""
    if not fvgs:
        return fvgs

    merged  = []
    current = fvgs[0].copy()

    for nxt in fvgs[1:]:
        same_dir    = nxt["direction"] == current["direction"]
        overlapping = nxt["bottom"] <= current["top"] and nxt["top"] >= current["bottom"]
        nearby      = nxt["bar"] - current["bar"] <= 4

        if same_dir and overlapping and nearby and not current["mitigated"]:
            current["top"]    = max(current["top"],    nxt["top"])
            current["bottom"] = min(current["bottom"], nxt["bottom"])
            if nxt["mitigated"]:
                current["mitigated"]       = True
                current["mitigated_index"] = nxt["mitigated_index"]
        else:
            merged.append(current)
            current = nxt.copy()

    merged.append(current)
    return merged


# ── public API ────────────────────────────────────────────────────────────────

def detect_fvg(df: pd.DataFrame, join_consecutive: bool = False) -> list[dict]:
    """
    Detect Fair Value Gaps in OHLCV data.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close, volume.  DatetimeIndex.
    join_consecutive : bool
        If True, merge adjacent same-direction FVGs that overlap.

    Returns
    -------
    list of dict
        Keys: index, bar, direction (1=bull/-1=bear),
              top, bottom, mitigated (bool), mitigated_index.
    """
    if len(df) < 3:
        return []

    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    idx    = df.index
    n      = len(df)

    fvgs: list[dict] = []

    for i in range(1, n - 1):
        ph, pl = highs[i - 1], lows[i - 1]
        nh, nl = highs[i + 1], lows[i + 1]
        bull   = closes[i] > opens[i]
        bear   = closes[i] < opens[i]

        if ph < nl and bull:
            fvgs.append({
                "index":           idx[i],
                "bar":             i,
                "direction":       1,
                "top":             float(nl),
                "bottom":          float(ph),
                "mitigated":       False,
                "mitigated_index": None,
            })
        elif pl > nh and bear:
            fvgs.append({
                "index":           idx[i],
                "bar":             i,
                "direction":       -1,
                "top":             float(pl),
                "bottom":          float(nh),
                "mitigated":       False,
                "mitigated_index": None,
            })

    # ── mitigation pass ───────────────────────────────────────────────────────
    for fvg in fvgs:
        start = fvg["bar"] + 2          # earliest bar that can react to the gap
        for j in range(start, n):
            if fvg["direction"] == 1:
                if lows[j] <= fvg["top"]:       # price enters the bullish gap
                    fvg["mitigated"]       = True
                    fvg["mitigated_index"] = idx[j]
                    break
            else:
                if highs[j] >= fvg["bottom"]:   # price enters the bearish gap
                    fvg["mitigated"]       = True
                    fvg["mitigated_index"] = idx[j]
                    break

    if join_consecutive:
        fvgs = _join_consecutive(fvgs)

    return fvgs


# ── demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng = np.random.default_rng(42)
    n   = 300
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")
    price = 100 + np.cumsum(rng.normal(0, 0.4, n))

    df = pd.DataFrame({
        "open":   price + rng.normal(0, 0.1, n),
        "high":   price + np.abs(rng.normal(0, 0.35, n)),
        "low":    price - np.abs(rng.normal(0, 0.35, n)),
        "close":  price + rng.normal(0, 0.1, n),
        "volume": rng.integers(1000, 5000, n).astype(float),
    }, index=dates)
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"]  = df[["open", "close", "low"]].min(axis=1)

    fvgs = detect_fvg(df)
    bull = [f for f in fvgs if f["direction"] ==  1]
    bear = [f for f in fvgs if f["direction"] == -1]
    mit  = [f for f in fvgs if f["mitigated"]]

    print(f"FVGs detected : {len(fvgs)}  ({len(bull)} bull, {len(bear)} bear)")
    print(f"Mitigated     : {len(mit)}")
    print()
    for f in fvgs[:8]:
        label  = "Bull" if f["direction"] == 1 else "Bear"
        status = "MITIGATED" if f["mitigated"] else "active"
        print(f"  {label}  bar={f['bar']:>3}  top={f['top']:.4f}  bot={f['bottom']:.4f}  [{status}]")

    joined = detect_fvg(df, join_consecutive=True)
    print(f"\njoin_consecutive=True -> {len(joined)} FVGs")
