import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import scripts.provision as provision


def test_load_mcp_declarations_accepts_url_type(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"github": {"type": "url", "url": "https://x/mcp"}}}))
    servers = provision.load_mcp_declarations(path)
    assert servers["github"]["url"] == "https://x/mcp"


def test_load_mcp_declarations_rejects_command(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"local": {"command": "npx", "args": ["foo"]}}}))
    with pytest.raises(provision.ProvisionError, match="command"):
        provision.load_mcp_declarations(path)


def test_load_mcp_declarations_rejects_non_url_type(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"sse": {"type": "sse", "url": "https://x/mcp"}}}))
    with pytest.raises(provision.ProvisionError, match="url"):
        provision.load_mcp_declarations(path)


def test_load_mcp_declarations_missing_file(tmp_path):
    with pytest.raises(provision.ProvisionError):
        provision.load_mcp_declarations(tmp_path / "does-not-exist.json")


def test_ensure_environment_creates_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(provision, "update_provisioned", lambda patch: None)
    client = MagicMock()
    client.beta.environments.create.return_value = SimpleNamespace(
        id="env_new", config=SimpleNamespace(type="self_hosted")
    )
    env_id = provision.ensure_environment(client, {})
    assert env_id == "env_new"
    client.beta.environments.create.assert_called_once()
    client.beta.environments.retrieve.assert_not_called()


def test_ensure_environment_reuses_when_present(monkeypatch):
    client = MagicMock()
    client.beta.environments.retrieve.return_value = SimpleNamespace(
        id="env_existing", config=SimpleNamespace(type="self_hosted")
    )
    env_id = provision.ensure_environment(client, {"environment_id": "env_existing"})
    assert env_id == "env_existing"
    client.beta.environments.create.assert_not_called()


def test_ensure_environment_rejects_non_self_hosted(monkeypatch):
    monkeypatch.setattr(provision, "update_provisioned", lambda patch: None)
    client = MagicMock()
    client.beta.environments.create.return_value = SimpleNamespace(
        id="env_new", config=SimpleNamespace(type="cloud")
    )
    with pytest.raises(provision.ProvisionError):
        provision.ensure_environment(client, {})


def test_ensure_skill_creates_then_versions(monkeypatch, tmp_path):
    monkeypatch.setattr(provision, "update_provisioned", lambda patch: None)
    monkeypatch.setattr(provision, "files_from_dir", lambda d: [("SKILL.md", b"...")])
    client = MagicMock()
    client.skills.create.return_value = SimpleNamespace(id="skill_1", latest_version_id="1")

    skill_id, version = provision.ensure_skill(client, {})
    assert (skill_id, version) == ("skill_1", "1")
    client.skills.create.assert_called_once()
    client.skills.versions.create.assert_not_called()

    client.skills.versions.create.return_value = SimpleNamespace(id="2")
    skill_id2, version2 = provision.ensure_skill(client, {"skill_id": "skill_1"})
    assert (skill_id2, version2) == ("skill_1", "2")
    client.skills.versions.create.assert_called_once_with(skill_id="skill_1", files=[("SKILL.md", b"...")])


def test_ensure_agent_creates_then_updates(monkeypatch):
    monkeypatch.setattr(provision, "update_provisioned", lambda patch: None)
    client = MagicMock()
    client.beta.agents.create.return_value = SimpleNamespace(id="agent_1", version="1")

    agent_id = provision.ensure_agent(client, {}, {"name": "x"})
    assert agent_id == "agent_1"
    client.beta.agents.update.assert_not_called()

    client.beta.agents.update.return_value = SimpleNamespace(id="agent_1", version="2")
    agent_id2 = provision.ensure_agent(client, {"agent_id": "agent_1"}, {"name": "x"})
    assert agent_id2 == "agent_1"
    client.beta.agents.create.assert_called_once()  # still just the first call


def test_ensure_github_vault_credential_reuses_credential(monkeypatch):
    client = MagicMock()
    vault_id = provision.ensure_github_vault_credential(
        client,
        {"vault_id": "vlt_1", "github_credential_id": "cred_1"},
        "https://api.githubcopilot.com/mcp/",
    )
    assert vault_id == "vlt_1"
    client.beta.vaults.create.assert_not_called()
    client.beta.vaults.credentials.create.assert_not_called()


def test_ensure_github_vault_credential_creates_when_absent(monkeypatch):
    monkeypatch.setattr(provision, "update_provisioned", lambda patch: None)
    monkeypatch.setenv("GITHUB_PAT", "ghp_test")
    client = MagicMock()
    client.beta.vaults.create.return_value = SimpleNamespace(id="vlt_new")
    client.beta.vaults.credentials.create.return_value = SimpleNamespace(id="cred_new")

    vault_id = provision.ensure_github_vault_credential(client, {}, "https://api.githubcopilot.com/mcp/")
    assert vault_id == "vlt_new"
    _, kwargs = client.beta.vaults.credentials.create.call_args
    assert kwargs["auth"]["type"] == "static_bearer"
    assert kwargs["auth"]["token"] == "ghp_test"


def test_build_agent_config_disables_web_tools_and_wires_mcp_and_skill():
    config = provision.build_agent_config(
        {"github": {"type": "url", "url": "https://x/mcp"}}, "skill_1"
    )
    assert config["model"] == "claude-opus-5"
    toolset = config["tools"][0]
    disabled = {c["name"] for c in toolset["configs"] if c["enabled"] is False}
    assert disabled == {"web_search", "web_fetch"}
    assert {"type": "mcp_toolset", "mcp_server_name": "github"} in config["tools"]
    assert config["mcp_servers"] == [{"type": "url", "name": "github", "url": "https://x/mcp"}]
    # `version` is deliberately omitted: an explicit skver_... id breaks the
    # worker's skill download (see provision.py build_agent_config).
    assert config["skills"] == [{"type": "custom", "skill_id": "skill_1"}]
