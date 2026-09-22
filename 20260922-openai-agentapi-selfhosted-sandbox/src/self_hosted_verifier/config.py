from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when a required environment setting is absent or invalid."""


def _required(env: dict[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    executor_api_key: str
    model: str
    image: str
    workspace_directory: str
    state_dir: Path
    log_dir: Path
    report_dir: Path
    agent_instructions: str = (
        "You are a verification assistant. Use the executor to read the requested "
        "marker and report the exact tool result."
    )
    capability_directories: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        values = dict(os.environ if env is None else env)
        workspace = values.get("OPENAI_WORKSPACE_DIRECTORY", "/workspace").strip()
        if not workspace.startswith("/"):
            raise ConfigurationError("OPENAI_WORKSPACE_DIRECTORY must be an absolute path")
        capability_directories = tuple(
            item.strip()
            for item in values.get("OPENAI_CAPABILITY_DIRECTORIES", "").split(",")
            if item.strip()
        )
        if any(not item.startswith("/") for item in capability_directories):
            raise ConfigurationError("OPENAI_CAPABILITY_DIRECTORIES entries must be absolute paths")
        return cls(
            openai_api_key=_required(values, "OPENAI_API_KEY"),
            executor_api_key=_required(values, "OPENAI_EXECUTOR_API_KEY"),
            model=_required(values, "OPENAI_MODEL"),
            image=values.get("OPENAI_EXECUTOR_IMAGE", "self-hosted-session-verifier:local"),
            workspace_directory=workspace,
            state_dir=Path(values.get("SELF_HOSTED_STATE_DIR", "state")),
            log_dir=Path(values.get("SELF_HOSTED_LOG_DIR", "logs")),
            report_dir=Path(values.get("SELF_HOSTED_REPORT_DIR", "reports")),
            agent_instructions=values.get(
                "OPENAI_AGENT_INSTRUCTIONS",
                "You are a verification assistant. Use the executor to read the requested "
                "marker and report the exact tool result.",
            ).strip(),
            capability_directories=capability_directories,
        )

    def ensure_directories(self) -> None:
        for directory in (self.state_dir, self.log_dir, self.report_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def public_dict(self) -> dict[str, str]:
        """Return safe settings for diagnostics; never include key values."""
        return {
            "model": self.model,
            "image": self.image,
            "workspace_directory": self.workspace_directory,
            "state_dir": str(self.state_dir),
            "log_dir": str(self.log_dir),
            "report_dir": str(self.report_dir),
            "capability_directories": ",".join(self.capability_directories),
        }
