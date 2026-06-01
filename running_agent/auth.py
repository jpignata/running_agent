from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

from .storage import read_json_file, write_json_file

STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
DEFAULT_REDIRECT_URI = "http://localhost/exchange_token"
TOKEN_PATH = Path(".strava_tokens.json")
ENV_PATH = Path(".env")


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def require_env(name: str) -> str:
    load_env_file()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_authorization_url(scope: str = "read,activity:read_all") -> str:
    load_env_file()
    client_id = require_env("STRAVA_CLIENT_ID")
    redirect_uri = os.environ.get("STRAVA_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": scope,
        }
    )
    return f"{STRAVA_AUTHORIZE_URL}?{query}"


def save_tokens(token_data: dict, path: Path = TOKEN_PATH) -> None:
    write_json_file(path, token_data)


def load_tokens(path: Path = TOKEN_PATH) -> dict:
    if not path.exists():
        raise RuntimeError(
            "No Strava token file found. Run `python -m running_agent auth-url` and "
            "`python -m running_agent exchange-code YOUR_CODE` first."
        )
    return read_json_file(path)
