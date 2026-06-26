"""Estado global do sync de pedidos — compartilhado entre workers via arquivo JSON."""

import json
import os
import threading

_FILE = "/tmp/della_sync_state.json"
_LOCK = threading.Lock()

_DEFAULT = {
    "running": False,
    "pct": 0,
    "msg": "",
    "result": None,
    "error": None,
    "modo": "",
}


def _read() -> dict:
    try:
        with open(_FILE) as f:
            return {**_DEFAULT, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(_DEFAULT)


def _write(state: dict) -> None:
    try:
        with open(_FILE, "w") as f:
            json.dump(state, f)
    except OSError:
        pass


def get() -> dict:
    with _LOCK:
        return _read()


def update(**kwargs) -> None:
    with _LOCK:
        state = _read()
        state.update(kwargs)
        _write(state)


def reset() -> None:
    with _LOCK:
        _write(dict(_DEFAULT))
