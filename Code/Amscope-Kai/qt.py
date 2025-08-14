"""amcam_qt_app.py  (rev‑2)
High‑FPS live‑view GUI for AmScope / Toupcam cameras.

Changes in this revision
────────────────────────
✓ *Zero‑copy* frame transfer using a persistent `ctypes.create_string_buffer`.
✓ PullImageV2 done inside the SDK callback ⇒ GUI thread never blocks.
✓ Fixed‑size preview widget, **no auto‑scaling** (removes a full‑frame resample).
✓ Linux byte‑order switched to BGR to skip per‑pixel swaps.
✓ Optional on‑screen FPS counter (toggle with the ☑︎ below the preview).

API remains unchanged: `MainWin(gain, integration_time_us, res)`.
"""

from __future__ import annotations

import sys
import ctypes
import time
from typing import Optional

import amcam
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QCheckBox,
    QVBoxLayout,
    QHBoxLayout,
    QDesktopWidget,
    QMessageBox,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helper widgets
# ──────────────────────────────────────────────────────────────────────────────

class SnapWin(QWidget):
    """Separate window that shows still‑image captures."""

    def __init__(self, w: int, h: int):
        super().__init__()
        self.setWindowTitle("Snapshot")
        self.setFixedSize(w, h)
        self.label = QLabel(self)
        self.label.resize(w, h)
        self.label.setScaledContents(False)

    def show_frame(self, qimg: QImage):
        self.label.setPixmap(QPixmap.fromImage(qimg))
        self.show()


# ──────────────────────────────────────────────────────────────────────────────
# Main camera window
# ──────────────────────────────────────────────────────────────────────────────

class MainWin(QWidget):
    """Live‑view window. Compatible with the legacy *app.py* launcher."""

    eventImage = pyqtSignal(int)

    def __init__(
        self,
        gain: int = 100,
        integration_time_us: int = 10_000,
        res: str = "low",
    ) -> None:
        super().__init__()
        self.hcam: Optional[amcam.Amcam] = None
        self.buf: Optional[ctypes.Array] = None
        self.w = self.h = 0
        self.gain = gain
        self.integration = integration_time_us  # already in µs
        self.res = res.lower()

        # frame counter for FPS display
        self._frame_accum = 0
        self._last_tick = time.perf_counter()

        self._init_ui()
        self._init_camera()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        # center the window on whatever display we’re on
        self.setFixedSize(820, 640)  # temp; corrected once cam opens
        geo = self.frameGeometry()
        geo.moveCenter(QDesktopWidget().availableGeometry().center())
        self.move(geo.topLeft())

        # widgets
        self.label = QLabel(self)
        self.label.setScaledContents(False)  # don’t resample!

        self.cb_auto = QCheckBox("Auto Exposure", self)
        self.cb_auto.stateChanged.connect(self._on_auto_exp_toggled)

        self.cb_fps = QCheckBox("Show FPS", self)

        # layout
        cols = QVBoxLayout(self)
        cols.addWidget(self.label, stretch=1)
        row = QHBoxLayout()
        row.addWidget(self.cb_auto)
        row.addWidget(self.cb_fps)
        row.addStretch(1)
        cols.addLayout(row)

    # ── Camera setup ──────────────────────────────────────────────────────────

    def _init_camera(self) -> None:
        cams = amcam.Amcam.EnumV2()
        if not cams:
            self.setWindowTitle("No camera found")
            self.cb_auto.setEnabled(False)
            return

        self.camname = cams[0].displayname
        self.setWindowTitle(self.camname)
        self.eventImage.connect(self._on_event_image)

        try:
            self.hcam = amcam.Amcam.Open(cams[0].id)
        except amcam.HRESULTException as ex:
            QMessageBox.warning(self, "", f"Failed to open camera (hr=0x{ex.hr:x})")
            return

        # basic settings
        self.hcam.put_ExpoAGain(self.gain)
        self._clamp_and_set_exposure(self.integration)
        self._apply_resolution(self.res)

        # negotiate RGB/BGR for zero‑copy into QImage
        if sys.platform != "win32":
            self.hcam.put_Option(amcam.AMCAM_OPTION_BYTEORDER, 1)  # BGR on Linux/mac

        # internal buffer (mutable)
        stride = ((self.w * 24 + 31) // 32) * 4
        self.buf = ctypes.create_string_buffer(stride * self.h)

        # resize widget exactly to sensor size (no scaling cost)
        self.setFixedSize(self.w, self.h + 40)  # + controls bar
        self.label.setFixedSize(self.w, self.h)

        # reflect current auto‑exposure state
        self.cb_auto.setChecked(self.hcam.get_AutoExpoEnable())

        # start stream
        try:
            self.hcam.StartPullModeWithCallback(self._camera_cb, self)
        except amcam.HRESULTException as ex:
            QMessageBox.warning(self, "", f"Stream start failed (hr=0x{ex.hr:x})")
            return

    def _clamp_and_set_exposure(self, target_us: int) -> None:
        lo, hi, _ = self.hcam.get_ExpTimeRange()
        self.hcam.put_ExpoTime(max(lo, min(target_us, hi)))

    def _apply_resolution(self, res: str) -> None:
        match res:
            case "high":
                self.hcam.put_eSize(0)  # 2560×1922
            case "mid":
                self.hcam.put_eSize(1)  # 1280×960
            case _:
                self.hcam.put_eSize(2)  # 640×480
        self.w, self.h = self.hcam.get_Size()

    # ── Toupcam callback (runs in SDK thread) ─────────────────────────────––

    @staticmethod
    def _camera_cb(event: int, ctx: "MainWin") -> None:
        if event == amcam.AMCAM_EVENT_IMAGE:
            try:
                ctx.hcam.PullImageV2(ctx.buf, 24, None)
            except amcam.HRESULTException:
                return  # drop frame
            ctx.eventImage.emit(event)
        elif event == amcam.AMCAM_EVENT_STILLIMAGE:
            try:
                ctx.hcam.PullStillImageV2(ctx.buf, 24, None)
            except amcam.HRESULTException:
                return
            ctx.eventImage.emit(event)

    # ── Qt slot (runs in GUI thread) ─────────────────────────────────────────

    @pyqtSlot(int)
    def _on_event_image(self, event: int) -> None:
        # stride is constant → safe
        stride = ((self.w * 24 + 31) // 32) * 4
        qimg = QImage(self.buf, self.w, self.h, stride, QImage.Format_RGB888)

        if event == amcam.AMCAM_EVENT_IMAGE:
            self.label.setPixmap(QPixmap.fromImage(qimg))
            self._update_fps()
        else:  # still image
            if not hasattr(self, "_snap_win"):
                self._snap_win = SnapWin(self.w, self.h)
            self._snap_win.show_frame(qimg)

    # ── Misc callbacks ──────────────────────────────────────────────────────

    def _on_auto_exp_toggled(self, state: int) -> None:
        if self.hcam:
            self.hcam.put_AutoExpoEnable(state == Qt.Checked)

    def _update_fps(self) -> None:
        if not self.cb_fps.isChecked():
            return
        self._frame_accum += 1
        now = time.perf_counter()
        if now - self._last_tick >= 1.0:
            fps = self._frame_accum / (now - self._last_tick)
            self.setWindowTitle(f"{self.camname} – {fps:.1f} fps")
            self._frame_accum = 0
            self._last_tick = now

    # ── API for *app.py* ────────────────────────────────────────────────────

    def snap(self):
        if self.hcam:
            self.hcam.Snap(0)

    # ── Cleanup ─────────────────────────────────────────────────────────────

    def closeEvent(self, evt):  # noqa: N802 (Qt override)
        if self.hcam:
            self.hcam.Close()
            self.hcam = None
        super().closeEvent(evt)


# ──────────────────────────────────────────────────────────────────────────────
# Stand‑alone entry point (for direct testing)  →   $ python -m amcam_qt_app
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWin()
    w.show()
    sys.exit(app.exec())
