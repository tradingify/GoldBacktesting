"""Nautilus Engine Adapters."""
from datetime import datetime
from typing import Type
import importlib
import inspect
import pandas as pd

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue, InstrumentId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.objects import Price, Quantity, Money, Currency
from nautilus_trader.model.identifiers import Symbol
from decimal import Decimal
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.config import LoggingConfig

from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.core.config import load_yaml
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.data.datasets.registry import DatasetRegistry
from src.gold_research.data.ingest.bar_builder import df_to_nautilus_bars
from src.gold_research.data.ingest.ib_loader import load_ib_parquet
from src.gold_research.strategies.base.strategy_base import GoldStrategy, GoldStrategyConfig

class ClassLoader:
    """Helper to dynamically instantiate python classes from string paths."""
    
    @staticmethod
    def load_strategy_class(class_path: str) -> Type[GoldStrategy]:
        """
        Dynamically loads a strategy class.
        Example path: 'src.gold_research.strategies.trend.donchian_breakout.DonchianBreakout'
        """
        try:
            module_path, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            if not issubclass(cls, GoldStrategy):
                raise TypeError(f"Class '{class_name}' must inherit from GoldStrategy.")
            return cls
        except Exception as e:
            raise RuntimeError(f"Failed to load strategy class '{class_path}': {str(e)}")

    @staticmethod
    def load_strategy_config_class(strategy_class: Type[GoldStrategy]) -> Type[GoldStrategyConfig] | None:
        """Infer the strategy config class from the strategy constructor annotation."""
        try:
            signature = inspect.signature(strategy_class.__init__)
        except (TypeError, ValueError):
            return None
        config_param = signature.parameters.get("config")
        if config_param is None:
            return None
        annotation = config_param.annotation
        if annotation is inspect.Signature.empty:
            return None
        if isinstance(annotation, type) and issubclass(annotation, GoldStrategyConfig):
            return annotation
        return None

class NautilusAdapter:
    """Isolates Nautilus Boilerplate."""

    @staticmethod
    def _data_config() -> dict:
        """Load global data defaults once per adapter call site."""
        return load_yaml(ProjectPaths.CONFIG_GLOBAL / "data.yaml")

    @staticmethod
    def infer_timeframe(spec: ExperimentSpec) -> str:
        """Resolve the timeframe for the run from params or registered dataset metadata."""
        timeframe = spec.strategy_params.get("timeframe")
        if timeframe:
            return str(timeframe)

        manifest = DatasetRegistry().get_manifest(spec.dataset.manifest_id)
        if manifest and manifest.timeframe:
            return manifest.timeframe

        manifest_id = spec.dataset.manifest_id.lower()
        timeframe_map = {
            "1_min": "1m",
            "5_mins": "5m",
            "15_mins": "15m",
            "30_mins": "30m",
            "1_hour": "1h",
            "4_hours": "4h",
            "1_day": "1d",
            "h1": "1h",
            "h4": "4h",
            "m5": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        for key, value in timeframe_map.items():
            if key in manifest_id:
                return value
        return "5m"

    @staticmethod
    def _window_mask(df: pd.DataFrame, start_time: str | None, end_time: str | None) -> pd.Series:
        """Build a timestamp mask for a dataframe with a UTC datetime column."""
        mask = pd.Series(True, index=df.index)
        if start_time:
            mask &= df["datetime"] >= pd.Timestamp(start_time)
        if end_time:
            mask &= df["datetime"] <= pd.Timestamp(end_time)
        return mask

    @classmethod
    def slice_dataframe_to_window(cls, df: pd.DataFrame, spec: ExperimentSpec) -> pd.DataFrame:
        """Apply the run's start and end timestamps to a bar dataframe."""
        if df.empty or "datetime" not in df.columns:
            return df
        mask = cls._window_mask(df, spec.dataset.start_time, spec.dataset.end_time)
        return df.loc[mask].copy()
    
    @staticmethod
    def create_engine(spec: ExperimentSpec) -> BacktestEngine:
        """
        Constructs a fresh Nautilus Engine preconfigured for the experiment.
        In V1, we simulate a generic venue (SIM).
        """
        config = NautilusAdapter._data_config()
        log_level = config.get("nautilus_engine", {}).get("log_level", "ERROR")
        engine_config = BacktestEngineConfig(
            trader_id="BACKTESTER-001",
            logging=LoggingConfig(log_level=log_level)
        )
        engine = BacktestEngine(config=engine_config)
        
        # Extract venue from the instrument string (e.g. XAUUSD-IDEALPRO-USD -> IDEALPRO or SIM)
        venue_str = spec.dataset.instrument_id.split('-')[1] if '-' in spec.dataset.instrument_id else "SIM"
        venue = Venue(venue_str)
        engine.add_venue(
            venue=venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            base_currency=None,
            starting_balances=[Money.from_str(f"{spec.risk.starting_capital} USD")]
            
        )
        return engine
        
    @staticmethod
    def add_instrument(engine: BacktestEngine, instrument_id_str: str):
        """Build the configured XAUUSD instrument definition for Nautilus."""
        config = NautilusAdapter._data_config()
        defaults = config.get("defaults", {})
        token = instrument_id_str.split('-')[0] # e.g. XAUUSD
        venue_str = instrument_id_str.split('-')[1] if '-' in instrument_id_str else "SIM"
        
        instrument_id = InstrumentId(Symbol(token), Venue(venue_str))
        price_precision = int(defaults.get("price_precision", 2))
        price_increment = float(defaults.get("tick_size", 0.01))
        size_precision = int(defaults.get("size_precision", 0))
        size_increment = int(defaults.get("size_increment", 1))
        max_quantity = int(defaults.get("max_quantity", 1000000))
        min_quantity = int(defaults.get("min_quantity", 1))
        base_currency = defaults.get("base_currency", token[:3] if len(token) >= 6 else token)
        quote_currency = defaults.get("quote_currency", token[3:] if len(token) >= 6 else "USD")
        
        instrument = CurrencyPair(
            instrument_id=instrument_id,
            raw_symbol=Symbol(token),
            base_currency=Currency.from_str(base_currency),
            quote_currency=Currency.from_str(quote_currency),
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=Price(price_increment, price_precision),
            size_increment=Quantity.from_int(size_increment),
            multiplier=Quantity.from_int(1),
            lot_size=Quantity.from_int(size_increment),
            max_quantity=Quantity.from_int(max_quantity),
            min_quantity=Quantity.from_int(min_quantity),
            margin_init=Decimal("0"),
            margin_maint=Decimal("0"),
            maker_fee=Decimal("0"),
            taker_fee=Decimal("0"),
            ts_event=0,
            ts_init=0
        )
        
        engine.add_instrument(instrument)
        return instrument
        
    @staticmethod
    def load_data(engine: BacktestEngine, spec: ExperimentSpec):
        """
        Points Nautilus at the requested parquet dataset catalog.
        Warning: Time boundaries should be rigidly enforced here.
        """
        catalog_path = ProjectPaths.DATA_CATALOG
        token = spec.dataset.instrument_id.split('-')[0]
        venue_str = spec.dataset.instrument_id.split('-')[1] if '-' in spec.dataset.instrument_id else "SIM"

        if catalog_path.exists():
            catalog = ParquetDataCatalog(str(catalog_path))
            instrument_id = InstrumentId(Symbol(token), Venue(venue_str))
            bars = catalog.bars(instrument_id=instrument_id)
            bars_list = list(bars)
            if spec.dataset.start_time or spec.dataset.end_time:
                start_ns = pd.Timestamp(spec.dataset.start_time).value if spec.dataset.start_time else None
                end_ns = pd.Timestamp(spec.dataset.end_time).value if spec.dataset.end_time else None
                filtered_bars = []
                for bar in bars_list:
                    ts_event = getattr(bar, "ts_event", None)
                    if start_ns is not None and ts_event is not None and ts_event < start_ns:
                        continue
                    if end_ns is not None and ts_event is not None and ts_event > end_ns:
                        continue
                    filtered_bars.append(bar)
                bars_list = filtered_bars
            if bars_list:
                engine.add_data(bars_list)
                return

        manifest = DatasetRegistry().get_manifest(spec.dataset.manifest_id)
        if not manifest or not manifest.source_files:
            raise FileNotFoundError(f"Missing Nautilus Catalog at: {catalog_path} and no registered dataset source files for {spec.dataset.manifest_id}")

        parquet_path = manifest.source_files[0]["path"]
        df = load_ib_parquet(parquet_path)
        df = NautilusAdapter.slice_dataframe_to_window(df, spec)
        timeframe = manifest.timeframe or NautilusAdapter.infer_timeframe(spec)
        price_precision = int(NautilusAdapter._data_config().get("defaults", {}).get("price_precision", 2))
        bars = df_to_nautilus_bars(df, token, venue_str, timeframe, price_precision=price_precision)
        engine.add_data(bars)
