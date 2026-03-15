"""Nautilus Backtest Runner."""
from typing import Dict, Any
import logging

from nautilus_trader.backtest.engine import BacktestEngine
from src.gold_research.backtests.specifications.experiment_spec import ExperimentSpec
from src.gold_research.backtests.engine.adapters import NautilusAdapter, ClassLoader

logger = logging.getLogger("gold_research.backtests.engine")

class NautilusRunner:
    """
    Executes a single specification synchronously.
    """
    
    def __init__(self, spec: ExperimentSpec):
        self.spec = spec
        self.engine: BacktestEngine = None
        
    def setup(self):
        """Bootstraps the Nautilus Engine components based on Spec."""
        logger.info(f"Setting up engine for run: {self.spec.run_id}")
        
        # 1. Boilerplate Engine & Venue Gen
        self.engine = NautilusAdapter.create_engine(self.spec)
        
        # 2. Add structural instrument definition
        NautilusAdapter.add_instrument(self.engine, self.spec.dataset.instrument_id)
        
        # 3. Load underlying tick/bar data into Engine
        # Requires the user to have generated the DataCatalog from the ingest module
        try:
             NautilusAdapter.load_data(self.engine, self.spec)
        except FileNotFoundError as e:
             logger.warning(f"Data loading failed (Catalog Missing?): {e}")
             logger.warning("Engine will run empty and execute no trades.")

        # 4. Instantiate the Strategy Type
        StrategyClass = ClassLoader.load_strategy_class(self.spec.strategy_class_path)
        
        # 5. Hydrate the config dictionary into the correct Pydantic format for that strategy
        # Usually it requires `instrument_id`, `timeframe` plus custom args
        config_payload = {
            "instrument_id": self.spec.dataset.instrument_id,
            "timeframe": NautilusAdapter.infer_timeframe(self.spec),
        }
        config_payload.update(self.spec.strategy_params)

        # 6. Add Strategy module
        try:
             config_class = ClassLoader.load_strategy_config_class(StrategyClass)
             if config_class is not None:
                 strategy_config = config_class(**config_payload)
             else:
                 GenericConfig = type("TempConfig", (), config_payload)
                 strategy_config = GenericConfig()
             strategy_node = StrategyClass(config=strategy_config)
             self.engine.add_strategy(strategy_node)
        except Exception as e:
             logger.error(f"Failed to add strategy: {e}")
             
    def run(self) -> Dict[str, Any]:
        """
        Executes the engine run and extracts results.
        
        Returns:
             Raw snapshot of generated objects (orders, fills, portfolio state).
        """
        if not self.engine:
            self.setup()
            
        logger.info(f"Running Engine for {self.spec.experiment_id}...")
        self.engine.run()
        
        fills_report = self._safe_report("generate_order_fills_report")
        positions_report = self._safe_report("generate_positions_report")

        # Return portfolio artifact state
        try:
            portfolios = self.engine.trader.portfolios()
        except AttributeError:
            portfolios = {}
        
        # Convert internal Nautilus objects to easily queryable artifacts
        return {
            "run_id": self.spec.run_id,
            "portfolios": portfolios,
            "engine": self.engine,
            "fills_report": fills_report,
            "positions_report": positions_report,
            "status": "COMPLETED"
        }

    def _safe_report(self, method_name: str):
        """Return a DataFrame report when the Nautilus API supports it."""
        try:
            report = getattr(self.engine.trader, method_name)()
        except Exception:
            return None
        return report
