# === File: tdc_ui/constants.py ===
from pathlib import Path

# where we persist last-known positions
STORAGE_PATH = Path.home() / ".tdc001_positions.json"

# preset encoder counts per mm
STEP_PRESETS = {
    "T-Cube 0.5 mm lead": 51200,
    "T-Cube 1.0 mm lead": 25600,
    "MTS28-Z8": 34555,
    "Manual set…": None,
}

# unit conversion factors to mm
UNIT_FACT = {
    "mm": 1.0,
    "µm": 1e-3,
}
