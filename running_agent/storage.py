from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .storage_paths import prepare_parent

PRIVATE_FILE_MODE = 0o600


def read_json_file(
    path: Path,
    *,
    default: Any = None,
    suppress_errors: bool = False,
) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if suppress_errors:
            return default
        raise


def write_json_file(
    path: Path,
    data: Any,
    *,
    private: bool = True,
    trailing_newline: bool = False,
) -> None:
    text = json.dumps(data, indent=2, sort_keys=True)
    if trailing_newline:
        text += "\n"
    write_text_file(path, text, private=private)


def read_text_file(path: Path, *, default: str | None = None) -> str | None:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, text: str, *, private: bool = True) -> None:
    prepare_parent(path)
    _atomic_write_text(path, text)
    if private:
        path.chmod(PRIVATE_FILE_MODE)


def append_jsonl(path: Path, entry: dict[str, Any], *, private: bool = True) -> None:
    prepare_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    if private:
        path.chmod(PRIVATE_FILE_MODE)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def _atomic_write_text(path: Path, text: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise
