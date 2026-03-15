"""
Strategy Card Report Generator.

Transforms a `StrategyScorecard` into a beautiful, standardized Markdown
document that can be reviewed visually or pushed directly to a Wiki.
"""
from typing import Dict, Any, Optional
import os
from datetime import datetime, UTC

from src.gold_research.analytics.scorecards import StrategyScorecard
from src.gold_research.core.paths import ProjectPaths

class StrategyCardReport:
    """Format and deploy a markdown tearsheet for a single run."""
    
    @staticmethod
    def generate_markdown(scorecard: StrategyScorecard, params: Dict[str, Any], notes: str = "") -> str:
        """Formats the data into a markdown template."""
        md = f"""# Strategy Tearsheet: {scorecard.run_id}
Generated on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}
        
## 📈 Core Performance
- **Net Profit**: ${scorecard.total_net_profit:,.2f}
- **Sharpe Ratio**: {scorecard.sharpe:.2f}
- **Sortino Ratio**: {scorecard.sortino:.2f}
- **Max Drawdown**: {scorecard.max_dd_pct * 100:.2f}%
- **Calmar Ratio**: {scorecard.calmar:.2f}

## ⚖️ Trade Statistics
- **Total Executions**: {scorecard.total_trades}
- **Win Rate**: {scorecard.win_rate * 100:.1f}%
- **Profit Factor**: {scorecard.profit_factor:.2f}

## ⚙️ Hyperparameters
```json
{params}
```

## 📝 Analyst Notes
{notes if notes else "No notes provided."}

---
*Status: {scorecard.status}*
"""
        return md
        
    @staticmethod
    def save_report(run_id: str, markdown_content: str):
        """Saves the generated report to the designated run folder."""
        # Find the experiment folder holding this run (Requires querying the registry in a real impl)
        # For direct saving, we'll output to a dedicated reports folder
        reports_dir = ProjectPaths.DATA / "manifests" / "reports" / "strategies"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = reports_dir / f"{run_id}_card.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        return str(filepath)
