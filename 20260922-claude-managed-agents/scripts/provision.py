"""Idempotent provisioning: self-hosted Environment, custom skill, GitHub MCP
vault credential, and the Agent that ties them together.

Safe to re-run: every step checks `.provisioned.json` first and reuses the
existing resource instead of recreating it (see design.md D6). The Agent is
the one resource that is explicitly re-`update`d on every run so a change to
its config (model, tools, mcp_servers, skills) is picked up as a new agent
version without creating a second Agent.

Order: Environment -> skill -> MCP declaration validation -> vault/credential
-> Agent. Each step's ID is persisted to `.provisioned.json` immediately
after it succeeds, so a failure partway through leaves the completed steps
reusable on the next run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import anthropic
from anthropic.lib import files_from_dir

from common.config import (
    AnthropicConfig,
    GithubMcpConfig,
    load_provisioned,
    optional_env,
    update_provisioned,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG_PATH = REPO_ROOT / "mcp.json"
SKILL_DIR = REPO_ROOT / "skills" / "container-probe"
SKILL_NAME = "container-probe"

DEFAULT_MODEL = "claude-opus-5"
AGENT_NAME = "cma-self-hosted-verification"
MCP_SERVER_NAME = "github"


class ProvisionError(SystemExit):
    """A provisioning step failed in a way the user must fix before retrying."""


def load_mcp_declarations(path: Path = MCP_CONFIG_PATH) -> dict[str, dict[str, Any]]:
    """Parse `mcp.json` and validate every server declaration.

    Only `{"type": "url", "url": "..."}` declarations are accepted (Managed
    Agents self-hosted environments only support Streamable HTTP MCP
    servers). A `command` key (stdio server) or any non-`url` type is
    rejected outright, before any API call is made, per agent-provisioning's
    "URL 形式でないサーバ宣言は拒否される" requirement.
    """
    if not path.exists():
        raise ProvisionError(f"{path} が見つかりません。GitHub の hosted MCP を宣言してください。")

    raw = json.loads(path.read_text(encoding="utf-8"))
    servers = raw.get("mcpServers", {})
    if not servers:
        raise ProvisionError(f"{path} に mcpServers が定義されていません。")

    for name, decl in servers.items():
        if "command" in decl:
            raise ProvisionError(
                f"MCP サーバ宣言 '{name}' に command が含まれています。"
                "self-hosted 環境では stdio サーバ（command 形式）は使えません。"
                "url 形式（Streamable HTTP）のみ受け付けます。"
            )
        if decl.get("type") != "url":
            raise ProvisionError(
                f"MCP サーバ宣言 '{name}' の type が 'url' ではありません ({decl.get('type')!r})。"
                "self-hosted 環境で使えるのは url 形式のみです。"
            )
        if not decl.get("url"):
            raise ProvisionError(f"MCP サーバ宣言 '{name}' に url がありません。")

    return servers


def ensure_environment(client: anthropic.Anthropic, state: dict[str, Any]) -> str:
    environment_id = state.get("environment_id")
    if environment_id:
        env = client.beta.environments.retrieve(environment_id=environment_id)
        print(f"[environment] reuse {env.id} (type={env.config.type})")
        return env.id

    env = client.beta.environments.create(
        name="cma-self-hosted-verification",
        config={"type": "self_hosted"},
    )
    if env.config.type != "self_hosted":
        raise ProvisionError(
            f"作成した Environment の config.type が self_hosted ではありません: {env.config.type!r}"
        )
    print(f"[environment] created {env.id} (type={env.config.type})")
    update_provisioned({"environment_id": env.id})
    return env.id


def ensure_skill(client: anthropic.Anthropic, state: dict[str, Any]) -> tuple[str, str]:
    skill_id = state.get("skill_id")
    files = files_from_dir(SKILL_DIR)

    if skill_id:
        version = client.skills.versions.create(skill_id=skill_id, files=files)
        print(f"[skill] {skill_id}: new version {version.id}")
        update_provisioned({"skill_id": skill_id, "skill_version": version.id})
        return skill_id, version.id

    skill = client.skills.create(files=files)
    print(f"[skill] created {skill.id}, version {skill.latest_version_id}")
    update_provisioned({"skill_id": skill.id, "skill_version": skill.latest_version_id})
    return skill.id, skill.latest_version_id


def ensure_github_vault_credential(
    client: anthropic.Anthropic, state: dict[str, Any], mcp_url: str
) -> str:
    vault_id = state.get("vault_id")
    if not vault_id:
        vault = client.beta.vaults.create(display_name="cma-self-hosted-verification")
        vault_id = vault.id
        print(f"[vault] created {vault_id}")
        update_provisioned({"vault_id": vault_id})
    else:
        print(f"[vault] reuse {vault_id}")

    credential_id = state.get("github_credential_id")
    if credential_id:
        print(f"[credential] reuse {credential_id}")
        return vault_id

    github = GithubMcpConfig.load()
    credential = client.beta.vaults.credentials.create(
        vault_id=vault_id,
        display_name="GitHub hosted MCP (static bearer)",
        auth={
            "type": "static_bearer",
            "mcp_server_url": mcp_url,
            "token": github.pat,
        },
    )
    assert not hasattr(credential, "token"), "credential response must not echo the token"
    print(f"[credential] created {credential.id} for {mcp_url}")
    update_provisioned({"github_credential_id": credential.id})
    return vault_id


def build_agent_config(mcp_servers: dict[str, dict[str, Any]], skill_id: str) -> dict[str, Any]:
    return {
        "name": AGENT_NAME,
        "model": optional_env("CMA_AGENT_MODEL", DEFAULT_MODEL),
        "mcp_servers": [
            {"type": "url", "name": name, "url": decl["url"]} for name, decl in mcp_servers.items()
        ],
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": True},
                "configs": [
                    {"name": "web_search", "enabled": False},
                    {"name": "web_fetch", "enabled": False},
                ],
            },
            *[
                {"type": "mcp_toolset", "mcp_server_name": name}
                for name in mcp_servers
            ],
        ],
        # `version` is deliberately omitted (defaults to "latest"): passing an
        # explicit `skver_...` id makes the *session's* resolved-agent snapshot
        # store an internal numeric version id instead, which the worker's
        # skill download then rejects with `Invalid version id` (discovered
        # via live verification — see design.md D9). "latest" is the only
        # value that downloads correctly.
        "skills": [
            {"type": "custom", "skill_id": skill_id},
        ],
    }


def ensure_agent(client: anthropic.Anthropic, state: dict[str, Any], config: dict[str, Any]) -> str:
    agent_id = state.get("agent_id")
    if agent_id:
        agent = client.beta.agents.update(agent_id=agent_id, **config)
        print(f"[agent] {agent_id}: updated to version {agent.version}")
    else:
        agent = client.beta.agents.create(**config)
        print(f"[agent] created {agent.id}, version {agent.version}")

    update_provisioned({"agent_id": agent.id, "agent_version": agent.version})
    return agent.id


def main() -> None:
    anthropic_config = AnthropicConfig.load()
    client = anthropic.Anthropic(api_key=anthropic_config.api_key)

    mcp_servers = load_mcp_declarations()
    state = load_provisioned()

    ensure_environment(client, state)
    state = load_provisioned()

    skill_id, skill_version = ensure_skill(client, state)
    state = load_provisioned()

    github_mcp_url = mcp_servers[MCP_SERVER_NAME]["url"]
    ensure_github_vault_credential(client, state, github_mcp_url)
    state = load_provisioned()

    agent_config = build_agent_config(mcp_servers, skill_id)
    ensure_agent(client, state, agent_config)

    print("[provision] done. State written to .provisioned.json")


if __name__ == "__main__":
    try:
        main()
    except ProvisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
