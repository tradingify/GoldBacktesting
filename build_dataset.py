"""
HistData M1 → Full Dataset Builder
===================================
1. Parse HistData CSVs (2024 + 2025)
2. Merge into single M1 dataset
3. Resample to M5, M15, M30, H1, H4, D1
4. Filter to Feb 2024 → Feb 2026 (2 years)
5. Split into in-sample / out-of-sample / forward-test
6. Save as parquet in organized folder structure
7. Full QC report

Output: D:\.openclaw\GoldBacktesting\bars\
"""

import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────
RAW_DIR = Path(r"D:\.openclaw\GoldBacktesting\histdata_raw")
BARS_DIR = Path(r"D:\.openclaw\GoldBacktesting\bars")

# Date boundaries (inclusive)
FULL_START = pd.Timestamp("2024-02-01", tz="UTC")
FULL_END   = pd.Timestamp("2026-01-31 23:59:59", tz="UTC")

# Split boundaries
IS_START  = pd.Timestamp("2024-02-01", tz="UTC")
IS_END    = pd.Timestamp("2025-04-30 23:59:59", tz="UTC")  # 15 months

OOS_START = pd.Timestamp("2025-05-01", tz="UTC")
OOS_END   = pd.Timestamp("2025-08-31 23:59:59", tz="UTC")  # 4 months

FWD_START = pd.Timestamp("2025-09-01", tz="UTC")
FWD_END   = pd.Timestamp("2026-01-31 23:59:59", tz="UTC")  # 5 months

# Timeframe resampling rules
RESAMPLE_MAP = {
    "xauusd_1_min":    None,  # base — no resampling
    "xauusd_5_mins":   "5min",
    "xauusd_15_mins":  "15min",
    "xauusd_30_mins":  "30min",
    "xauusd_1_hour":   "1h",
    "xauusd_4_hours":  "4h",
    "xauusd_1_day":    "1D",
}

SPLIT_FOLDERS = {
    "in-sample":       (IS_START, IS_END),
    "out-of-sample":   (OOS_START, OOS_END),
    "forward-test":    (FWD_START, FWD_END),
}


def load_histdata_csv(filepath: Path) -> pd.DataFrame:
    """Parse HistData MT format CSV."""
    df = pd.read_csv(
        filepath,
        header=None,
        names=["date", "time", "open", "high", "low", "close", "volume"],
    )
    # Parse datetime: "2024.01.01" + "18:00"
    df["datetime"] = pd.to_datetime(
        df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M"
    )
    df = df.drop(columns=["date", "time"])
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    df["datetime"] = df["datetime"].dt.tz_localize("UTC")
    return df


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample M1 OHLCV to higher timeframe."""
    df_idx = df.set_index("datetime")
    resampled = df_idx.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])
    resampled = resampled.reset_index()
    return resampled


def qc_report(name: str, df: pd.DataFrame) -> dict:
    """Generate QC metrics for a dataset."""
    gaps = df["datetime"].diff().dt.total_seconds()
    return {
        "name": name,
        "rows": len(df),
        "start": str(df["datetime"].iloc[0]),
        "end": str(df["datetime"].iloc[-1]),
        "duplicates": int(df["datetime"].duplicated().sum()),
        "null_open": int(df["open"].isna().sum()),
        "null_close": int(df["close"].isna().sum()),
        "price_min": round(float(df["low"].min()), 2),
        "price_max": round(float(df["high"].max()), 2),
        "zero_range_bars": int((df["high"] == df["low"]).sum()),
        "negative_bars": int((df["close"] < 0).sum()),
    }


def main():
    print("=" * 70)
    print("  HISTDATA M1 → FULL DATASET BUILDER")
    print("=" * 70)

    # ── Step 1: Load raw CSVs ───────────────────────────────────────
    print("\n[1/6] Loading HistData CSVs...")
    csv_2024 = RAW_DIR / "2024" / "DAT_MT_XAUUSD_M1_2024.csv"
    csv_2025 = RAW_DIR / "2025" / "DAT_MT_XAUUSD_M1_2025.csv"

    df_2024 = load_histdata_csv(csv_2024)
    print(f"  2024: {len(df_2024):,} bars  ({df_2024['datetime'].iloc[0]} -> {df_2024['datetime'].iloc[-1]})")

    df_2025 = load_histdata_csv(csv_2025)
    print(f"  2025: {len(df_2025):,} bars  ({df_2025['datetime'].iloc[0]} -> {df_2025['datetime'].iloc[-1]})")

    # ── Step 2: Merge + deduplicate ─────────────────────────────────
    print("\n[2/6] Merging and deduplicating...")
    df_m1 = pd.concat([df_2024, df_2025], ignore_index=True)
    before_dedup = len(df_m1)
    df_m1 = df_m1.drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    after_dedup = len(df_m1)
    print(f"  Before dedup: {before_dedup:,}  After: {after_dedup:,}  Removed: {before_dedup - after_dedup:,}")

    # ── Step 3: Filter to Feb 2024 → Jan 2026 ──────────────────────
    print("\n[3/6] Filtering to target range (Feb 2024 -> Jan 2026)...")
    df_m1 = df_m1[(df_m1["datetime"] >= FULL_START) & (df_m1["datetime"] <= FULL_END)].reset_index(drop=True)
    print(f"  Filtered: {len(df_m1):,} bars")
    print(f"  Range: {df_m1['datetime'].iloc[0]} -> {df_m1['datetime'].iloc[-1]}")

    # ── Step 4: Build all timeframes ────────────────────────────────
    print("\n[4/6] Building all timeframes from M1...")
    datasets = {}
    for name, rule in RESAMPLE_MAP.items():
        if rule is None:
            datasets[name] = df_m1.copy()
            print(f"  {name}: {len(datasets[name]):,} bars (base M1)")
        else:
            datasets[name] = resample_ohlcv(df_m1, rule)
            print(f"  {name}: {len(datasets[name]):,} bars (resampled from M1)")

    # ── Step 5: Split into folders ──────────────────────────────────
    print("\n[5/6] Splitting into folders...")
    for folder, (start, end) in SPLIT_FOLDERS.items():
        folder_path = BARS_DIR / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"\n  [{folder}] {start.date()} -> {end.date()}")
        for name, df in datasets.items():
            split = df[(df["datetime"] >= start) & (df["datetime"] <= end)].reset_index(drop=True)
            # Store datetime as string in IB format for compatibility
            split_out = split.copy()
            split_out["datetime"] = split_out["datetime"].dt.strftime("%Y%m%d  %H:%M:%S")
            out_path = folder_path / f"{name}.parquet"
            split_out.to_parquet(str(out_path), index=False)
            size_kb = out_path.stat().st_size // 1024
            print(f"    {name}.parquet: {len(split):,} bars  ({size_kb} KB)")

    # ── Step 6: QC Report ───────────────────────────────────────────
    print("\n[6/6] Quality Control Report")
    print("=" * 70)

    all_qc = []
    for folder, (start, end) in SPLIT_FOLDERS.items():
        print(f"\n  === {folder.upper()} ({start.date()} -> {end.date()}) ===")
        for name in RESAMPLE_MAP.keys():
            df = datasets[name]
            split = df[(df["datetime"] >= start) & (df["datetime"] <= end)].reset_index(drop=True)
            if len(split) == 0:
                print(f"    {name}: EMPTY!")
                continue
            qc = qc_report(f"{folder}/{name}", split)
            all_qc.append(qc)
            issues = []
            if qc["duplicates"] > 0:
                issues.append(f"DUPES={qc['duplicates']}")
            if qc["null_open"] > 0 or qc["null_close"] > 0:
                issues.append(f"NULLS")
            if qc["negative_bars"] > 0:
                issues.append(f"NEGATIVE PRICES")
            if qc["zero_range_bars"] / max(1, qc["rows"]) > 0.10:
                issues.append(f"HIGH ZERO-RANGE ({qc['zero_range_bars']}/{qc['rows']})")

            status = "PASS" if not issues else f"WARN: {', '.join(issues)}"
            print(f"    {name}: {qc['rows']:>8,} bars  ${qc['price_min']:,.0f}-${qc['price_max']:,.0f}  [{status}]")

    # Final summary
    total_files = len(RESAMPLE_MAP) * len(SPLIT_FOLDERS)
    total_bars = sum(q["rows"] for q in all_qc)
    print(f"\n{'=' * 70}")
    print(f"  DONE: {total_files} files generated across {len(SPLIT_FOLDERS)} folders")
    print(f"  Total bars: {total_bars:,}")
    print(f"  Output: {BARS_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
