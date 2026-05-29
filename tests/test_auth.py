from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from running_agent.auth import build_authorization_url, load_env_file


class AuthTest(unittest.TestCase):
    def test_load_env_file_loads_values_and_preserves_existing_environment(self) -> None:
        path = _env_file(
            "\n".join(
                [
                    "STRAVA_CLIENT_ID=file-client",
                    "STRAVA_CLIENT_SECRET='file-secret'",
                    "EXISTING=from-file",
                    "# ignored",
                    "not-an-env-line",
                ]
            )
        )
        previous_client_id = os.environ.pop("STRAVA_CLIENT_ID", None)
        previous_client_secret = os.environ.pop("STRAVA_CLIENT_SECRET", None)
        self.addCleanup(_restore_env, "STRAVA_CLIENT_ID", previous_client_id)
        self.addCleanup(_restore_env, "STRAVA_CLIENT_SECRET", previous_client_secret)
        os.environ["EXISTING"] = "already-set"
        self.addCleanup(os.environ.pop, "STRAVA_CLIENT_ID", None)
        self.addCleanup(os.environ.pop, "STRAVA_CLIENT_SECRET", None)
        self.addCleanup(os.environ.pop, "EXISTING", None)

        load_env_file(path)

        self.assertEqual(os.environ["STRAVA_CLIENT_ID"], "file-client")
        self.assertEqual(os.environ["STRAVA_CLIENT_SECRET"], "file-secret")
        self.assertEqual(os.environ["EXISTING"], "already-set")

    def test_build_authorization_url_uses_env_values(self) -> None:
        os.environ["STRAVA_CLIENT_ID"] = "client-123"
        os.environ["STRAVA_REDIRECT_URI"] = "http://localhost/callback"
        self.addCleanup(os.environ.pop, "STRAVA_CLIENT_ID", None)
        self.addCleanup(os.environ.pop, "STRAVA_REDIRECT_URI", None)

        url = build_authorization_url(scope="read")

        self.assertIn("client_id=client-123", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%2Fcallback", url)
        self.assertIn("scope=read", url)


def _env_file(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
    path = Path(handle.name)
    with handle:
        handle.write(text)
    return path


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
