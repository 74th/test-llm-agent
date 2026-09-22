import pytest

from common import config


def test_require_env_missing_raises_with_name_and_howto(monkeypatch):
    monkeypatch.delenv("SOME_VAR", raising=False)
    with pytest.raises(config.ConfigError) as exc_info:
        config.require_env("SOME_VAR", "do the thing to set it")
    message = str(exc_info.value)
    assert "SOME_VAR" in message
    assert "do the thing to set it" in message


def test_require_env_present_returns_value(monkeypatch):
    monkeypatch.setenv("SOME_VAR", "value")
    assert config.require_env("SOME_VAR", "unused") == "value"


def test_anthropic_config_missing_key_exits(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(config.ConfigError) as exc_info:
        config.AnthropicConfig.load()
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_anthropic_config_loads(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert config.AnthropicConfig.load().api_key == "sk-ant-test"


def test_github_mcp_config_missing_pat_exits(monkeypatch):
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    with pytest.raises(config.ConfigError) as exc_info:
        config.GithubMcpConfig.load()
    assert "GITHUB_PAT" in str(exc_info.value)


def test_environment_worker_config_missing_reports_missing_name(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_ENVIRONMENT_ID", raising=False)
    monkeypatch.delenv("ANTHROPIC_ENVIRONMENT_KEY", raising=False)
    with pytest.raises(config.ConfigError) as exc_info:
        config.EnvironmentWorkerConfig.load()
    assert "ANTHROPIC_ENVIRONMENT_ID" in str(exc_info.value)


def test_provisioned_roundtrip(tmp_path):
    path = tmp_path / ".provisioned.json"

    assert config.load_provisioned(path) == {}

    config.save_provisioned({"environment_id": "env_1"}, path)
    assert config.load_provisioned(path) == {"environment_id": "env_1"}

    result = config.update_provisioned({"agent_id": "agent_1"}, path)
    assert result == {"environment_id": "env_1", "agent_id": "agent_1"}
    assert config.load_provisioned(path) == {"environment_id": "env_1", "agent_id": "agent_1"}
