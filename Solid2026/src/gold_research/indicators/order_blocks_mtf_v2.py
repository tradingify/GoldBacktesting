import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import warnings

warnings.filterwarnings("ignore")

# ---- SETTINGS (must match Pine inputs) -----------------------------------
DISP_MULT    = 1.5
SWING_LEN    = 10
MAX_OBS      = 5
MAX_TOUCHES  = 2
MITIGATE_MID = False

# TF timedelta for activation_time overflow fallback
TF_DELTA = {
    "M5":  pd.Timedelta(minutes=5),
    "M15": pd.Timedelta(minutes=15),
    "M30": pd.Timedelta(minutes=30),
    "H1":  pd.Timedelta(hours=1),
    "H4":  pd.Timedelta(hours=4),
    "D1":  pd.Timedelta(days=1),
}

# Bars per TF
TF_BAR_COUNT = {
    "M5":  2000,
    "M15": 1000,
    "M30": 800,
    "H1":  500,
    "H4":  300,
    "D1":  150,
}


class OB:
    def __init__(self, tf, ob_type, top, bot, activation_time, ob_candle_time):
        self.tf              = tf
        self.type            = ob_type
        self.top             = top
        self.bot             = bot
        self.mid             = (top + bot) / 2.0
        self.activation_time = activation_time
        self.ob_candle_time  = ob_candle_time
        self.active          = True
        self.touched         = 0
        self.in_zone         = False

    def __repr__(self):
        t = "Bull" if self.type == 1 else "Bear"
        return (
            f"[{self.tf}] {t} OB | "
            f"Top: {self.top:,.2f} | Bot: {self.bot:,.2f} | Mid: {self.mid:,.2f} | "
            f"Touched: {self.touched}"
        )


def calculate_atr(df, n=14):
    """Wilders ATR - matches Pine ta.atr(14). Fixed 2026-03-06."""
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def fetch_data(tf_str, symbol="XAUUSD"):
    """
    Fetch OHLCV from MT5. Returns df with Open/High/Low/Close indexed by time.
    FIX: Added M5 and M30 (were missing). Per-TF bar counts for depth control.
    """
    tf_map = {
        "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "15m": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1,
    }
    if tf_str not in tf_map:
        return pd.DataFrame()
    count = TF_BAR_COUNT.get(tf_str, 500)
    rates = mt5.copy_rates_from_pos(symbol, tf_map[tf_str], 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)[["time","open","high","low","close","tick_volume"]]
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","tick_volume":"Volume"}, inplace=True)
    return df


def get_potential_obs(df, tf_str):
    """
    Detect potential OBs on a TF dataframe.
    FIX 2026-03-06: activation_time = open of NEXT bar after impulse.
    Pine fires OBs at bar[0] of the new HTF bar (no-lookahead) which equals
    the close of the impulse bar = open of the next HTF bar.
    Using df.index[i] (impulse open) was wrong: caused OBs to be added
    mid-impulse and immediately mitigated, explaining missing H1/H4 near-price OBs.
    """
    if df.empty or len(df) < SWING_LEN + 1:
        return []

    atr    = calculate_atr(df)
    close  = df["Close"]
    open_  = df["Open"]
    high   = df["High"]
    low    = df["Low"]

    impulse_body   = (close - open_).abs()
    is_strong_bull = (close > open_) & (impulse_body > DISP_MULT * atr)
    is_strong_bear = (close < open_) & (impulse_body > DISP_MULT * atr)

    prior_high  = high.rolling(SWING_LEN).max().shift(1)
    prior_low   = low.rolling(SWING_LEN).min().shift(1)
    breaks_high = high > prior_high
    breaks_low  = low  < prior_low

    tf_delta        = TF_DELTA.get(tf_str, pd.Timedelta(hours=1))
    potential_obs   = []
    seen_ob_candles = set()

    for i in range(SWING_LEN + 1, len(df)):
        # FIX: activation at open of NEXT bar, not open of impulse bar
        act_time = df.index[i + 1] if i + 1 < len(df) else df.index[i] + tf_delta

        if is_strong_bear.iloc[i] and breaks_low.iloc[i]:
            for j in range(i - 1, max(0, i - 11), -1):
                if close.iloc[j] > open_.iloc[j]:
                    ob_key = (tf_str, -1, df.index[j])
                    if ob_key not in seen_ob_candles:
                        potential_obs.append(OB(tf_str, -1, float(high.iloc[j]), float(low.iloc[j]), act_time, df.index[j]))
                        seen_ob_candles.add(ob_key)
                    break

        if is_strong_bull.iloc[i] and breaks_high.iloc[i]:
            for j in range(i - 1, max(0, i - 11), -1):
                if close.iloc[j] < open_.iloc[j]:
                    ob_key = (tf_str, 1, df.index[j])
                    if ob_key not in seen_ob_candles:
                        potential_obs.append(OB(tf_str, 1, float(high.iloc[j]), float(low.iloc[j]), act_time, df.index[j]))
                        seen_ob_candles.add(ob_key)
                    break

    return potential_obs


def run_mtf_analysis(symbol="XAUUSD", verbose=False):
    """
    Run full MTF OB analysis, return list of active OBs.
    FIX 2026-03-06:
      - Added M5 and M30 TFs.
      - Switched base chart from M15 to M5 (finer granularity for HTF timing).
      - activation_time fix in get_potential_obs resolves H1/H4 near-price OBs.
      - D1 limited to 150 bars to prevent ancient OBs from persisting.
    """
    if not mt5.initialize():
        print("MT5 init failed. Is MetaTrader 5 running?")
        return []
    try:
        dfs = {}
        for tf_key in ["M5","M15","M30","H1","H4","D1"]:
            dfs[tf_key] = fetch_data(tf_key, symbol)
            if verbose:
                print(f"  [{tf_key}] fetched {len(dfs[tf_key])} bars")

        base_df = dfs["M5"]
        if base_df.empty:
            print("[ERROR] No M5 data.")
            return []

        all_potential_obs = []
        for tf_key, df_tf in dfs.items():
            if not df_tf.empty:
                obs = get_potential_obs(df_tf, tf_key)
                all_potential_obs.extend(obs)
                if verbose:
                    print(f"  [{tf_key}] {len(obs)} potential OBs")

        all_potential_obs.sort(key=lambda x: x.activation_time)

        active_obs = []
        obs_idx    = 0

        for i in range(len(base_df)):
            current_time = base_df.index[i]
            curr_close   = base_df.iloc[i]["Close"]
            curr_high    = base_df.iloc[i]["High"]
            curr_low     = base_df.iloc[i]["Low"]

            while (obs_idx < len(all_potential_obs) and
                   all_potential_obs[obs_idx].activation_time <= current_time):
                new_ob = all_potential_obs[obs_idx]
                obs_idx += 1
                tf_type_obs = [o for o in active_obs if o.tf == new_ob.tf and o.type == new_ob.type]
                if len(tf_type_obs) >= MAX_OBS:
                    oldest = tf_type_obs[0]
                    oldest.active = False
                    active_obs.remove(oldest)
                active_obs.append(new_ob)

            for ob in active_obs[:]:
                price_in_zone = curr_low <= ob.top and curr_high >= ob.bot
                if price_in_zone and not ob.in_zone:
                    ob.touched += 1
                    ob.in_zone  = True
                elif not price_in_zone:
                    ob.in_zone  = False

                mitigated = False
                if ob.type == 1:
                    threshold = ob.mid if MITIGATE_MID else ob.bot
                    if curr_close < threshold:
                        mitigated = True
                else:
                    threshold = ob.mid if MITIGATE_MID else ob.top
                    if curr_close > threshold:
                        mitigated = True

                if MAX_TOUCHES > 0 and ob.touched > MAX_TOUCHES:
                    mitigated = True

                if mitigated:
                    ob.active = False
                    active_obs.remove(ob)

        return active_obs
    finally:
        mt5.shutdown()


def main():
    symbol = "XAUUSD"
    print(f"\nOrder Blocks MTF v2 FIXED -- {symbol}\n")
    active_obs = run_mtf_analysis(symbol, verbose=True)
    if not active_obs:
        print("No active OBs found.")
        return
    print(f"\n--- ACTIVE ORDER BLOCKS ({symbol}) ---")
    for tf in ["M5","M15","M30","H1","H4","D1"]:
        tf_obs = [o for o in active_obs if o.tf == tf]
        if tf_obs:
            print(f"\n[{tf}] ({len(tf_obs)} active)")
            for ob in tf_obs:
                print(f"  {ob}")
    print(f"\nTotal: {len(active_obs)} active OBs")


if __name__ == "__main__":
    main()
