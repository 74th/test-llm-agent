import pytest

from verify import config


@pytest.mark.parametrize(
    "func,names",
    [
        (config.anthropic_api_key, ["CLAUDE_API_KEY", "ANTHROPIC_API_KEY"]),
        (config.jev_api_key, ["JEV_API_TOKEN"]),
        (config.environment_id, ["ANTHROPIC_ENVIRONMENT_ID"]),
        (config.environment_key, ["ANTHROPIC_ENVIRONMENT_KEY"]),
    ],
)
def test_missing_key_raises(monkeypatch, func, names):
    for n in names:
        monkeypatch.delenv(n, raising=False)
    with pytest.raises(RuntimeError) as e:
        func()
    assert names[0] in str(e.value)


def test_key_value_not_in_error(monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "secret-xyz")
    assert config.anthropic_api_key() == "secret-xyz"
    monkeypatch.delenv("JEV_API_TOKEN")
    with pytest.raises(RuntimeError) as e:
        config.jev_api_key()
    assert "secret-xyz" not in str(e.value)


def test_model():
    assert config.MODEL == "claude-haiku-5-5"
