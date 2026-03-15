"""
Portfolio Card Report Generator.

Generates a macro tearsheet summarizing the aggregate metrics of a multi-strategy
synthetic portfolio.
"""
from typing import Dict, Any, List
import os
from datetime import datetime, UTC

from src.gold_research.core.paths import ProjectPaths

class PortfolioCardReport:
    """Formats and exports a Macro Portfolio Performance Summary."""
    
    @staticmethod
    def generate_markdown(portfolio_id: str, macro_metrics: Dict[str, Any], constituent_runs: List[str]) -> str:
        """
        Builds the markdown for the blended logic bucket.
        """
        sharpe = macro_metrics.get("portfolio_sharpe", 0.0)
        mdd = macro_metrics.get("portfolio_max_drawdown", 0.0)
        final_eq = macro_metrics.get("portfolio_final_value", 0.0)
        
        runs_list = "\n".join([f"- `{run}`" for run in constituent_runs])
        
        md = f"""# Portfolio Tearsheet: {portfolio_id}
Generated on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}

## 🌍 Macro Performance (Synthetic)
- **Final Account Value**: ${final_eq:,.2f}
- **Blended Sharpe Ratio**: {sharpe:.2f}
- **Blended Max Drawdown**: {mdd * 100:.2f}%

## 🧬 Constituent Sub-Strategies ({len(constituent_runs)})
{runs_list}

---
*Note: This report assumes 0 correlation penalty and execution on a shared $100k capital base.*
"""
        return md
        
    @staticmethod
    def save_report(portfolio_id: str, markdown_content: str):
        reports_dir = ProjectPaths.DATA / "manifests" / "reports" / "portfolios"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = reports_dir / f"{portfolio_id}_macro.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        return str(filepath)
