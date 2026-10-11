"""Agent SDK の実行ヘルパー: 組み込みツールを無効にし、sandboxd を呼ぶ in-process MCP の tool を出す。

design D3 / D4:
- ホストのプロジェクト `<tmp>/project` を cwd にし、`.claude/skills/sandbox-probe` にスキルを置く。
- サンドボックス用の tool は、引数に含まれる `<tmp>/project` を `/workspace` に置き換えてから
  sandboxd に渡す。置き換え前(raw)と後(mapped)の値を記録する。
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from .config import MODEL, SKILL_DIR, SKILL_NAME, anthropic_api_key
from .sandboxd import ROOT_DIR, SandboxdClient

Condition = Literal["A", "B", "C", "plain"]

SERVER = "sandbox"
SANDBOX_TOOLS = [f"mcp__{SERVER}__sandbox_exec", f"mcp__{SERVER}__sandbox_read_file", f"mcp__{SERVER}__sandbox_list_dir"]
SANDBOX_SKILL_DIR = f"{ROOT_DIR}/.claude/skills/{SKILL_NAME}"

SYSTEM_PROMPT = (
    "あなたは検証用アシスタントです。コマンドの実行とファイルの操作には、提供されているツールを使ってください。"
)


@dataclass
class SandboxCall:
    tool: str
    raw: dict[str, Any]
    mapped: dict[str, Any]
    replaced: bool
    result: dict[str, Any]


class PathMapper:
    """ホストのプロジェクトのパスを、サンドボックスの /workspace に置き換える。"""

    def __init__(self, host_root: Path | str, sandbox_root: str = ROOT_DIR):
        self.host_root = str(host_root).rstrip("/")
        self.sandbox_root = sandbox_root

    def __call__(self, value: str) -> str:
        return value.replace(self.host_root, self.sandbox_root)


def make_sandbox_server(client: SandboxdClient, mapper: PathMapper, log: list[SandboxCall]):
    def record(name: str, raw: dict[str, Any], mapped: dict[str, Any], result: dict[str, Any]) -> None:
        log.append(SandboxCall(name, raw, mapped, raw != mapped, result))

    def text(s: str, is_error: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {"content": [{"type": "text", "text": s}]}
        if is_error:
            out["is_error"] = True
        return out

    @tool(
        "sandbox_exec",
        "サンドボックスでシェルコマンドを実行し、終了コード・標準出力・標準エラーを返す。"
        "コマンドは `sh -c` で実行され、カレントディレクトリは /workspace。呼び出しのあいだで状態は持ち越されない。",
        {"command": str},
    )
    async def sandbox_exec(args: dict[str, Any]) -> dict[str, Any]:
        raw = {"command": args["command"]}
        mapped = {"command": mapper(args["command"])}
        r = client.exec(mapped["command"])
        record("sandbox_exec", raw, mapped, r.to_dict())
        if r.error:
            return text(f"error: {r.error}", True)
        return text(f"exit_code: {r.exit_code}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}", r.exit_code != 0)

    @tool("sandbox_read_file", "サンドボックス内のファイルを読み、内容を返す。", {"path": str})
    async def sandbox_read_file(args: dict[str, Any]) -> dict[str, Any]:
        raw = {"path": args["path"]}
        mapped = {"path": mapper(args["path"])}
        r = client.read(mapped["path"])
        record("sandbox_read_file", raw, mapped, r.to_dict())
        if not r.ok:
            return text(f"error ({r.status}): {r.error}", True)
        return text(r.content or "")

    @tool("sandbox_list_dir", "サンドボックス内のディレクトリの一覧を返す。", {"path": str})
    async def sandbox_list_dir(args: dict[str, Any]) -> dict[str, Any]:
        raw = {"path": args["path"]}
        mapped = {"path": mapper(args["path"])}
        r = client.list(mapped["path"])
        record("sandbox_list_dir", raw, mapped, r.to_dict())
        if not r.ok:
            return text(f"error ({r.status}): {r.error}", True)
        lines = [f"{e['mode']} {e['type']:9} {e['size']:6} {e['name']}" for e in r.entries]
        return text("\n".join(lines) or "(empty)")

    tools = [sandbox_exec, sandbox_read_file, sandbox_list_dir]
    return create_sdk_mcp_server(SERVER, tools=tools), tools


@dataclass
class RunResult:
    condition: str
    prompt: str
    host_project: str
    tools_option: list[str]
    init: dict[str, Any] = field(default_factory=dict)
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    user_texts: list[str] = field(default_factory=list)  # Skill tool が差し込んだ本文などの、tool 結果以外のユーザ側メッセージ
    skill_results: list[dict[str, Any]] = field(default_factory=list)
    sandbox_calls: list[SandboxCall] = field(default_factory=list)
    final_text: str = ""
    models: list[str] = field(default_factory=list)
    cost_usd: float | None = None
    num_turns: int | None = None
    is_error: bool | None = None
    result_subtype: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @property
    def tool_names(self) -> list[str]:
        return [u["name"] for u in self.tool_uses]

    def sandbox_stdout(self) -> str:
        return "\n".join(c.result.get("stdout", "") or "" for c in self.sandbox_calls if c.tool == "sandbox_exec")


def _block_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)


def prepare_project(base: Path) -> Path:
    project = base / "project"
    shutil.copytree(SKILL_DIR, project / ".claude" / "skills" / SKILL_NAME)
    return project


def reset_sandbox(client: SandboxdClient, copy_skill: bool) -> None:
    client.delete(f"{ROOT_DIR}/.claude")
    if not copy_skill:
        return
    for src in SKILL_DIR.rglob("*"):
        if src.is_file():
            rel = src.relative_to(SKILL_DIR)
            mode = "0755" if src.stat().st_mode & 0o111 else "0644"
            r = client.write(f"{SANDBOX_SKILL_DIR}/{rel}", src.read_bytes(), mode=mode)
            if not r.ok:
                raise RuntimeError(f"skill copy failed: {rel}: {r.error}")


def build_options(condition: Condition, project: Path, config_dir: Path, server: Any) -> ClaudeAgentOptions:
    # tools=[] だと Skill tool も外れる(init の tools に出ない)ため、Skill は明示する
    builtin = ["Read"] if condition == "C" else []
    base_tools = builtin if condition == "plain" else ["Skill", *builtin]
    return ClaudeAgentOptions(
        model=MODEL,
        env={"ANTHROPIC_API_KEY": anthropic_api_key(), "CLAUDE_CONFIG_DIR": str(config_dir)},
        system_prompt=SYSTEM_PROMPT,
        tools=base_tools,
        allowed_tools=[*SANDBOX_TOOLS, *builtin],
        mcp_servers={SERVER: server},
        skills=None if condition == "plain" else [SKILL_NAME],
        setting_sources=["project"],
        permission_mode="bypassPermissions",
        cwd=str(project),
        max_turns=15,
        max_budget_usd=0.2,
    )


async def run_condition(condition: Condition, prompt: str, client: SandboxdClient | None = None) -> RunResult:
    own_client = client is None
    client = client or SandboxdClient()
    base = Path(tempfile.mkdtemp(prefix="skill-verify-"))
    try:
        project = prepare_project(base)
        config_dir = base / "claude-config"
        config_dir.mkdir()
        reset_sandbox(client, copy_skill=condition == "B")

        log: list[SandboxCall] = []
        server, _ = make_sandbox_server(client, PathMapper(project), log)
        options = build_options(condition, project, config_dir, server)
        rr = RunResult(condition, prompt, str(project), list(options.tools or []), sandbox_calls=log)

        skill_ids: set[str] = set()
        async for m in query(prompt=prompt, options=options):
            if isinstance(m, SystemMessage) and m.subtype == "init":
                rr.init = {k: m.data.get(k) for k in ("tools", "skills", "slash_commands", "model", "cwd", "mcp_servers")}
            elif isinstance(m, AssistantMessage):
                if m.model and m.model not in rr.models:
                    rr.models.append(m.model)
                for b in m.content:
                    if isinstance(b, ToolUseBlock):
                        rr.tool_uses.append({"id": b.id, "name": b.name, "input": b.input})
                        if b.name == "Skill":
                            skill_ids.add(b.id)
                    elif isinstance(b, TextBlock):
                        rr.final_text = b.text if not rr.final_text else rr.final_text + "\n" + b.text
            elif isinstance(m, UserMessage):
                if isinstance(m.content, str):
                    rr.user_texts.append(m.content)
                    continue
                for b in m.content:
                    if isinstance(b, ToolResultBlock):
                        entry = {"tool_use_id": b.tool_use_id, "is_error": b.is_error, "content": _block_text(b.content)}
                        rr.tool_results.append(entry)
                        if b.tool_use_id in skill_ids:
                            rr.skill_results.append({**entry, "tool_use_result": m.tool_use_result})
                    elif isinstance(b, TextBlock):
                        rr.user_texts.append(b.text)
            elif isinstance(m, ResultMessage):
                rr.cost_usd = m.total_cost_usd
                rr.num_turns = m.num_turns
                rr.is_error = m.is_error
                rr.result_subtype = m.subtype
                if m.result:
                    rr.final_text = m.result
        return rr
    finally:
        shutil.rmtree(base, ignore_errors=True)
        if own_client:
            client.close()
