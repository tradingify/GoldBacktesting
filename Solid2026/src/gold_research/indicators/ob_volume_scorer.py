"""
Order Block Volume Scorer
==========================
ICT concept: the last candle before an impulse move that takes out a
swing high or low is the Order Block (OB).  It represents institutional
supply/demand and acts as a magnet for price.

Volume scoring
--------------
  volume_score : sum of volumes of the 3 bars centred on the OB candle
  percentage   : min(bull_vol, bear_vol) / max(bull_vol, bear_vol) * 100

  Higher percentage → more balanced buying/selling → more contested OB →
  stronger magnet effect.

Mitigation
----------
  Bullish OB : mitigated when a future close < OB.bottom
  Bearish OB : mitigated when a future close > OB.top
"""

import numpy as np
import pandas as pd


# ── swing helpers ─────────────────────────────────────────────────────────────

def _find_swings(highs: np.ndarray, lows: np.ndarray, length: int):
    n  = len(highs)
    sh = []
    sl = []
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


def _vol_score(opens, closes, volumes, ob_bar, n):
    """Compute bull/bear vol in a 3-bar window around ob_bar."""
    lo = max(0, ob_bar - 1)
    hi = min(n, ob_bar + 2)
    bull_v = sum(volumes[b] for b in range(lo, hi) if closes[b] >= opens[b])
    bear_v = sum(volumes[b] for b in range(lo, hi) if closes[b] <  opens[b])
    total  = bull_v + bear_v
    pct    = (min(bull_v, bear_v) / max(bull_v, bear_v) * 100
              if max(bull_v, bear_v) > 0 else 0.0)
    return float(total), round(float(pct), 2)


# ── public API ────────────────────────────────────────────────────────────────

def score_ob_volume(
    df: pd.DataFrame,
    swing_length: int = 10,
) -> list[dict]:
    """
    Detect and score Order Blocks by volume contestation.

    Parameters
    ----------
    df : pd.DataFrame
        Columns: open, high, low, close, volume.  DatetimeIndex.
    swing_length : int
        Bars each side for pivot detection.

    Returns
    -------
    list of dict
        Keys: index, bar, direction (1=bull / -1=bear),
              top, bottom, volume_score, percentage,
              mitigated (bool), mitigated_index.
    """
    opens   = df["open"].values
    highs   = df["high"].values
    lows    = df["low"].values
    closes  = df["close"].values
    volumes = df["volume"].values
    idx     = df.index
    n       = len(df)

    sh_bars, sl_bars = _find_swings(highs, lows, swing_length)

    obs:   list[dict] = []
    seen:  set[tuple] = set()
    lookforward = swing_length * 3

    # ── bullish OBs ───────────────────────────────────────────────────────────
    # Impulse: close that breaks above a swing high → last bearish candle before
    for sh in sh_bars:
        for j in range(sh + 1, min(sh + lookforward, n)):
            if closes[j] > highs[sh]:
                # find last bearish candle in the run-up [sh .. j)
                ob_bar = None
                for k in range(j - 1, max(sh - 1, -1), -1):
                    if closes[k] < opens[k]:
                        ob_bar = k
                        break
                if ob_bar is None:
                    ob_bar = max(0, j - 1)

                key = (ob_bar, 1)
                if key in seen:
                    break
                seen.add(key)

                vol_score, pct = _vol_score(opens, closes, volumes, ob_bar, n)
                top    = float(highs[ob_bar])
                bottom = float(lows[ob_bar])

                mitigated, mit_idx = False, None
                for m in range(ob_bar + 1, n):
                    if closes[m] < bottom:
                        mitigated = True
                        mit_idx   = idx[m]
                        break

                obs.append({
                    "index":           idx[ob_bar],
                    "bar":             ob_bar,
                    "direction":       1,
                    "top":             top,
                    "bottom":          bottom,
                    "volume_score":    vol_score,
                    "percentage":      pct,
                    "mitigated":       mitigated,
                    "mitigated_index": mit_idx,
                })
                break

    # ── bearish OBs ───────────────────────────────────────────────────────────
    # Impulse: close that breaks below a swing low → last bullish candle before
    for sl in sl_bars:
        for j in range(sl + 1, min(sl + lookforward, n)):
            if closes[j] < lows[sl]:
                ob_bar = None
                for k in range(j - 1, max(sl - 1, -1), -1):
                    if closes[k] > opens[k]:
                        ob_bar = k
                        break
                if ob_bar is None:
                    ob_bar = max(0, j - 1)

                key = (ob_bar, -1)
                if key in seen:
                    break
                seen.add(key)

                vol_score, pct = _vol_score(opens, closes, volumes, ob_bar, n)
                top    = float(highs[ob_bar])
                bottom = float(lows[ob_bar])

                mitigated, mit_idx = False, None
                for m in range(ob_bar + 1, n):
                    if closes[m] > top:
                        mitigated = True
                        mit_idx   = idx[m]
                        break

                obs.append({
                    "index":           idx[ob_bar],
                    "bar":             ob_bar,
                    "direction":       -1,
                    "top":             top,
                    "bottom":          bottom,
                    "volume_score":    vol_score,
                    "percentage":      pct,
                    "mitigated":       mitigated,
                    "mitigated_index": mit_idx,
                })
                break

    obs.sort(key=lambda x: x["bar"])
    return obs


# ── demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng   = np.random.default_rng(55)
    n     = 400
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")
    price = 100 + np.cumsum(rng.normal(0, 0.4, n))

    df = pd.DataFrame({
        "open":   price,
        "high":   price + np.abs(rng.normal(0, 0.45, n)),
        "low":    price - np.abs(rng.normal(0, 0.45, n)),
        "close":  price + rng.normal(0, 0.12, n),
        "volume": rng.integers(500, 8000, n).astype(float),
    }, index=dates)
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"]  = df[["open", "close", "low"]].min(axis=1)

    obs = score_ob_volume(df, swing_length=6)
    bull_obs = [o for o in obs if o["direction"] ==  1]
    bear_obs = [o for o in obs if o["direction"] == -1]
    mit_obs  = [o for o in obs if o["mitigated"]]

    print(f"Order Blocks : {len(obs)}  ({len(bull_obs)} bull, {len(bear_obs)} bear)")
    print(f"Mitigated    : {len(mit_obs)}")
    print()
    for o in obs[:10]:
        tag    = "Bull" if o["direction"] == 1 else "Bear"
        status = "MITIGATED" if o["mitigated"] else "active"
        print(f"  {tag}  bar={o['bar']:>3}  top={o['top']:.4f}  bot={o['bottom']:.4f}"
              f"  vol={o['volume_score']:.0f}  pct={o['percentage']:.1f}%  [{status}]")
