"""
Engulfing Pro K V1 — Python Mirror
====================================
1:1 mirror of Engulfing_Pro_K_V1.pine
Data source: MetaTrader5 (XAUUSD)
Built by Gemini CLI — 2026-03-05
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime


def detect_engulfing(df, engulfing_mode='smart', use_strict_wicks=False,
                     req_color_swap=True, body_size_mult=0.8, gap_tolerance_pct=50):
    """
    Detect engulfing candles mirroring the Pine Script logic exactly.
    
    Modes:
        - 'strict': Standard engulfing — body must fully cover previous body
        - 'smart': Visual reversal — allows gap tolerance
    
    Returns list of signal dicts with time, type, price, mode.
    """
    signals = []

    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    c = df['close'].values
    t = df['time'].values

    for i in range(1, len(df)):
        o0, h0, l0, c0 = o[i], h[i], l[i], c[i]
        o1, h1, l1, c1 = o[i-1], h[i-1], l[i-1], c[i-1]

        # --- Basic Conditions ---
        is_bullish = c0 > o0
        is_bearish = c0 < o0
        prev_bullish = c1 > o1
        prev_bearish = c1 < o1

        # --- Body Sizes ---
        body_size = abs(c0 - o0)
        body_size1 = abs(c1 - o1)

        # --- Previous candle body boundaries ---
        prev_top = max(o1, c1)
        prev_bot = min(o1, c1)

        # --- Gap tolerance zones ---
        tolerance_ratio = gap_tolerance_pct / 100.0
        allowed_bull_open_max = prev_bot + (body_size1 * tolerance_ratio)
        allowed_bear_open_min = prev_top - (body_size1 * tolerance_ratio)

        # --- Color condition ---
        color_bull_ok = (not req_color_swap) or prev_bearish
        color_bear_ok = (not req_color_swap) or prev_bullish

        # --- 1. Strict Engulfing (Standard) ---
        bull_body_strict = is_bullish and color_bull_ok and (c0 >= prev_top) and (o0 <= prev_bot)
        bear_body_strict = is_bearish and color_bear_ok and (o0 >= prev_top) and (c0 <= prev_bot)

        # --- 2. Smart Engulfing (Visual Reversal) ---
        bull_body_smart = is_bullish and color_bull_ok and (c0 > prev_top) and (o0 <= allowed_bull_open_max)
        bear_body_smart = is_bearish and color_bear_ok and (c0 < prev_bot) and (o0 >= allowed_bear_open_min)

        # --- Apply mode selection ---
        is_smart = (engulfing_mode.lower() == 'smart')
        bull_body_base = bull_body_smart if is_smart else bull_body_strict
        bear_body_base = bear_body_smart if is_smart else bear_body_strict

        # --- 3. Wick Engulfing (optional strict override) ---
        bull_wick_strict = is_bullish and color_bull_ok and (c0 >= h1) and (o0 <= l1)
        bear_wick_strict = is_bearish and color_bear_ok and (o0 >= h1) and (c0 <= l1)

        # --- Final engulfing base ---
        raw_bull_engulf = bull_wick_strict if use_strict_wicks else bull_body_base
        raw_bear_engulf = bear_wick_strict if use_strict_wicks else bear_body_base

        # --- Body size multiplier check ---
        size_condition = body_size >= (body_size1 * body_size_mult)

        # --- Final signals ---
        if raw_bull_engulf and size_condition:
            signals.append({
                'time': pd.to_datetime(t[i], unit='s'),
                'type': 'BULLISH',
                'price': float(c0),
                'mode': 'Smart' if is_smart else 'Strict'
            })
        elif raw_bear_engulf and size_condition:
            signals.append({
                'time': pd.to_datetime(t[i], unit='s'),
                'type': 'BEARISH',
                'price': float(c0),
                'mode': 'Smart' if is_smart else 'Strict'
            })

    return signals


def main():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return

    symbol = "XAUUSD"
    timeframes = {
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1
    }

    params = {
        'engulfing_mode': 'smart',
        'use_strict_wicks': False,
        'req_color_swap': True,
        'body_size_mult': 0.8,
        'gap_tolerance_pct': 50
    }

    print(f"=== Engulfing Pro K V1 — {symbol} — {datetime.now()} ===")
    print(f"Mode: {params['engulfing_mode']} | Wick Strict: {params['use_strict_wicks']} | "
          f"Color Swap: {params['req_color_swap']} | Body Mult: {params['body_size_mult']} | "
          f"Gap Tol: {params['gap_tolerance_pct']}%")
    print("-" * 70)

    for tf_name, tf_val in timeframes.items():
        rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, 500)
        if rates is None or len(rates) == 0:
            print(f"\n[{tf_name}] No data available")
            continue

        df = pd.DataFrame(rates)
        signals = detect_engulfing(df, **params)

        print(f"\n[{tf_name}] — {len(signals)} total signals (showing last 10)")
        if not signals:
            print("  No engulfing signals detected.")
        else:
            for sig in signals[-10:]:
                print(f"  {sig['time']} | {sig['type']:7s} | {sig['mode']:6s} | {sig['price']:.2f}")

    mt5.shutdown()
    print("\n✅ Done.")


if __name__ == "__main__":
    main()
