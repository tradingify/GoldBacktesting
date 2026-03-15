"""
ICT Event Pipeline — bar-by-bar indicator labeling for XAUUSD research.

Pipeline layers:
  EventRegistry   — tracks active IndicatorEvents across time.
  BarProcessor    — orchestrates multi-timeframe indicator runs and labels
                    each base-TF bar with a ConfluenceResult.

Usage:
    from gold_research.pipeline.bar_processor import BarProcessor
    processor = BarProcessor(bars_dir="D:/.openclaw/GoldBacktesting/bars")
    labels = processor.run(base_tf="M15")
    # labels is a DataFrame: timestamp | open | high | low | close |
    #                         score | direction | fire | combo | events
"""
