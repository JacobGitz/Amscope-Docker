# popups.py

import datetime
from PyQt6.QtWidgets import QMessageBox

def _format_date(iso_dt: str) -> str:
    """
    Convert an ISO-8601 timestamp into US-style MM/DD/YYYY hh:mm:ss AM/PM.
    Falls back to the raw string on parse errors.
    """
    try:
        dt = datetime.datetime.fromisoformat(iso_dt)
        return dt.strftime("%m/%d/%Y %I:%M:%S %p")
    except Exception:
        return iso_dt


def ask_restore_session(
    parent,
    backend: str,
    port: str,
    preset_name: str,
    steps_per_mm: int,
    iso_dt: str
) -> bool:
    """
    On startup, ask whether to restore the last session.
    Shows backend, port, named preset, numeric steps/mm, and US-formatted timestamp.
    """
    ts = _format_date(iso_dt)
    msg = (
        "Would you like to restore your last session?\n\n"
        f"Backend: {backend}\n"
        f"Port: {port}\n"
        f"Preset: {preset_name}\n"
        f"Steps/mm: {steps_per_mm}\n"
        f"Last used: {ts}"
    )
    choice = QMessageBox.question(
        parent,
        "Restore session",
        msg,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    return (choice == QMessageBox.StandardButton.Yes)


def ask_restore_preset(
    parent,
    old_steps: int,
    iso_dt: str
) -> bool:
    """
    When manually selecting a previously-used backend+port,
    ask if you'd like to restore the old steps/mm setting.
    """
    ts = _format_date(iso_dt)
    msg = (
        f"You previously used Steps/mm = {old_steps} on {ts} for this device.\n\n"
        "Would you like to restore that preset now?"
    )
    choice = QMessageBox.question(
        parent,
        "Restore preset",
        msg,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    return (choice == QMessageBox.StandardButton.Yes)


def warn_lost_power(
    parent,
    last_pos: int,
    last_mm: float,
    iso_dt: str
) -> bool:
    """
    Warn that the device was powered off (homed=False).
    Offer to home and return to the last saved position.
    """
    ts = _format_date(iso_dt)
    msg = (
        "It appears the device was powered off since last use.\n"
        f"You were at {last_pos} cnt ({last_mm:.3f} mm) on {ts}.\n\n"
        "You must home before absolute moves.  Home and return to that position?"
    )
    choice = QMessageBox.question(
        parent,
        "Device lost power",
        msg,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    return (choice == QMessageBox.StandardButton.Yes)


def warn_moved(
    parent,
    last_pos: int,
    curr_pos: int,
    last_mm: float,
    curr_mm: float,
    iso_dt: str
) -> bool:
    """
    Warn that the device has been moved elsewhere since last use.
    Offer to return to your last saved position.
    """
    ts = _format_date(iso_dt)
    msg = (
        f"Device has moved since {ts}:\n"
        f"  Last: {last_pos} cnt ({last_mm:.3f} mm)\n"
        f"  Now:  {curr_pos} cnt ({curr_mm:.3f} mm)\n\n"
        "Would you like to return it to your last saved position?"
    )
    choice = QMessageBox.question(
        parent,
        "Device moved",
        msg,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    return (choice == QMessageBox.StandardButton.Yes)

