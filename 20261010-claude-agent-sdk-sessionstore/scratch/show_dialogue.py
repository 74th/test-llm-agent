import asyncio, sys, tempfile
from pathlib import Path
sys.path.insert(0, "src")
from claude_agent_sdk import AssistantMessage, UserMessage, TextBlock, ToolUseBlock, ToolResultBlock, ResultMessage
from verify.agent import *
from verify.file_store import FileSessionStore

def show(title, t):
    print(f"\n===== {title} =====")
    for m in t.messages:
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock) and b.text: print("[assistant text]", b.text)
                elif isinstance(b, ToolUseBlock): print("[assistant tool_use]", b.name, b.input)
        elif isinstance(m, UserMessage) and not isinstance(m.content, str):
            for b in m.content:
                if isinstance(b, ToolResultBlock): print("[tool_result]", b.content)
        elif isinstance(m, ResultMessage):
            print("[result]", repr(m.result), "session:", m.session_id[:8])

async def main():
    tmp = Path(tempfile.mkdtemp()); cwd = Path("workspace"); cwd.mkdir(exist_ok=True)
    issued = []
    p1 = "issue_token ツールで認証トークンを発行してください。"
    print("USER(1):", p1)
    t1 = await run_turn(p1, store=FileSessionStore(tmp/"s"), issued=issued, config_dir=new_config_dir(), cwd=cwd)
    show("1回目", t1)
    print("\n(正解値 issued =", issued, ")  返答に値が含まれる?:", issued[0] in t1.text)
    p2 = "先ほど issue_token が返したトークンの値を、そのまま答えてください。"
    print("\n--- 別 config dir + 新しい FileSessionStore インスタンスで resume ---\nUSER(2):", p2)
    t2 = await run_turn(p2, store=FileSessionStore(tmp/"s"), resume=t1.session_id, issued=issued, config_dir=new_config_dir(), cwd=cwd)
    show("2回目(resume)", t2)
    print("\nissued(再発行されていないか):", issued, " 2回目の返答に値が含まれる?:", issued[0] in t2.text)
asyncio.run(main())
