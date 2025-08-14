#!/usr/bin/env python3
"""
vendor-serial-identifier.py — Resolve device serials using vendor SDKs.

Outputs JSON list of candidates:
[{
  "source": "amcam",
  "serial": "<serial>",
  "display_name": "<SDK display name>",
  "device_id": "<SDK device id if available>",
  "vendor_id": "0x####" | null,   # mapped via PyUSB; falls back to --vid/--pid if given
  "product_id": "0x####" | null
}, ...]

CLI:
  python vendor-serial-identifier.py --json
  python vendor-serial-identifier.py --json --vid 0x0547 --pid 0x6310
  python vendor-serial-identifier.py --json --provider amcam
  python vendor-serial-identifier.py --json --debug
"""
from __future__ import annotations

# --- stdlib
import argparse
import ctypes
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Ensure local OS/ (where amcam.py may live) is importable if run directly
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# ------------------------- utils / logging -------------------------

def dbg(msg: str, enable: bool) -> None:
    if enable:
        sys.stderr.write(msg.rstrip() + "\n")

def add_dll_dir(p: Path) -> None:
    """Add a directory to Windows DLL search path (or PATH for older Pythons)."""
    if not p:
        return
    try:
        os.add_dll_directory(str(p))  # Python 3.8+
    except AttributeError:
        os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")

# ------------------------- PyUSB backend wiring -------------------------

# Prefer user env override; else try common spots. You said your DLL lives in OS/lib/libusb.dll.
LIBUSB_DLL_ENV = os.environ.get("LIBUSB_DLL", "")
LIBUSB_CANDIDATES = [
    Path(LIBUSB_DLL_ENV) if LIBUSB_DLL_ENV else None,
    HERE / "lib"  / "libusb.dll",
    HERE / "libs" / "libusb.dll",
    HERE / "lib"  / "libusb-1.0.dll",
    HERE / "libs" / "libusb-1.0.dll",
]
LIBUSB_DLL_PATH: Optional[Path] = next((p for p in LIBUSB_CANDIDATES if p and p.exists()), None)

def get_pyusb_backend(debug: bool=False):
    """
    Lazily construct a PyUSB libusb1 backend using our exact DLL path.
    Returns the backend object, or None if not available / platform doesn't need it.
    """
    # Import inside function so module import never fails due to backend
    try:
        import usb.backend.libusb1 as libusb1
    except Exception as e:
        dbg(f"[pyusb] import backend failed: {e}", debug)
        return None

    # On Windows, be explicit about the DLL we want.
    if platform.system() == "Windows":
        if not LIBUSB_DLL_PATH:
            dbg("[pyusb] no libusb DLL found next to script (looked in OS/lib and OS/libs)", debug)
            return None
        add_dll_dir(LIBUSB_DLL_PATH.parent)
        try:
            ctypes.CDLL(str(LIBUSB_DLL_PATH))  # force-load to surface VC++/bitness issues early
        except OSError as e:
            dbg(f"[pyusb] failed to load {LIBUSB_DLL_PATH.name}: {e}", debug)
            return None
        be = libusb1.get_backend(find_library=lambda name: str(LIBUSB_DLL_PATH))
        if be is None:
            dbg(f"[pyusb] libusb backend couldn't init via {LIBUSB_DLL_PATH}", debug)
        return be

    # Non-Windows: let libusb1 find the system lib
    be = libusb1.get_backend()
    if be is None:
        dbg("[pyusb] libusb backend not available on this system", debug)
    return be

def usb_ids_by_serial(serial: str, debug: bool=False) -> Tuple[Optional[str], Optional[str]]:
    """
    Map a string serial -> (vid_hex, pid_hex) using PyUSB if possible.
    Returns (None, None) if not available or not found.
    """
    if not serial:
        return None, None
    try:
        import usb.core, usb.util  # type: ignore
    except Exception as e:
        dbg(f"[pyusb] PyUSB import failed: {e}", debug)
        return None, None

    be = get_pyusb_backend(debug=debug)
    if be is None:
        return None, None

    try:
        for dev in usb.core.find(find_all=True, backend=be):
            try:
                s = usb.util.get_string(dev, dev.iSerialNumber) if getattr(dev, "iSerialNumber", None) else None
            except Exception:
                s = None
            if s and s.strip() == serial:
                return f"0x{dev.idVendor:04x}", f"0x{dev.idProduct:04x}"
    except Exception as e:
        dbg(f"[pyusb] enumeration failed: {e}", debug)
    return None, None

# ------------------------- Vendor SDK: amcam -------------------------

def prepare_vendor_search_path() -> None:
    """
    Make sure Windows can find vendor DLLs like amcam.dll when amcam.py tries to load them.
    Looks in OS/, OS/lib/, OS/libs/.
    """
    for d in (HERE, HERE / "lib", HERE / "libs"):
        if d.exists():
            add_dll_dir(d)

def provider_amcam(debug: bool=False) -> List[Dict[str, Any]]:
    """
    Query the Amscope/ToupTek 'amcam' SDK for connected cameras and extract their serials.
    Works with a local amcam.py in OS/ or an installed package.
    """
    out: List[Dict[str, Any]] = []
    prepare_vendor_search_path()
    try:
        import amcam  # type: ignore
    except Exception as e:
        dbg(f"[amcam] import failed: {e}", debug)
        return out

    # Enumerate cameras via SDK
    try:
        devs = amcam.Amcam.EnumV2()
    except Exception as e:
        dbg(f"[amcam] EnumV2 failed: {e}", debug)
        return out

    for dev in devs:
        serial = None
        h = None
        try:
            try:
                h = amcam.Amcam.Open(getattr(dev, "id", None))
            except Exception as e:
                dbg(f"[amcam] Open failed for {getattr(dev, 'id', None)}: {e}", debug)
                h = None
            if h:
                try:
                    serial = h.SerialNumber()
                except Exception as e:
                    dbg(f"[amcam] SerialNumber() failed: {e}", debug)
                finally:
                    try:
                        h.Close()
                    except Exception:
                        pass
        except Exception as e:
            dbg(f"[amcam] unexpected error per-device: {e}", debug)

        if not serial:
            continue

        vid, pid = usb_ids_by_serial(serial, debug=debug)
        out.append({
            "source": "amcam",
            "serial": serial,
            "display_name": getattr(dev, "displayname", None),
            "device_id": getattr(dev, "id", None),
            "vendor_id": vid,
            "product_id": pid,
        })

    return out

# ------------------------- Provider registry -------------------------

PROVIDERS: Dict[str, Callable[..., List[Dict[str, Any]]]] = {
    "amcam": provider_amcam,
    # add more providers later...
}

# ------------------------- CLI / main -------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Resolve device serials using vendor SDKs.")
    ap.add_argument("--json", action="store_true", help="Output JSON")  # (we always output JSON)
    ap.add_argument("--vid", type=str, default=None, help="Filter by vendor id, e.g. 0x0547")
    ap.add_argument("--pid", type=str, default=None, help="Filter by product id, e.g. 0x6310")
    ap.add_argument("--provider", choices=sorted(PROVIDERS.keys()), help="Force a specific provider")
    ap.add_argument("--debug", action="store_true", help="Emit provider warnings to stderr")
    args = ap.parse_args()

    results: List[Dict[str, Any]] = []

    providers = [PROVIDERS[args.provider]] if args.provider else list(PROVIDERS.values())

    for prov in providers:
        try:
            results.extend([r for r in prov(debug=args.debug) if r.get("serial")])
        except Exception as e:
            dbg(f"[WARN] provider {prov.__name__} failed: {e}", args.debug)

    # If user supplied VID/PID, attach where missing so filters can work:
    if args.vid or args.pid:
        for r in results:
            if not r.get("vendor_id") and args.vid:
                r["vendor_id"] = args.vid
            if not r.get("product_id") and args.pid:
                r["product_id"] = args.pid

    # Optional post-filter
    if args.vid:
        vid_lc = args.vid.lower()
        results = [r for r in results if (r.get("vendor_id") or "").lower() == vid_lc]
    if args.pid:
        pid_lc = args.pid.lower()
        results = [r for r in results if (r.get("product_id") or "").lower() == pid_lc]

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
