# -------------------------------
# File: storage.py
# -------------------------------
from pathlib import Path
import json

# where we persist state (settings + positions)
STORAGE_PATH = Path.home() / ".tdc001_state.json"


def load_state() -> dict:
    """
    Load complete state from disk, returning a dict with "settings" and "positions".
    """
    try:
        return json.loads(STORAGE_PATH.read_text())
    except FileNotFoundError:
        return {"settings": {}, "positions": {}}


def save_state(state: dict) -> None:
    """
    Atomically write the full state (settings + positions) back to disk.
    """
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORAGE_PATH.write_text(json.dumps(state, indent=2))


def load_positions() -> dict:
    """
    Return the positions sub-dict from saved state.
    """
    return load_state().get("positions", {})


def save_positions(positions: dict) -> None:
    """
    Save only the positions into the state file, preserving existing settings.
    """
    state = load_state()
    state["positions"] = positions
    save_state(state)


def load_settings() -> dict:
    """
    Return the settings sub-dict from saved state.
    """
    return load_state().get("settings", {})


def save_settings(settings: dict) -> None:
    """
    Save only the settings into the state file, preserving existing positions.
    """
    state = load_state()
    state["settings"] = settings
    save_state(state)

