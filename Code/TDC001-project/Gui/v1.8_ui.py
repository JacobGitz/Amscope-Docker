#!/usr/bin/env python3
import sys
import os
import json
import datetime
import socket
import shutil
import subprocess
from functools import partial
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
import requests
import argparse

from PyQt6.QtGui import QIcon, QIntValidator, QDoubleValidator
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QComboBox, QLineEdit,
    QPushButton, QVBoxLayout, QFormLayout, QGroupBox,
    QGridLayout, QStatusBar, QMessageBox
)
from PyQt6.QtCore import QTimer, QObject, pyqtSignal, QThread

STORAGE_PATH = os.path.expanduser('~/.tdc001_positions.json')

def load_positions() -> Dict[str, Dict]:
    try:
        with open(STORAGE_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_positions(data: Dict[str, Dict]):
    try:
        os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
        with open(STORAGE_PATH, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass

class APIClient:
    def __init__(self, base: str):
        self.base = base.rstrip('/')
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base}{path if path.startswith('/') else '/' + path}"

    def _req(self, method: str, path: str, timeout: float = 3, **kwargs):
        resp = self.session.request(method, self._url(path), timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    list_ports = lambda self: self._req('get', '/ports')
    status     = lambda self: self._req('get', '/status')
    connect    = lambda self, p: self._req('post', '/connect', json={'port': p})
    move_rel   = lambda self, s: self._req('post', '/move_rel', timeout=120, json={'steps': s})
    move_abs   = lambda self, p: self._req('post', '/move_abs', timeout=120, json={'position': p})
    home       = lambda self: self._req('post', '/home', timeout=120)
    flash      = lambda self: self._req('post', '/identify')
    stop       = lambda self: self._req('post', '/stop')


def scan_for_backends(port: int = 8000, timeout: float = 0.25, workers: int = 64) -> List[str]:
    subnets: List[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        subnets.append('.'.join(ip.split('.')[:3]))
    except:
        pass
    targets = ['127.0.0.1', 'host.docker.internal']
    for p in subnets + ['192.168.0', '192.168.1', '10.0.0']:
        targets.extend(f'{p}.{i}' for i in range(1, 255))
    found: List[str] = []
    def ping(h: str) -> Optional[str]:
        try:
            r = requests.get(f'http://{h}:{port}/ping', timeout=timeout)
            if r.status_code == 200 and r.json().get('backend') == 'TDC001':
                return f'http://{h}:{port}'
        except:
            pass
        return None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(ping, targets):
            if res and res not in found:
                found.append(res)
    return found

class Worker(QObject):
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
            res = None
            err = e
        self.finished.emit(res, err)

class MainWindow(QMainWindow):
    STEP_PRESETS = {
        'T-Cube 0.5 mm lead': 51200,
        'T-Cube 1.0 mm lead': 25600,
        'MTS28-Z8': 34555,
        'Manual set…': None
    }
    UNIT_FACT = {'mm': 1.0, 'µm': 1e-3}

    def __init__(self, backend: Optional[str] = None):
        super().__init__()
        self.setWindowTitle('Thorlabs TDC001 Controller')
        self.setWindowIcon(QIcon.fromTheme('applications-engineering'))
        self.resize(900, 600)
        self.api: Optional[APIClient] = None
        self.steps_per_mm = self.STEP_PRESETS['T-Cube 0.5 mm lead'] or 1
        self.positions = load_positions()
        self.homed = False
        self._iv = QIntValidator(1, 1_000_000, self)
        self._dv = QDoubleValidator(0.0, 1e6, 6, self)
        self._build_ui()
        self._populate_backends(backend)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)
        self._refresh()

    def _run_async(self, fn, *args):
        if not callable(fn):
            return
        worker = Worker(fn, *args)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda res, err: self._on_done(thread, worker, res, err))
        thread.start()

    def _on_done(self, thread, worker, res, err):
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()
        if err:
            QMessageBox.critical(self, 'Error', str(err))
        else:
            self.sb.showMessage('Done', 2000)
            self._refresh(save=True)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        self.lbl = QLabel('Status: —')
        main.addWidget(self.lbl)
        self.pos = QLabel('')
        main.addWidget(self.pos)
        self.sb = QStatusBar()
        self.setStatusBar(self.sb)

        net = QGroupBox('Network')
        form = QFormLayout(net)
        self.cmbB = QComboBox()
        self.cmbB.setEditable(True)
        self.cmbB.setPlaceholderText('http://<ip>:8000')
        self.cmbB.currentTextChanged.connect(self._load_ports)
        self.cmbB.currentIndexChanged.connect(lambda i: self._load_ports(self.cmbB.itemText(i)))
        btnAdd = QPushButton('Add')
        btnAdd.clicked.connect(lambda: self._load_ports(self.cmbB.currentText().strip(), add=True))
        self.cmbP = QComboBox()
        self.cmbP.activated.connect(self._connect)
        form.addRow('Backend:', self.cmbB)
        form.addRow('', btnAdd)
        form.addRow('Cube port:', self.cmbP)
        main.addWidget(net)

        mot = QGroupBox('Motion')
        grid = QGridLayout(mot)
        self.pr = QComboBox()
        self.pr.addItems(self.STEP_PRESETS.keys())
        self.pr.currentTextChanged.connect(self._on_preset)
        self.es = QLineEdit(str(self.steps_per_mm))
        self.es.setValidator(self._iv)
        grid.addWidget(QLabel('Steps/mm preset:'), 0, 0)
        grid.addWidget(self.pr, 0, 1, 1, 2)
        grid.addWidget(self.es, 0, 3)

        self.er = QLineEdit('0')
        self.er.setValidator(self._dv)
        self.ur = QComboBox()
        self.ur.addItems(self.UNIT_FACT.keys())
        btnNeg = QPushButton('–')
        btnNeg.clicked.connect(partial(self._move_rel, -1))
        btnPos = QPushButton('+')
        btnPos.clicked.connect(partial(self._move_rel, 1))
        grid.addWidget(QLabel('Move relative:'), 1, 0)
        grid.addWidget(self.er, 1, 1)
        grid.addWidget(self.ur, 1, 2)
        grid.addWidget(btnNeg, 1, 3)
        grid.addWidget(btnPos, 1, 4)

        self.ea = QLineEdit('0')
        self.ea.setValidator(self._dv)
        self.ua = QComboBox()
        self.ua.addItems(self.UNIT_FACT.keys())
        btnGo = QPushButton('Go to absolute')
        btnGo.clicked.connect(self._move_abs)
        grid.addWidget(QLabel('Move absolute:'), 2, 0)
        grid.addWidget(self.ea, 2, 1)
        grid.addWidget(self.ua, 2, 2)
        grid.addWidget(btnGo, 2, 3, 1, 2)

        btnHome = QPushButton('Home')
        btnHome.clicked.connect(lambda: self._run_async(self.api.home) if self.api else None)
        btnFlash = QPushButton('Flash')
        btnFlash.clicked.connect(lambda: self._run_async(self.api.flash) if self.api else None)
        btnStop = QPushButton('STOP')
        btnStop.setStyleSheet('background:#d9534f; color:white; font-weight:bold;')
        btnStop.clicked.connect(lambda: self._run_async(self.api.stop) if self.api else None)
        grid.addWidget(btnHome, 3, 0, 1, 2)
        grid.addWidget(btnFlash, 3, 2)
        grid.addWidget(btnStop, 3, 3, 1, 2)
        main.addWidget(mot)
        main.addStretch()

    def _populate_backends(self, backend: Optional[str]):
        candidates: List[str] = []
        if backend and backend != 'auto':
            candidates = [backend]
        else:
            try:
                ip = socket.gethostbyname(socket.gethostname())
                candidates.append(f'http://{ip}:8000')
            except Exception:
                pass
            candidates += ['http://127.0.0.1:8000', 'http://host.docker.internal:8000']
            candidates += scan_for_backends()
        for u in dict.fromkeys(candidates):
            self.cmbB.addItem(u)
        if self.cmbB.count():
            self._load_ports(self.cmbB.currentText())

    def _load_ports(self, url: str, add: bool = False):
        url = url.strip()
        if add and url:
            seen = [self.cmbB.itemText(i) for i in range(self.cmbB.count())]
            if url not in seen:
                self.cmbB.addItem(url)
        if not url:
            return
        self.api = APIClient(url)
        self.sb.showMessage('Loading ports…', 2000)
        try:
            ports = self.api.list_ports()
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'/ports failed:\n{e}')
            ports = []
        self.cmbP.clear()
        self.cmbP.addItems(ports)
        self.sb.showMessage(f'Ports: {ports}', 5000)

    def _connect(self):
        if not self.api:
            return
        port = self.cmbP.currentText().strip()
        if not port:
            QMessageBox.warning(self, 'No port', 'Select a cube-port first.')
            return
        key = f'{self.api.base}|{port}'
        last = self.positions.get(key)
        if last:
            msg = (
                f"Previous position: {last['pos']} counts "
                f"({last['pos']/self.steps_per_mm:.3f} mm), saved on {last['time']}. Restore?"
            )
            choice = QMessageBox.question(
                self,
                'Restore position',
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if choice == QMessageBox.StandardButton.Yes:
                self.homed = True
                mm = last['pos'] / self.steps_per_mm
                self.ea.setText(f"{mm:.3f}")
                # update the pos label to reflect restored position
                self.pos.setText(f"Pos: {last['pos']} cnt | {mm:.3f} mm")
            else:
                self.homed = False
        try:
            self.api.connect(port)
            self.sb.showMessage('Connected', 2000)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'/connect failed:\n{e}')

    def _on_preset(self, name: str):
        val = self.STEP_PRESETS[name]
        if val is None:
            self.es.setReadOnly(False)
        else:
            self.es.setText(str(val))
            self.es.setReadOnly(True)
            self.steps_per_mm = val

    def _to_counts(self, txt: str, cmb: QComboBox) -> int:
        try:
            mm = float(txt) * self.UNIT_FACT[cmb.currentText()]
        except:
            mm = 0.0
        try:
            self.steps_per_mm = int(self.es.text())
        except:
            pass
        return round(mm * self.steps_per_mm)

    def _move_rel(self, sign: int):
        self.homed = False
        cnt = sign * abs(self._to_counts(self.er.text(), self.ur))
        self.sb.showMessage('Moving relative…', 2000)
        self._run_async(self.api.move_rel, cnt)

    def _move_abs(self):
        self.homed = False
        cnt = self._to_counts(self.ea.text(), self.ua)
        self.sb.showMessage('Moving absolute…', 2000)
        self._run_async(self.api.move_abs, cnt)

    def _refresh(self, save: bool = False):
        if not self.api:
            self.lbl.setText('Status: no backend')
            return
        try:
            st = self.api.status()
        except Exception as e:
            self.lbl.setText(f'Status: ⚠ {e}')
            return
        busy = st.get('moving_forward') or st.get('moving_reverse')
        if self.homed and not busy:
            self.lbl.setText('Status: homed')
        else:
            self.lbl.setText('Status: moving' if busy else 'Status: idle')
        pos = st.get('position', 0)
        self.pos.setText(f'Pos: {pos} cnt | {pos/self.steps_per_mm:.3f} mm')
        if save and not busy:
            port = self.cmbP.currentText().strip()
            key = f'{self.api.base}|{port}'
            self.positions[key] = {'pos': pos, 'time': datetime.datetime.now().isoformat()}
            save_positions(self.positions)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', default=os.getenv('BACKEND_URL', 'auto'))
    args = parser.parse_args()
    if os.getenv('USE_NOVNC'):
        xvfb = shutil.which('Xvfb')
        ws = shutil.which('websockify')
        if xvfb and ws:
            os.environ.setdefault('DISPLAY', ':99')
            subprocess.Popen([xvfb, ':99', '-screen', '0', '1280x800x24'])
            subprocess.Popen([ws, '6080', 'localhost:5900'])
    app = QApplication(sys.argv)
    w = MainWindow(args.backend)
    w.show()
    sys.exit(app.exec())

