from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .auth import load_env_file, require_env

GARMIN_TOKENSTORE = Path.home() / ".garminconnect"
NUMERIC_TYPES = (int, float)


class GarminClient:
    def __init__(self, tokenstore: Path = GARMIN_TOKENSTORE):
        self.tokenstore = tokenstore
        self.api = self._authenticate()

    def readiness_snapshot(
        self,
        target_date: date | None = None,
        vo2max_lookback_days: int = 30,
    ) -> dict[str, Any]:
        target_date = target_date or date.today()
        date_text = target_date.isoformat()
        yesterday_text = (target_date - timedelta(days=1)).isoformat()

        return {
            "date": date_text,
            "stats": self._safe_call("stats", self.api.get_stats, date_text),
            "heart_rates": self._safe_call("heart_rates", self.api.get_heart_rates, date_text),
            "sleep": self._safe_call("sleep", self.api.get_sleep_data, date_text),
            "hrv": self._safe_call("hrv", self.api.get_hrv_data, date_text),
            "stress": self._safe_call("stress", self.api.get_stress_data, date_text),
            "body_battery": self._safe_call(
                "body_battery",
                self.api.get_body_battery,
                yesterday_text,
                date_text,
            ),
            "training_readiness": self._optional_call("get_training_readiness", date_text),
            "training_status": self._optional_call("get_training_status", date_text),
            "vo2max": self._safe_recent_vo2max(target_date, lookback_days=vo2max_lookback_days),
        }

    def _authenticate(self):
        try:
            from garminconnect import Garmin
        except ImportError as error:
            raise RuntimeError(
                "Garmin support requires the garminconnect package. Install project dependencies "
                "before running Garmin commands."
            ) from error

        load_env_file()
        email = require_env("GARMIN_EMAIL")
        password = require_env("GARMIN_PASSWORD")

        try:
            api = Garmin(
                email,
                password,
                prompt_mfa=lambda: input("Enter Garmin MFA code: ").strip(),
            )
            api.login(str(self.tokenstore))
            return api
        except Exception as error:
            raise RuntimeError(f"Garmin authentication failed: {error}") from error

    def _optional_call(self, method_name: str, *args) -> dict[str, Any]:
        method = getattr(self.api, method_name, None)
        if not method:
            return {"available": False, "error": f"{method_name} is not available."}
        return self._safe_call(method_name, method, *args)

    def _safe_call(self, name: str, method, *args) -> dict[str, Any]:
        try:
            return {"available": True, "data": method(*args)}
        except Exception as error:
            return {"available": False, "error": f"{name} failed: {error}"}

    def _safe_recent_vo2max(self, target_date: date, lookback_days: int) -> dict[str, Any]:
        method = getattr(self.api, "get_max_metrics", None)
        if not method:
            return {"available": False, "error": "get_max_metrics is not available."}

        first_result = None
        for offset in range(max(lookback_days, 0) + 1):
            vo2max_date = target_date - timedelta(days=offset)
            result = self._safe_call("get_max_metrics", method, vo2max_date.isoformat())
            if first_result is None:
                first_result = result
            if _has_vo2max(result.get("data")):
                if offset:
                    result["date"] = vo2max_date.isoformat()
                    result["fallback_for_date"] = target_date.isoformat()
                return result
        return first_result or {
            "available": False,
            "error": "get_max_metrics failed: no attempts made",
        }


def _has_vo2max(data: Any) -> bool:
    if isinstance(data, list):
        return any(_has_vo2max(item) for item in data)
    if not isinstance(data, dict):
        return False
    generic = data.get("generic")
    if isinstance(generic, dict) and any(
        isinstance(generic.get(key), NUMERIC_TYPES)
        for key in ["vo2MaxPreciseValue", "vo2MaxValue"]
    ):
        return True
    return any(
        isinstance(data.get(key), NUMERIC_TYPES) for key in ["vo2MaxPreciseValue", "vo2MaxValue"]
    )
