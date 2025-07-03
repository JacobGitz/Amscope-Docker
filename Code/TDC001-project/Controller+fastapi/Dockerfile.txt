# ───────── base image ─────────
FROM python:3.13-slim

# Install only what we *actually* need
RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 dbus avahi-daemon avahi-utils \
 && rm -rf /var/lib/apt/lists/*
# ───────── copy code ─────────
WORKDIR /app
COPY tdc_server.py tdc001.py ./

# Add entrypoint and make it executable
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# ───────── dependencies ──────
ARG PIP_NO_INDEX=1
COPY requirements.lock .
COPY wheelhouse/ ./wheelhouse/
RUN if [ "$PIP_NO_INDEX" = "1" ]; then \
        pip install --no-index --find-links=wheelhouse -r requirements.lock ; \
    else \
        pip install --no-cache-dir -r requirements.lock ; \
    fi

# ───────── runtime params ────
EXPOSE 8000/tcp
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./entrypoint.sh"]

