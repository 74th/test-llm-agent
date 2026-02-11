#!/bin/bash
uv run uvicorn server.server:app --host 0.0.0.0 --port 8000
