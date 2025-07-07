# === File: tdc_ui/worker.py ===
from PyQt6.QtCore import QObject, pyqtSignal

class Worker(QObject):
    """Runs any function in a QThread and emits (result, error)."""
    finished = pyqtSignal(object, object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args

    def run(self):
        try:
            res = self.fn(*self.args)
            err = None
        except Exception as e:
            res, err = None, e
        self.finished.emit(res, err)
