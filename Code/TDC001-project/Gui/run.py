# === File: run.py ===
import os, sys, argparse, shutil, subprocess
from PyQt6.QtWidgets import QApplication
from main_window import MainWindow


def main():
    p = argparse.ArgumentParser(description="TDC001 Docker‐UI launcher")
    p.add_argument("--backend", default=os.getenv("BACKEND_URL", "auto"))
    args = p.parse_args()

    # optional Xvfb+noVNC support for headless Docker
    if os.getenv("USE_NOVNC"):
        if shutil.which("Xvfb") and shutil.which("websockify"):
            subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
            subprocess.Popen(["websockify", "6080", "localhost:5900"])

    app = QApplication(sys.argv)
    w   = MainWindow(args.backend)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
