"""設定: .env の読み込み。キーの値は出力しない。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-haiku-5-5"
RESULTS = ROOT / "results"
SKILL_NAME = "sandbox-probe"
SKILL_DIR = ROOT / "skills" / SKILL_NAME

load_dotenv(ROOT / ".env")


def _require(*names: str, hint: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise RuntimeError(f"{' または '.join(names)} が設定されていません。{hint}")


def anthropic_api_key() -> str:
    return _require("CLAUDE_API_KEY", "ANTHROPIC_API_KEY", hint=".env に CLAUDE_API_KEY を書いてください")


def jev_api_key() -> str:
    return _require("JEV_API_TOKEN", hint=".env に JEV_API_TOKEN を書いてください")


def environment_id() -> str:
    return _require("ANTHROPIC_ENVIRONMENT_ID", hint="scripts/provision.py の結果を .env に書いてください")


def environment_key() -> str:
    return _require("ANTHROPIC_ENVIRONMENT_KEY", hint="Console で Environment key を発行して .env に書いてください")


def has_environment_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_ENVIRONMENT_ID") and os.environ.get("ANTHROPIC_ENVIRONMENT_KEY"))


def secret_values() -> list[str]:
    """生成物に含まれていないことを確認するための秘密値(出力はしない)。"""
    names = ("CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "JEV_API_TOKEN", "ANTHROPIC_ENVIRONMENT_KEY")
    return [v for n in names if (v := os.environ.get(n))]
