"""Agent SDK: スキルのファイルがどこから読まれ、どこで実行されるか(spec: agent-sdk-skill-sandbox)。

条件 A: スキルはホストだけ / 条件 B: サンドボックスにもコピー / 条件 C: ホストの Read を許可。
結果は results/sdk_<条件>.json と results/judgements/sdk_<条件>.json に保存する。
"""

import re

import pytest

from verify import jev
from verify.records import save_json, save_judgements
from verify.sandboxd import SandboxdClient
from verify.sdk_agent import SANDBOX_TOOLS, PathMapper, RunResult, run_condition

pytestmark = [pytest.mark.anyio, pytest.mark.live]

PROMPT = "sandbox-probe スキルを使って、実行環境を調べて報告してください。"
PASSPHRASE = "KUMQUAT-7412"
MARKER = "SANDBOXD-LOCAL-a91f"
FORBIDDEN = {"Bash", "Write", "Edit", "Glob", "Grep", "Read", "NotebookEdit", "WebFetch", "WebSearch"}


@pytest.fixture(scope="module")
def sbx():
    c = SandboxdClient()
    if not c.health():
        pytest.skip("sandboxd が起動していない(scripts/sandboxd_up.sh)")
    yield c
    c.close()


def observe(rr: RunResult, sbx: SandboxdClient) -> dict:
    """tool 呼び出しの記録から、スキルのパス・参照ファイルの読み取り・スクリプト実行を取り出す。"""
    base = None
    for t in rr.user_texts:
        if m := re.search(r"Base directory for this skill: (\S+)", t):
            base = m.group(1)
    mapped_base = PathMapper(rr.host_project)(base) if base else None
    results = {r["tool_use_id"]: r for r in rr.tool_results}

    reference_reads = []
    for u in rr.tool_uses:
        if u["name"] == "Read" and "reference.md" in u["input"].get("file_path", ""):
            r = results.get(u["id"], {})
            reference_reads.append({
                "tool": "Read(host)", "path": u["input"]["file_path"],
                "ok": PASSPHRASE in r.get("content", ""), "result": r.get("content", "")[:300],
            })
    for c in rr.sandbox_calls:
        target = c.raw.get("path") or c.raw.get("command") or ""
        if "reference.md" in target:
            res = c.result
            ok = PASSPHRASE in ((res.get("content") or "") + (res.get("stdout") or ""))
            reference_reads.append({"tool": c.tool, "path": target, "mapped": c.mapped, "ok": ok,
                                    "result": res.get("error") or res.get("stderr") or "ok"})
    script_runs = [
        {"raw": c.raw["command"], "mapped": c.mapped["command"], "exit_code": c.result["exit_code"],
         "stdout": c.result["stdout"], "stderr": c.result["stderr"][:300]}
        for c in rr.sandbox_calls if c.tool == "sandbox_exec" and "probe" in c.raw["command"]
    ]
    return {
        "skill_called": "Skill" in rr.tool_names,
        "skill_base_dir": base,
        "skill_base_dir_mapped": mapped_base,
        "skill_base_dir_exists_in_sandbox": sbx.list(mapped_base).ok if mapped_base else None,
        "reference_reads": reference_reads,
        "script_runs": script_runs,
        "marker_in_sandbox_stdout": MARKER in rr.sandbox_stdout(),
        "script_file_executed_in_sandbox": any(
            r["exit_code"] == 0 and "PROBE_SCRIPT: /workspace/" in r["stdout"] for r in script_runs
        ),
    }


@pytest.mark.parametrize("condition", ["A", "B", "C"])
async def test_skill_condition(condition, sbx):
    rr = await run_condition(condition, PROMPT, sbx)
    obs = observe(rr, sbx)

    # どの条件でも、ホストのコマンド実行・ファイル操作の tool は使われない(条件 C の Read だけ許す)
    allowed = {"Skill", *SANDBOX_TOOLS} | ({"Read"} if condition == "C" else set())
    used = set(rr.tool_names)
    host_tools = used & (FORBIDDEN - ({"Read"} if condition == "C" else set()))

    text = rr.final_text
    js = [jev.judge_value("passphrase", text, PASSPHRASE), jev.judge_value("marker", text, MARKER)]
    failed_p = jev.says_failed(text)
    save_judgements(f"sdk_{condition}", text, js, {"says_failed": failed_p})
    save_json(f"sdk_{condition}.json", {
        **rr.to_dict(),
        "observation": obs,
        "judgement": {
            **{j.label: j.to_dict() for j in js},
            "says_failed": {"jev_prob": failed_p, "jev_pass": jev.passes(failed_p)},
        },
        "host_tools_used": sorted(host_tools),
    })

    assert not host_tools, host_tools
    assert used <= allowed, used - allowed
    assert all(m.startswith("claude-haiku-5-5") for m in rr.models), rr.models

    if condition == "B":
        assert obs["skill_called"]
        assert obs["marker_in_sandbox_stdout"], obs["script_runs"]
        assert PASSPHRASE in text and MARKER in text, text
        assert js[0].jev_pass and js[1].jev_pass, [j.to_dict() for j in js]
