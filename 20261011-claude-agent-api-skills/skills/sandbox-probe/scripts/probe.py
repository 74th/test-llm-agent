#!/usr/bin/env python3
"""実行場所を報告する。標準ライブラリだけを使う。"""

import os
import socket
import sys
from pathlib import Path

MARKER_FILE = Path("/etc/sandbox-marker")


def main() -> None:
    try:
        marker = MARKER_FILE.read_text().strip() or "EMPTY"
    except OSError:
        marker = "MISSING"
    print(f"PROBE_HOST: {socket.gethostname()}")
    print(f"PROBE_MARKER: {marker}")
    print(f"PROBE_CWD: {os.getcwd()}")
    print(f"PROBE_SCRIPT: {Path(__file__).resolve()}")
    print(f"PROBE_PYTHON: {sys.executable}")


if __name__ == "__main__":
    main()
