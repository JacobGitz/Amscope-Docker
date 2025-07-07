#!/usr/bin/env bash
exec uvicorn tdc_server:app --host 0.0.0.0 --port 8000
