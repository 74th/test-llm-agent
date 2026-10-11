"""Managed Agents の準備: Environment(self_hosted)→ Skill → Agent(design D6)。

何度実行しても重複して作らない。ID は .provisioned.json に保存する(秘密の値は保存しない)。
Skill は実行のたびに新しいバージョンを作り、Agent は skills に version を指定せず(latest)更新する。

    uv run python scripts/provision.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import anthropic
from anthropic.lib import files_from_dir

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from verify.config import MODEL, ROOT, SKILL_DIR, SKILL_NAME, anthropic_api_key  # noqa: E402

STATE = ROOT / ".provisioned.json"
NAME = "verify-skills-in-sandbox"


def load() -> dict[str, Any]:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(patch: dict[str, Any]) -> dict[str, Any]:
    data = {**load(), **patch}
    STATE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def ensure_environment(client: anthropic.Anthropic, state: dict[str, Any]) -> str:
    if env_id := state.get("environment_id"):
        env = client.beta.environments.retrieve(environment_id=env_id)
        print(f"[environment] reuse {env.id} (type={env.config.type})")
        return env.id
    env = client.beta.environments.create(name=NAME, config={"type": "self_hosted"})
    print(f"[environment] created {env.id} (type={env.config.type})")
    save({"environment_id": env.id})
    return env.id


def ensure_skill(client: anthropic.Anthropic, state: dict[str, Any]) -> str:
    files = files_from_dir(SKILL_DIR)
    if skill_id := state.get("skill_id"):
        v = client.skills.versions.create(skill_id=skill_id, files=files)
        print(f"[skill] {skill_id}: new version {v.id}")
        save({"skill_version": v.id})
        return skill_id
    skill = client.skills.create(files=files, display_name=f"{SKILL_NAME} ({NAME})")
    print(f"[skill] created {skill.id}, version {skill.latest_version_id}")
    save({"skill_id": skill.id, "skill_version": skill.latest_version_id})
    return skill.id


def agent_config(skill_id: str) -> dict[str, Any]:
    return {
        "name": NAME,
        "model": MODEL,
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": True},
                "configs": [
                    {"name": "web_search", "enabled": False},
                    {"name": "web_fetch", "enabled": False},
                ],
            }
        ],
        # version は指定しない(latest)。明示すると、ワーカーのダウンロードが Invalid version id で失敗する。
        "skills": [{"type": "custom", "skill_id": skill_id}],
    }


def ensure_agent(client: anthropic.Anthropic, state: dict[str, Any], config: dict[str, Any]) -> str:
    if agent_id := state.get("agent_id"):
        current = client.beta.agents.retrieve(agent_id=agent_id)
        agent = client.beta.agents.update(agent_id=agent_id, version=current.version, **config)
        print(f"[agent] {agent_id}: updated to version {agent.version}")
    else:
        agent = client.beta.agents.create(**config)
        print(f"[agent] created {agent.id}, version {agent.version}")
    save({"agent_id": agent.id, "agent_version": agent.version})
    return agent.id


def main() -> None:
    client = anthropic.Anthropic(api_key=anthropic_api_key())
    ensure_environment(client, load())
    skill_id = ensure_skill(client, load())
    ensure_agent(client, load(), agent_config(skill_id))
    print(f"[provision] done -> {STATE.name}")


if __name__ == "__main__":
    main()
