import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
import requests

__all__ = ["APIClient", "scan_for_backends"]

# ---------------------------------------------------------------------------
# Low‑level REST wrapper ------------------------------------------------------
# ---------------------------------------------------------------------------

class APIClient:
    """Thin helper around the FastAPI‑based **TDC001** backend.

    It purposefully *does not* swallow exceptions so the GUI can surface
    connection problems to the user.
    """

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()

    # ─── private helpers ────────────────────────────────────────────────────
    def _url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def _req(self, method: str, path: str, timeout: float = 3, **kw):
        r = self.session.request(method, self._url(path), timeout=timeout, **kw)
        r.raise_for_status()
        # Be defensive: only attempt JSON if Content‑Type hints at it
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return {}

    # ─── public API mirrors backend endpoints ───────────────────────────────
    def list_ports(self) -> List[str]:      return self._req("GET",  "/ports")
    def status(self) -> dict:               return self._req("GET",  "/status")
    def connect(self, port: str):           return self._req("POST", "/connect",  json={"port": port})
    def move_rel(self, steps: int):         return self._req("POST", "/move_rel", json={"steps": steps},    timeout=150)
    def move_abs(self, position: int):      return self._req("POST", "/move_abs", json={"position": position}, timeout=150)
    def home(self):                         return self._req("POST", "/home",     timeout=120)
    def flash(self):                        return self._req("POST", "/identify")
    def stop(self):                         return self._req("POST", "/stop")

# ---------------------------------------------------------------------------
# LAN discovery helper --------------------------------------------------------
# ---------------------------------------------------------------------------

def _is_backend(url: str, timeout: float) -> Optional[str]:
    """Return *url* if it hosts a TDC001 backend, else ``None``."""
    try:
        r = requests.get(f"{url}/ping", timeout=timeout)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            if r.json().get("backend") == "TDC001":
                return url
    except requests.RequestException:
        pass  # silence network errors during scan
    return None


def scan_for_backends(port: int = 8000, timeout: float = 0.25, workers: int = 64) -> List[str]:
    """Return a *deduplicated* list of reachable **TDC001** backends on the LAN.

    Strategy (mirrors rock‑solid v1.8 behaviour):
    1.  Check well‑known hosts: ``127.0.0.1`` and ``host.docker.internal`` (if resolvable).
    2.  Probe our own /24 subnet – cheap and reliable in most labs.
    3.  Fall‑back scan of the common lab nets ``192.168.0.*``, ``192.168.1.*`` and ``10.0.0.*``.

    Each candidate is verified via ``GET /ping`` → must return
    ``{"backend": "TDC001"}`` to be accepted.  This prevents the GUI from
    clogging the dropdown with random port‑8000 servers or gateways.
    """
    hosts: List[str] = []

    # ① canonical localhost variants -------------------------------------------------
    hosts.extend(["127.0.0.1"])  # always valid
    try:
        socket.gethostbyname("host.docker.internal")
        hosts.append("host.docker.internal")
    except socket.gaierror:
        pass  # not defined on this platform → ignore

    # ② our own /24 -------------------------------------------------------------------
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    prefix = ".".join(local_ip.split(".")[:3])
    hosts.extend(f"{prefix}.{i}" for i in range(1, 255))

    # ③ common lab sub‑nets ------------------------------------------------------------
    hosts.extend(f"192.168.{sub}.{i}" for sub in (0, 2) for i in range(1, 255))
    hosts.extend(f"10.0.0.{i}" for i in range(1, 255))

    # ─── probe candidates concurrently ─────────────────────────────────────────
    urls = [f"http://{h}:{port}" for h in dict.fromkeys(hosts)]  # dedupe early
    found: List[str] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_is_backend, u, timeout) for u in urls]
        for f in as_completed(futures):
            hit = f.result()
            if hit and hit not in found:
                found.append(hit)
    return found

