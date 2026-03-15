"""Repository helpers for portfolio persistence."""

from contextlib import closing
from pathlib import Path
import json

from src.gold_research.store.db import get_connection, initialize_database
from src.gold_research.store.runs_repo import utc_now_iso


class PortfolioRepository:
    """Persist generated portfolio definitions and members."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = initialize_database(db_path)

    def upsert_portfolio(
        self,
        *,
        portfolio_id: str,
        portfolio_type: str,
        selection_policy: dict,
        allocation_policy: dict,
    ) -> None:
        with closing(get_connection(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO portfolios (portfolio_id, portfolio_type, selection_policy_json, allocation_policy_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(portfolio_id) DO UPDATE SET
                    portfolio_type=excluded.portfolio_type,
                    selection_policy_json=excluded.selection_policy_json,
                    allocation_policy_json=excluded.allocation_policy_json,
                    created_at=excluded.created_at
                """,
                (
                    portfolio_id,
                    portfolio_type,
                    json.dumps(selection_policy, default=str),
                    json.dumps(allocation_policy, default=str),
                    utc_now_iso(),
                ),
            )
            conn.commit()

    def replace_members(self, portfolio_id: str, members: list[dict]) -> None:
        with closing(get_connection(self.db_path)) as conn:
            conn.execute("DELETE FROM portfolio_members WHERE portfolio_id = ?", (portfolio_id,))
            conn.executemany(
                """
                INSERT INTO portfolio_members (portfolio_id, run_id, weight, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        portfolio_id,
                        member["run_id"],
                        member["weight"],
                        member.get("role", "constituent"),
                        utc_now_iso(),
                    )
                    for member in members
                ],
            )
            conn.commit()
