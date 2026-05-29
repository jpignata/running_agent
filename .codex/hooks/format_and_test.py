#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


EDIT_TOOL_NAMES = {
    "apply_patch",
    "Edit",
    "Write",
    "functions.apply_patch",
}


def is_file_edit(payload):
    tool_name = payload.get("tool_name", "")
    if tool_name in EDIT_TOOL_NAMES:
        return True

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    return isinstance(command, str) and command.lstrip().startswith("*** Begin Patch")


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    if not is_file_edit(payload):
        return 0

    repo_root = Path(__file__).resolve().parents[2]
    commands = [
        [sys.executable, "-m", "isort", "running_agent", "tests"],
        [sys.executable, "-m", "black", "running_agent", "tests"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
    ]
    for command in commands:
        subprocess.run(command, cwd=repo_root, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
