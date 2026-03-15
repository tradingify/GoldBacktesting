import datetime
from typing import Dict, Optional, Tuple

class SessionModel:
    """
    Handles trading session windows and liquidity sweep detection logic.
    All times are assumed to be in a consistent timezone (e.g., UTC).
    """

    def __init__(self, config: Optional[Dict[str, Dict[str, str]]] = None):
        """
        Initialize with session windows.
        Format: {"SessionName": {"open": "HH:MM", "close": "HH:MM"}}
        """
        self.sessions = config or {
            # All times in UTC — matches Kay V1 / Leviathan Pine script inputs exactly.
            # NOTE: Wadi's TradingView chart is set to UTC+1 (Berlin).
            # The session boxes on chart appear 1hr later than these UTC times — that is correct and expected.
            # Python logic must always compare in UTC.
            # LOCKED session times (Berlin / UTC+1) — confirmed by Wadi on 2026-03-04
            # Sessions are contiguous: Tokyo ends when London starts, London ends when NY starts.
            # These are Berlin local times. Convert to UTC by subtracting 1 hour if needed.
            "Tokyo":   {"open": "03:00", "close": "11:00", "enabled": True},
            "London":  {"open": "11:00", "close": "16:00", "enabled": True},
            "NewYork": {"open": "16:00", "close": "23:00", "enabled": True},
            "Sydney":  {"open": "13:00", "close": "06:00", "enabled": False},  # disabled by default
        }

    def is_in_session(self, dt: datetime.datetime, session_name: str) -> bool:
        """Checks if a given datetime falls within a named session window."""
        if session_name not in self.sessions:
            return False
        
        cfg = self.sessions[session_name]
        open_t = datetime.time.fromisoformat(cfg["open"])
        close_t = datetime.time.fromisoformat(cfg["close"])
        current_t = dt.time()

        if open_t < close_t:
            return open_t <= current_t < close_t
        else:  # Handles sessions crossing midnight
            return current_t >= open_t or current_t < close_t

    def get_active_sessions(self, dt: datetime.datetime) -> list[str]:
        """Returns a list of all sessions active at the given datetime."""
        return [name for name in self.sessions if self.is_in_session(dt, name)]

    @staticmethod
    def detect_sweep(
        current_high: float, 
        current_low: float, 
        current_close: float, 
        target_high: float, 
        target_low: float
    ) -> Optional[str]:
        """
        Detects if the current candle has swept a target high or low.
        
        Rules:
        - Bearish Sweep: High went above target_high, but Close is below target_high.
        - Bullish Sweep: Low went below target_low, but Close is above target_low.
        """
        bear_sweep = current_high > target_high and current_close < target_high
        bull_sweep = current_low < target_low and current_close > target_low

        if bear_sweep and bull_sweep:
            return "both"
        if bear_sweep:
            return "bearish"
        if bull_sweep:
            return "bullish"
        return None

    @staticmethod
    def is_mitigated(price: float, ob_mid: float, is_bullish_ob: bool) -> bool:
        """
        OB Mitigation logic for parity with Pine script.
        Bullish OB is mitigated if price drops to/below Mean Threshold (mid).
        Bearish OB is mitigated if price rises to/above Mean Threshold (mid).
        """
        if is_bullish_ob:
            return price <= ob_mid
        else:
            return price >= ob_mid

if __name__ == "__main__":
    # Quick self-test
    model = SessionModel()
    test_dt = datetime.datetime(2026, 3, 4, 14, 30) # 2:30 PM
    print(f"Active sessions at {test_dt}: {model.get_active_sessions(test_dt)}")
    
    sweep = model.detect_sweep(105.0, 95.0, 99.0, 104.0, 96.0)
    print(f"Sweep detection result: {sweep}")
