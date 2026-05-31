#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root"

python_bin="python3"
if [[ -x ".venv/bin/python" ]]; then
  python_bin=".venv/bin/python"
fi

"$python_bin" -m ruff check --fix running_agent tests
"$python_bin" -m isort running_agent tests
"$python_bin" -m black running_agent tests
