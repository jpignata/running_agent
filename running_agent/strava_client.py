from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .auth import TOKEN_PATH, load_tokens, require_env, save_tokens

STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


class StravaClient:
    def __init__(self, token_path=TOKEN_PATH):
        self.token_path = token_path
        self.tokens = load_tokens(token_path)

    @classmethod
    def exchange_code(cls, code: str) -> dict[str, Any]:
        payload = {
            "client_id": require_env("STRAVA_CLIENT_ID"),
            "client_secret": require_env("STRAVA_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
        }
        token_data = _post_form(STRAVA_TOKEN_URL, payload)
        save_tokens(token_data)
        return token_data

    def refresh_access_token_if_needed(self) -> str:
        expires_at = int(self.tokens.get("expires_at", 0))
        if expires_at > int(time.time()) + 60:
            return self.tokens["access_token"]

        payload = {
            "client_id": require_env("STRAVA_CLIENT_ID"),
            "client_secret": require_env("STRAVA_CLIENT_SECRET"),
            "refresh_token": self.tokens["refresh_token"],
            "grant_type": "refresh_token",
        }
        self.tokens = _post_form(STRAVA_TOKEN_URL, payload)
        save_tokens(self.tokens, self.token_path)
        return self.tokens["access_token"]

    def recent_activities(
        self, days: int = 14, per_page: int = 100
    ) -> list[dict[str, Any]]:
        after = int(datetime.now(timezone.utc).timestamp()) - (days * 24 * 60 * 60)
        activities: list[dict[str, Any]] = []
        page = 1
        while True:
            page_activities = self._get(
                "/athlete/activities",
                {
                    "after": str(after),
                    "per_page": str(per_page),
                    "page": str(page),
                },
            )
            if not page_activities:
                break
            activities.extend(page_activities)
            if len(page_activities) < per_page:
                break
            page += 1
        return sorted(activities, key=_activity_start_timestamp, reverse=True)

    def latest_run(self, days: int = 90) -> dict[str, Any] | None:
        runs = [
            activity
            for activity in self.recent_activities(days=days)
            if activity.get("type") == "Run"
        ]
        if not runs:
            return None
        return max(runs, key=_activity_start_timestamp)

    def runs_on_date(
        self, target_date: date, search_days: int = 120
    ) -> list[dict[str, Any]]:
        runs = [
            activity
            for activity in self.recent_activities(days=search_days)
            if activity.get("type") == "Run"
            and _activity_local_date(activity) == target_date
        ]
        return sorted(runs, key=_activity_start_timestamp, reverse=True)

    def detailed_activity(
        self,
        activity_id: int | str,
        include_all_efforts: bool = True,
    ) -> dict[str, Any]:
        return self._get(
            f"/activities/{activity_id}",
            {"include_all_efforts": str(include_all_efforts).lower()},
        )

    def logged_in_athlete(self) -> dict[str, Any]:
        return self._get("/athlete")

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        token = self.refresh_access_token_if_needed()
        url = f"{STRAVA_API_BASE}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8")
            raise RuntimeError(
                f"Strava request failed with HTTP {error.code}: {body}"
            ) from error


def _post_form(url: str, payload: dict[str, str]) -> dict[str, Any]:
    data = urlencode(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8")
        raise RuntimeError(
            f"Strava request failed with HTTP {error.code}: {body}"
        ) from error


def _activity_start_timestamp(activity: dict[str, Any]) -> float:
    value = activity.get("start_date") or activity.get("start_date_local")
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def _activity_local_date(activity: dict[str, Any]) -> date | None:
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
