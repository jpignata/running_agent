from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

SERVICE_NAME = "running-agent-telegram.service"


def install_telegram_user_service(
    *,
    project_dir: Path | None = None,
    python_executable: Path | None = None,
    service_dir: Path | None = None,
    enable: bool = True,
    start: bool = True,
) -> Path:
    project_dir = (project_dir or Path.cwd()).resolve()
    python_executable = (python_executable or Path(sys.executable)).resolve()
    service_dir = service_dir or Path.home() / ".config" / "systemd" / "user"
    service_path = service_dir / SERVICE_NAME

    service_dir.mkdir(parents=True, exist_ok=True)
    service_path.write_text(
        render_telegram_user_service(
            project_dir=project_dir,
            python_executable=python_executable,
        ),
        encoding="utf-8",
    )
    service_path.chmod(0o644)

    if enable or start:
        _run_systemctl("daemon-reload")
    if enable:
        _run_systemctl("enable", SERVICE_NAME)
    if start:
        _run_systemctl("restart", SERVICE_NAME)

    return service_path


def render_telegram_user_service(*, project_dir: Path, python_executable: Path) -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=Running Agent Telegram coach",
            "Wants=network-online.target",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={_quote_systemd_value(project_dir)}",
            "Environment=PYTHONUNBUFFERED=1",
            f"ExecStart={_quote_systemd_value(python_executable)} -m running_agent telegram",
            "Restart=always",
            "RestartSec=15",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def boot_linger_hint() -> str:
    user = os.environ.get("USER") or "<user>"
    return (
        "For user services to start before you log in after a reboot, enable linger once with:\n"
        f"loginctl enable-linger {shlex.quote(user)}"
    )


def _quote_systemd_value(value: Path) -> str:
    text = str(value)
    if not any(char.isspace() for char in text) and '"' not in text and "\\" not in text:
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_systemctl(*args: str) -> None:
    subprocess.run(["systemctl", "--user", *args], check=True)
