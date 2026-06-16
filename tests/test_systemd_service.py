from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.systemd_service import (
    SERVICE_NAME,
    boot_linger_hint,
    install_telegram_user_service,
    render_telegram_user_service,
)


class SystemdServiceTest(unittest.TestCase):
    def test_render_telegram_user_service_uses_project_and_python_paths(self) -> None:
        service = render_telegram_user_service(
            project_dir=Path("/home/jp/workspace/running_agent"),
            python_executable=Path("/home/jp/workspace/running_agent/.venv/bin/python"),
        )

        self.assertIn("WorkingDirectory=/home/jp/workspace/running_agent", service)
        self.assertIn(
            "ExecStart=/home/jp/workspace/running_agent/.venv/bin/python "
            "-m running_agent telegram",
            service,
        )
        self.assertIn("Restart=always", service)
        self.assertIn("WantedBy=default.target", service)

    def test_render_telegram_user_service_quotes_paths_with_spaces(self) -> None:
        service = render_telegram_user_service(
            project_dir=Path("/tmp/running agent"),
            python_executable=Path("/tmp/running agent/.venv/bin/python"),
        )

        self.assertIn('WorkingDirectory="/tmp/running agent"', service)
        self.assertIn('ExecStart="/tmp/running agent/.venv/bin/python"', service)

    @patch("running_agent.systemd_service._run_systemctl")
    def test_install_telegram_user_service_writes_and_enables_service(self, run_systemctl) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service_dir = Path(temp_dir) / "systemd"

            service_path = install_telegram_user_service(
                project_dir=Path("/repo"),
                python_executable=Path("/repo/.venv/bin/python"),
                service_dir=service_dir,
            )

            self.assertEqual(service_path, service_dir / SERVICE_NAME)
            self.assertIn("WorkingDirectory=/repo", service_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [call.args for call in run_systemctl.call_args_list],
                [
                    ("daemon-reload",),
                    ("enable", SERVICE_NAME),
                    ("restart", SERVICE_NAME),
                ],
            )

    @patch("running_agent.systemd_service._run_systemctl")
    def test_install_telegram_user_service_prefers_project_venv_python(self, run_systemctl) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "repo"
            service_dir = Path(temp_dir) / "systemd"
            venv_python = project_dir / ".venv" / "bin" / "python"
            python_target = Path(temp_dir) / "python-target"
            venv_python.parent.mkdir(parents=True)
            python_target.touch()
            os.symlink(python_target, venv_python)

            service_path = install_telegram_user_service(
                project_dir=project_dir,
                service_dir=service_dir,
                enable=False,
                start=False,
            )

            self.assertIn(
                f"ExecStart={venv_python} -m running_agent telegram",
                service_path.read_text(encoding="utf-8"),
            )
            run_systemctl.assert_not_called()

    @patch.dict("os.environ", {"USER": "runner user"})
    def test_boot_linger_hint_quotes_user(self) -> None:
        self.assertIn("loginctl enable-linger 'runner user'", boot_linger_hint())


if __name__ == "__main__":
    unittest.main()
