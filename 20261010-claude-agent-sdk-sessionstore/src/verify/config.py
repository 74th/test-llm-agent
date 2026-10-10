"""設定: .env の読み込みと Agent SDK のオプション生成。キーの値は出力しない。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-haiku-5-5"

load_dotenv(ROOT / ".env")


def anthropic_api_key() -> str:
    key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("CLAUDE_API_KEY が .env にありません")
    return key


def jev_api_key() -> str:
    key = os.environ.get("JEV_API_TOKEN")
    if not key:
        raise RuntimeError("JEV_API_TOKEN が .env にありません")
    return key


def sdk_env(config_dir: Path | None = None) -> dict[str, str]:
    """subprocess に渡す環境変数。config_dir を分けるとローカル transcript を共有しない。"""
    env = {"ANTHROPIC_API_KEY": anthropic_api_key()}
    if config_dir is None:
        config_dir = Path(tempfile.mkdtemp(prefix="claude-config-"))
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env
