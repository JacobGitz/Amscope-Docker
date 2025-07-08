"""tdc_controller.py – Simple, well‑commented helper for ThorLabs **TDC001** cubes.

Author: Jacob Lazarchik (2025)

This file intentionally trades *brevity* for *clarity*: every time a new Python
concept is introduced, we put a short inline comment right next to it.  That
makes the file a friendly first stop for newcomers while still exposing the
core actions you need in a Docker‑hosted environment.

Highlights
~~~~~~~~~~
* **Explicit connection** – You *must* pass the serial‑port device (e.g.
  ``"/dev/ttyUSB0"``) when constructing :class:`TDCController`.
* **Safe defaults** – No automatic homing.  Motors are enabled only when you
  ask for it (but see ``enable_after_init`` flag).
* **Beginner friendly** – Single class, every unfamiliar idea annotated.
* **Helpful discovery** – :func:`find_tdc001_ports` searches all serial ports
  for likely TDC001 cubes so host scripts can decide which port to mount into
  the container.

Run as a script
~~~~~~~~~~~~~~~
Invoking ``python -m tdc_controller`` (or ``python tdc_controller.py``) drops you
into an *interactive shell* that lets you identify, jog, home, or stop the cube
without writing any code – perfect for quick bench tests.
"""
from __future__ import annotations                 # → allow future‑style type hints on Py<3.10

# ────────────────────────────── standard library ──────────────────────────────
import inspect                                       # → runtime reflection utilities
import time                                          # → sleep / simple timing
from typing import Dict, List                        # → static typing helpers

# ────────────────────────────── third‑party libs ──────────────────────────────
from serial.tools import list_ports                  # → enumerate system serial ports
from serial.tools.list_ports_common import ListPortInfo  # → rich object describing a port
from thorlabs_apt_device import TDC001               # → official low‑level driver

__all__ = ["TDCController", "find_tdc001_ports"]     # → what `from … import *` should export

# ══════════════════════════════ helper functions ══════════════════════════════

def find_tdc001_ports(
    *,
    vendor_ids: tuple[int, ...] = (0x0403, 0x1313),   # common FTDI / Thorlabs USB VIDs
    serial_prefix: str = "83",                       # TDC001 cubes usually start with 83‑‑
) -> List[str]:
    """Return *device strings* (e.g. ``'/dev/ttyUSB0'``) for attached TDC001 cubes."""
    ports: List[str] = []                             # → collected matches

    for p in list_ports.comports():                   # → every serial device
        if p.vid not in vendor_ids:                   # ✱ vendor mismatch
            continue
        if p.serial_number is None:                   # ✱ no serial → skip
            continue
        if not p.serial_number.startswith(serial_prefix):  # ✱ not a cube
            continue
        ports.append(p.device)                        # ✱ good → save
    return ports                                      # → hand back list

# ══════════════════════════════ main wrapper class ════════════════════════════

class TDCController:
    """Beginner‑friendly façade over :class:`thorlabs_apt_device.TDC001`."""

    # ➊ constructor – open serial port & start background polling
    def __init__(
        self,
        serial_port: str,                            # required: which /dev/ttyUSB?*
        *,                                           # ⬑ forces the rest to be keyword‑only
        enable_after_init: bool = True,              # auto‑enable motor driver?
        poll_delay: float = 0.1,                     # seconds to let status thread spin up
    ) -> None:
        self._cube = TDC001(serial_port=serial_port, home=False)  # low‑level driver
        self._cube.register_error_callback(self._error_callback)  # print errors
        time.sleep(poll_delay)                       # let polling thread unpack first status
        if enable_after_init:
            self._cube.set_enabled(True)             # power stage

    # ➋ convenience property ----------------------------------------------------
    @property
    def status(self) -> Dict[str, object]:           # expose bay 0 / chan 0 dict
        return self._cube.status_[0][0]

    # ➌ motion helpers ---------------------------------------------------------
    def _wait_until(self, predicate, timeout: float = 120, dt: float = 0.05) -> None:
        """Block until *predicate()* is True or we exceed *timeout*."""
        time.sleep(.3)
        t0 = time.time()
        while not predicate():
            if time.time() - t0 > timeout:
                raise TimeoutError("TDC001 operation timed‑out")
            time.sleep(dt)

    def move_relative(self, counts: int) -> None:
        """Jog by *counts* encoder steps relative to current position."""
        self._cube.move_relative(counts)
        self._wait_until(self._is_idle)

    def move_absolute(self, position: int) -> None:
        """Move to *position* encoder counts from mechanical zero."""
        self._cube.move_absolute(position)
        self._wait_until(self._is_idle)

    def home(self) -> None:
        """Run cube homing sequence."""
        self._cube.home()
        self._wait_until(lambda: self.status["homed"], timeout=300)

    def identify(self) -> None:
        """Flash the cube LED (helps to know which cube you’re talking to)."""
        self._cube.identify()

    # ➍ utility ----------------------------------------------------------------
    def available_commands(self) -> Dict[str, str]:
        """Return public method signatures – great for interactive help."""
        pub = [m for m in dir(self) if not m.startswith("_") and callable(getattr(self, m))]
        return {name: str(inspect.signature(getattr(self, name))) for name in pub}

    # ➎ teardown ---------------------------------------------------------------
    def close(self) -> None:
        try:
            self._cube.stop(immediate=True)          # abort motion if moving
        except Exception:
            pass
        self._cube.close()                           # close serial & threads

    def __enter__(self) -> "TDCController":          # enable "with" syntax
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False                                 # propagate exceptions

    # ➏ internal helpers -------------------------------------------------------
    def _is_idle(self) -> bool:                      # both mov flags False → idle
        return not (self.status["moving_forward"] or self.status["moving_reverse"])

    @staticmethod
    def _error_callback(source, msgid, code, notes):
        print(f"[TDC001‑{source:#x}] Error {code}: {notes}")

# ══════════════════════════════ CLI entry‑point ═══════════════════════════════

def _interactive_cli() -> None:
    """Very small REPL so the module works as a *stand‑alone* script."""
    ports = find_tdc001_ports()
    if not ports:
        print("No TDC001 cubes found.")
        return

    # If multiple cubes→ ask user which: --------------------------------------
    if len(ports) > 1:
        print("Available cubes:")
        for idx, dev in enumerate(ports, 1):
            print(f"  {idx}. {dev}")
        sel = input("Select cube [1‑{}]: ".format(len(ports))).strip()
        try:
            port = ports[int(sel) - 1]
        except Exception:
            print("Invalid selection → abort.")
            return
    else:
        port = ports[0]
        print(f"Using {port}")

    # Main loop ---------------------------------------------------------------
    with TDCController(port) as ctrl:
        print("Commands: [m]ove‑rel  [a]bsolute  [h]ome  [i]dentify  [s]tatus  [q]uit")
        while True:
            cmd = input("> ").strip().lower() or "?"
            if cmd in ("q", "quit", "exit"):
                break
            if cmd.startswith("m"):
                val = int(input("  counts to move (±): "))
                ctrl.move_relative(val)
            elif cmd.startswith("a"):
                pos = int(input("  target absolute counts: "))
                ctrl.move_absolute(pos)
            elif cmd.startswith("h"):
                print("  Homing… this may take ~30 s")
                ctrl.home()
            elif cmd.startswith("i"):
                ctrl.identify()
            elif cmd.startswith("s"):
                print(ctrl.status)
            else:
                print("Unknown command – try again.")

# Allow `python tdc_controller.py` ---------------------------------------------
if __name__ == "__main__":
    _interactive_cli()

