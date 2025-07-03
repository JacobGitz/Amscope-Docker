#!/usr/bin/env python3
"""
Main Window Module

This module defines the MainWindow class, which provides a PyQt6 graphical user interface
for controlling a Thorlabs TDC001 device over a networked backend. It refactors the v1.8 UI,
adds full session‐restore on boot (backend, port, preset, position), and only issues
lost‐power/moved warnings once the device is truly idle. It also auto-returns to your
last position without flicker and preserves your chosen steps/mm preset.
"""

import sys
import datetime
import socket

from PyQt6.QtGui import QIcon, QIntValidator, QDoubleValidator
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QComboBox, QLineEdit,
    QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QStatusBar, QMessageBox
)
from PyQt6.QtCore import QTimer, QThread

from api import APIClient, scan_for_backends
from constants import STEP_PRESETS, UNIT_FACT
from storage import load_positions, save_positions, load_settings, save_settings
from popups import ask_restore_session, ask_restore_preset, warn_lost_power, warn_moved
from task_runner import Worker


class MainWindow(QMainWindow):
    """Main UI class with boot-time session restore and safe-state checks."""

    def __init__(self, backend_hint=None):
        super().__init__()
        # Window setup
        self.setWindowTitle("Thorlabs TDC001 Controller")
        self.setWindowIcon(QIcon.fromTheme("applications-engineering"))
        self.resize(900, 600)

        # State
        self.api = None
        self.steps_per_mm = STEP_PRESETS["T-Cube 0.5 mm lead"]
        self.positions = load_positions()      # { "backend|port": {pos, time, steps_per_mm, homed} }
        self.settings = load_settings()        # { backend, port, preset, steps_per_mm, date }
        self.session_restored = False
        self._did_post_connect_warn = False

        # Input validators
        self.int_val = QIntValidator(1, 10**6, self)
        self.fl_val  = QDoubleValidator(0.0, 1e6, 6, self)

        # Build UI, discover backends, restore session, start polling
        self._build_ui()
        self._discover_backends(backend_hint)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(500)
        self._maybe_restore_session()

    def _maybe_restore_session(self):
        """
        On startup, if we have saved backend+port, offer to restore:
          1) backend URL
          2) cube-port
          3) steps/mm preset (or Custom)
          4) return to last absolute position
        """
        # pull saved session settings
        saved_backend = self.settings.get("backend")
        saved_port    = self.settings.get("port")
        saved_preset  = self.settings.get("preset", "Custom")
        saved_spm     = self.settings.get("steps_per_mm", self.steps_per_mm)
        saved_date    = self.settings.get("date", "")

        # nothing to restore?
        if not (saved_backend and saved_port):
            return

        # backend must still be in our dropdown
        if self.cmb_backend.findText(saved_backend) < 0:
            return

        # ask the user
        if not ask_restore_session(
            self,
            saved_backend,
            saved_port,
            saved_preset,
            saved_spm,
            saved_date,
        ):
            return

        # mark that we *have* just done a boot-restore
        self.session_restored = True

        # 1) pick the saved backend & reload ports
        self.cmb_backend.setCurrentText(saved_backend)
        self._on_backend_change(saved_backend)

        # 2) pick the saved port
        self.cmb_port.setCurrentText(saved_port)

        # 3) restore the preset (or custom)
        if saved_preset in STEP_PRESETS:
            self.cmb_preset.setCurrentText(saved_preset)
        else:
            # force “Custom” and fill in the numeric value
            self.cmb_preset.setCurrentText("Custom")
            self.ed_steps.setText(str(saved_spm))

        # 4) call your existing preset handler so everything stays in sync
        self._on_preset(self.cmb_preset.currentText())

        # 5) connect the device (this also saves the settings again)
        self._connect_device()

        # 6) do one immediate status refresh to avoid flicker
        self._refresh_status()

        # 7) auto‐move back to the last saved absolute position
        key = f"{self.api.base}|{saved_port}"
        last = self.positions.get(key)
        if last and "pos" in last:
            # no need to QTimer this if you don't mind the slight delay
            QTimer.singleShot(200, lambda: self._run_async(self.api.move_abs, last["pos"]))

        # 8) schedule your lost‐power / moved‐elsewhere safety check
        self._did_post_connect_warn = False
        QTimer.singleShot(500, self._check_post_connect)

    def _connect_device(self):
        """
        Called when user selects a cube-port:
        - Connects to API
        - Saves session settings
        - Schedules lost-power/moved warnings once device is idle
        """
        port = self.cmb_port.currentText().strip()
        if not port:
            return

        try:
            self.api.connect(port)
            self.statusbar.showMessage("Connected", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"/connect failed:\n{e}")
            return

        # Persist connection settings for next boot
        self.settings.update({
            "backend":      self.api.base,
            "port":         port,
            "preset":       self.cmb_preset.currentText(),
            "steps_per_mm": self.steps_per_mm,
            "date":         datetime.datetime.now().isoformat()
        })
        save_settings(self.settings)

        # Reset warning guard and schedule safety check
        self._did_post_connect_warn = False
        QTimer.singleShot(500, self._check_post_connect)

    def _check_post_connect(self):
        """
        After connecting:
        1) If busy (initializing/moving), retry in 200 ms
        2) Once idle and not yet warned:
           • If previously homed but now un-homed → lost-power
           • Else if homed and position differs → moved-elsewhere
        """
        port = self.cmb_port.currentText().strip()
        key  = f"{self.api.base}|{port}"
        last = self.positions.get(key)
        if not last or self._did_post_connect_warn:
            return

        st = self.api.status()
        curr_pos   = st["position"]
        curr_homed = st["homed"]
        busy = st["moving_forward"] or st["moving_reverse"]

        # Retry if still busy
        if busy:
            QTimer.singleShot(200, self._check_post_connect)
            return

        # Fetch saved data
        last_pos   = last["pos"]
        last_homed = last.get("homed", False)
        last_steps = last.get("steps_per_mm", self.steps_per_mm)
        last_mm    = last_pos / last_steps
        last_time  = last["time"]

        # Lost-power case
        if last_homed and not curr_homed:
            self._did_post_connect_warn = True
            if warn_lost_power(self, last_pos, last_mm, last_time):
                def after_home(res, err):
                    if not err:
                        self._run_async(self.api.move_abs, last_pos)
                w = Worker(self.api.home)
                t = QThread(self)
                w.moveToThread(t)
                t.started.connect(w.run)
                w.finished.connect(after_home)
                t.start()

        # Moved-elsewhere case
        if curr_homed and abs(curr_pos - last_pos) > 2:
            self._did_post_connect_warn = True
            curr_mm = curr_pos / self.steps_per_mm
            if warn_moved(self, last_pos, curr_pos, last_mm, curr_mm, last_time):
                self._run_async(self.api.move_abs, last_pos)

    def _build_ui(self):
        """Construct all widgets, layouts, and connect signals."""
        central = QWidget(self)
        self.setCentralWidget(central)
        main_v = QVBoxLayout(central)
        main_v.setSpacing(10)
        main_v.setContentsMargins(10, 10, 10, 10)

        # Status row
        st_h = QHBoxLayout()
        self.lbl_status = QLabel("Status: —")
        self.lbl_homed   = QLabel("Homed: ✗")
        self.lbl_pos     = QLabel("Pos: — cnt | — mm")
        for lbl in (self.lbl_status, self.lbl_homed, self.lbl_pos):
            st_h.addWidget(lbl)
        st_h.addStretch()
        main_v.addLayout(st_h)

        # ── Network group ─────────────────────────────────────────────────────
        net_g = QGroupBox("Network")
        net_f = QFormLayout(net_g)

        # Backend combobox – *react on commit only*
        self.cmb_backend = QComboBox()
        self.cmb_backend.setEditable(True)
        self.cmb_backend.setPlaceholderText("http://<ip>:8000")

        # disconnect any eager default signal that fires on every keystroke
        try:
            self.cmb_backend.currentTextChanged.disconnect()
        except TypeError:
            pass  # nothing connected yet – OK

        # ① user picked an item from the drop-down
        self.cmb_backend.currentIndexChanged.connect(
            lambda i: self._on_backend_change(self.cmb_backend.itemText(i))
        )
        # ② user finished typing and pressed ↵
        self.cmb_backend.lineEdit().editingFinished.connect(
            lambda: self._on_backend_change(self.cmb_backend.currentText())
        )

        btn_add = QPushButton("Add Backend")
        btn_add.clicked.connect(self._add_backend)

        self.cmb_port = QComboBox()
        self.cmb_port.currentIndexChanged.connect(self._connect_device)

        net_f.addRow("Backend:", self.cmb_backend)
        net_f.addRow("", btn_add)
        net_f.addRow("Cube port:", self.cmb_port)
        main_v.addWidget(net_g)

        # Motion group
        mot_g = QGroupBox("Motion")
        grid = QGridLayout(mot_g)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        # Steps/mm preset
        grid.addWidget(QLabel("Steps/mm preset:"), 0, 0)
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(STEP_PRESETS.keys())
        self.cmb_preset.currentTextChanged.connect(self._on_preset)
        grid.addWidget(self.cmb_preset, 0, 1)
        self.ed_steps = QLineEdit(str(self.steps_per_mm))
        self.ed_steps.setValidator(self.int_val)
        grid.addWidget(self.ed_steps, 0, 2)

        # Relative move
        grid.addWidget(QLabel("Move relative:"), 1, 0)
        self.ed_rel = QLineEdit("0"); self.ed_rel.setValidator(self.fl_val)
        grid.addWidget(self.ed_rel, 1, 1)
        self.cmb_unit_rel = QComboBox(); self.cmb_unit_rel.addItems(UNIT_FACT.keys())
        grid.addWidget(self.cmb_unit_rel, 1, 2)
        btn_neg = QPushButton("–"); btn_neg.clicked.connect(lambda: self._move_rel(-1))
        btn_pos = QPushButton("+"); btn_pos.clicked.connect(lambda: self._move_rel(1))
        grid.addWidget(btn_neg, 1, 3); grid.addWidget(btn_pos, 1, 4)

        # Absolute move
        grid.addWidget(QLabel("Move absolute:"), 2, 0)
        self.ed_abs = QLineEdit("0"); self.ed_abs.setValidator(self.fl_val)
        grid.addWidget(self.ed_abs, 2, 1)
        self.cmb_unit_abs = QComboBox(); self.cmb_unit_abs.addItems(UNIT_FACT.keys())
        grid.addWidget(self.cmb_unit_abs, 2, 2)
        btn_go = QPushButton("Go to absolute"); btn_go.clicked.connect(self._move_abs)
        grid.addWidget(btn_go, 2, 3, 1, 2)

        # Control buttons
        btn_home = QPushButton("Home");  btn_home.clicked.connect(lambda: self._run_async(self.api.home))
        btn_flash = QPushButton("Flash"); btn_flash.clicked.connect(lambda: self._run_async(self.api.flash))
        btn_stop = QPushButton("STOP")
        btn_stop.setStyleSheet("background:#d9534f;color:white;font-weight:bold;")
        btn_stop.clicked.connect(lambda: self._run_async(self.api.stop))
        grid.addWidget(btn_home, 3, 0); grid.addWidget(btn_flash, 3, 1)
        grid.addWidget(btn_stop, 3, 2, 1, 3)

        main_v.addWidget(mot_g)
        main_v.addStretch()

        # Status bar
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)

    # main_window.py
    def _discover_backends(self, hint=None):
        """Populate backend dropdown with *verified* TDC001 servers only."""
        if hint and hint != "auto":
            # Still verify the user-supplied hint so we don’t crash later
            candidates = [hint] if _is_backend(hint, 0.3) else []
        else:
            candidates = scan_for_backends()          # already does localhost + host.docker.internal + LAN

        self.cmb_backend.clear()
        for url in candidates:
            self.cmb_backend.addItem(url)

        if self.cmb_backend.count():
            self._on_backend_change(self.cmb_backend.currentText())

    def _add_backend(self):
        """Save user-typed backend URL into dropdown."""
        url = self.cmb_backend.currentText().strip()
        if url and self.cmb_backend.findText(url) == -1:
            self.cmb_backend.addItem(url)
            self.cmb_backend.setCurrentText(url)

    def _on_backend_change(self, url):
        """When backend changes, fetch available cube-ports."""
        if not url:
            return
        self.api = APIClient(url)
        self.statusbar.showMessage("Loading ports...", 2000)
        try:
            ports = self.api.list_ports()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"/ports failed:\n{e}")
            ports = []
        self.cmb_port.clear()
        self.cmb_port.addItems(ports)
        self.statusbar.showMessage(f"Ports: {ports}", 2000)

    def _on_preset(self, name):
        """Handle preset change: update steps_per_mm and save."""
        val = STEP_PRESETS.get(name)
        if val is None:
            self.ed_steps.setReadOnly(False)
        else:
            self.steps_per_mm = val
            self.ed_steps.setText(str(val))
            self.ed_steps.setReadOnly(True)
        self.settings["preset"]       = name
        self.settings["steps_per_mm"] = self.steps_per_mm
        save_settings(self.settings)

    def _to_counts(self, txt, cmb):
        """Convert text+unit into encoder counts."""
        try:
            dist = float(txt) * UNIT_FACT[cmb.currentText()]
        except:
            dist = 0.0
        try:
            self.steps_per_mm = int(self.ed_steps.text())
        except:
            pass
        return round(dist * self.steps_per_mm)

    def _move_rel(self, sign):
        """Move relative in background thread."""
        cnt = sign * abs(self._to_counts(self.ed_rel.text(), self.cmb_unit_rel))
        self.statusbar.showMessage("Moving relative...", 2000)
        self._run_async(self.api.move_rel, cnt)

    def _move_abs(self):
        """Move absolute in background thread."""
        cnt = self._to_counts(self.ed_abs.text(), self.cmb_unit_abs)
        self.statusbar.showMessage("Moving absolute...", 2000)
        self._run_async(self.api.move_abs, cnt)

    def _refresh_status(self):
        """Poll backend, update labels, and persist if idle & homed."""
        if not self.api:
            self.lbl_status.setText("Status: no backend")
            self.lbl_homed.setText("Homed: ✗")
            return
        try:
            st = self.api.status()
        except Exception as e:
            self.lbl_status.setText(f"Status: ⚠ {e}")
            return
        busy = st["moving_forward"] or st["moving_reverse"]
        homed_flag = st["homed"]
        pos = st["position"]
        self.lbl_status.setText("Status: moving" if busy else "Status: idle")
        self.lbl_homed.setText(f"Homed: {'✓' if homed_flag else '✗'}")
        mm = pos / self.steps_per_mm
        self.lbl_pos.setText(f"Pos: {pos} cnt | {mm:.3f} mm")
        if homed_flag and not busy:
            port = self.cmb_port.currentText().strip()
            key  = f"{self.api.base}|{port}"
            self.positions[key] = {
                "pos": pos,
                "time": datetime.datetime.now().isoformat(),
                "steps_per_mm": self.steps_per_mm,
                "homed": True
            }
            save_positions(self.positions)

    def _run_async(self, fn, *args):
        """Run a backend call in a Worker/QThread to keep UI responsive."""
        if not callable(fn):
            return
        worker = Worker(fn, *args)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda res, err: self._on_done(thread, worker, res, err))
        thread.start()

    def _on_done(self, thread, worker, res, err):
        """Cleanup after task and report errors or 'Done'."""
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()
        if err:
            QMessageBox.critical(self, "Error", str(err))
        else:
            self.statusbar.showMessage("Done", 2000)
            self._refresh_status()


if __name__ == "__main__":
    from run import main
    main()

