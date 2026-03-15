import unittest
from pathlib import Path

from src.gold_research.reports.html_dashboard import HtmlDashboardReport


class TestHtmlDashboardSmoke(unittest.TestCase):
    def test_build_dashboard_outputs_files(self):
        payload = HtmlDashboardReport.build_dashboard()

        dashboard_path = Path(payload["dashboard_path"])
        self.assertTrue(dashboard_path.exists())
        self.assertTrue((dashboard_path.parent / "runs").exists())
        self.assertTrue((dashboard_path.parent / "portfolios").exists())


if __name__ == "__main__":
    unittest.main()
