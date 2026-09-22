"""Environment variable loading and `.provisioned.json` persistence.

All provisioning/verification scripts and the mode-B orchestrator import this
module instead of reading `os.environ` directly, so a missing prerequisite
fails with one consistent, actionable message.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_PROVISIONED_PATH = Path(
    os.environ.get("CMA_PROVISIONED_FILE", ".provisioned.json")
)


class ConfigError(SystemExit):
    """A required configuration value is missing or invalid.

    Subclasses SystemExit so scripts can let it propagate to a clean exit
    with a readable message, without every call site adding its own
    try/except.
    """


def require_env(name: str, how_to_set: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"必須の環境変数 {name} が設定されていません。{how_to_set}"
        )
    return value


def optional_env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


@dataclasses.dataclass(frozen=True)
class AnthropicConfig:
    api_key: str

    @classmethod
    def load(cls) -> "AnthropicConfig":
        return cls(
            api_key=require_env(
                "ANTHROPIC_API_KEY",
                "Anthropic Console で発行した API キーを `export ANTHROPIC_API_KEY=sk-ant-...` "
                "のように設定するか、`.env` に書いて読み込んでください。",
            )
        )


@dataclasses.dataclass(frozen=True)
class GithubMcpConfig:
    pat: str

    @classmethod
    def load(cls) -> "GithubMcpConfig":
        return cls(
            pat=require_env(
                "GITHUB_PAT",
                "GitHub で Personal Access Token を発行し、"
                "`export GITHUB_PAT=ghp_...` のように設定してください。",
            )
        )


@dataclasses.dataclass(frozen=True)
class EnvironmentWorkerConfig:
    """Credentials the worker/orchestrator need to talk to the environment's
    work queue. `ANTHROPIC_ENVIRONMENT_ID` / `ANTHROPIC_ENVIRONMENT_KEY` are
    also read directly by `EnvironmentWorker` itself; this wrapper exists so
    the orchestrator (which drives the mid-level poller, not the worker
    class) gets the same missing-variable error message.
    """

    environment_id: str
    environment_key: str

    @classmethod
    def load(cls) -> "EnvironmentWorkerConfig":
        return cls(
            environment_id=require_env(
                "ANTHROPIC_ENVIRONMENT_ID",
                "`scripts/provision.py` を実行して self-hosted Environment を作成し、"
                "`.provisioned.json` の environment_id を `export ANTHROPIC_ENVIRONMENT_ID=env_...` "
                "として設定してください。",
            ),
            environment_key=require_env(
                "ANTHROPIC_ENVIRONMENT_KEY",
                "Console で Environment 用のキーを発行し、"
                "`export ANTHROPIC_ENVIRONMENT_KEY=...` として設定してください。",
            ),
        )


def load_provisioned(path: Path | None = None) -> dict[str, Any]:
    """Read `.provisioned.json`, returning `{}` if it does not exist yet."""
    target = path or DEFAULT_PROVISIONED_PATH
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def save_provisioned(data: dict[str, Any], path: Path | None = None) -> None:
    """Overwrite `.provisioned.json` with `data`."""
    target = path or DEFAULT_PROVISIONED_PATH
    target.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update_provisioned(patch: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Merge `patch` into the existing `.provisioned.json` and save it."""
    data = load_provisioned(path)
    data.update(patch)
    save_provisioned(data, path)
    return data
