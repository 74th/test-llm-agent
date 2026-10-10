import asyncio, sys, json, tempfile
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition, ResultMessage, AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock, UserMessage, query
from claude_agent_sdk._internal.sessions import project_key_for_directory
from verify.agent import make_probe_server, new_config_dir, TOOL_NAME
from verify.config import MODEL, sdk_env
from verify.file_store import FileSessionStore

async def run(prompt, store, issued, resume=None, cwd=None):
    opts = ClaudeAgentOptions(
        model=MODEL, env=sdk_env(new_config_dir()),
        system_prompt="あなたは検証用の親エージェントです。トークン発行は必ず worker サブエージェントに任せ、自分では issue_token を呼びません。worker の報告に含まれる値は、尋ねられるまで返答に書かないでください(返答は「完了」のみ)。",
        mcp_servers={"probe": make_probe_server(issued)},
        agents={"worker": AgentDefinition(description="トークンを発行する作業者", prompt="issue_token ツールを1回だけ呼び、返ってきた値を報告せよ。", tools=[TOOL_NAME], model="haiku")},
        allowed_tools=[TOOL_NAME, "Agent", "Task"], tools=["Agent"], permission_mode="bypassPermissions",
        setting_sources=[], max_turns=8, max_budget_usd=0.3, session_store=store, resume=resume, cwd=cwd)
    text, sid, msgs = "", None, []
    async for m in query(prompt=prompt, options=opts):
        msgs.append(m)
        if isinstance(m, AssistantMessage): text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        if isinstance(m, ResultMessage): sid = m.session_id
    return sid, text, msgs

async def main():
    tmp = Path(tempfile.mkdtemp()); cwd = Path("workspace").resolve(); issued = []
    store = FileSessionStore(tmp/"s")
    sid, text, msgs = await run("worker サブエージェントにトークンを発行させてください。", store, issued, cwd=cwd)
    for m in msgs:
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock): print("[tool_use]", b.name, str(b.input)[:80])
    print("1回目の返答:", repr(text), "| issued:", issued)
    pk = project_key_for_directory(str(cwd))
    print("store files:"); [print("  ", p.relative_to(tmp/"s")) for p in sorted((tmp/"s").rglob("*.jsonl"))]
    subs = await store.list_subkeys({"project_key": pk, "session_id": sid})
    print("list_subkeys:", subs)
    for sk in subs:
        ent = await store.load({"project_key": pk, "session_id": sid, "subpath": sk})
        print("subagent", sk, "entries:", len(ent), "| token in subagent transcript:", bool(issued) and issued[0] in json.dumps(ent))
    main_ent = await store.load({"project_key": pk, "session_id": sid})
    print("token in MAIN transcript:", bool(issued) and issued[0] in json.dumps(main_ent))
    sid2, text2, _ = await run("worker が発行したトークンの値を、そのまま答えてください。", FileSessionStore(tmp/"s"), issued, resume=sid, cwd=cwd)
    print("resume answer:", text2, "| ok:", bool(issued) and issued[0] in text2, "| issued count:", len(issued))
asyncio.run(main())
