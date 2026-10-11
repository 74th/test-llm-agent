"""Managed Agents: Skills API のスキルがワーカーコンテナにどう置かれ、どう実行されるか
(spec: managed-agent-skill-sandbox)。scripts/worker_up.sh でワーカーを起動しておく。"""

import subprocess

import pytest

from verify import config, jev
from verify.managed import run_session
from verify.records import save_json, save_judgements

pytestmark = pytest.mark.live

WORKER = "verify-cma-worker"
MARKER = "CMA-WORKER-LOCAL-5c2e"
PASSPHRASE = "KUMQUAT-7412"
PROMPTS = {
    "natural": "sandbox-probe スキルを使って、実行環境を調べて報告してください。",
    "with_path": (
        "sandbox-probe スキルのファイルは /workspace/skills/sandbox-probe/ にあります。"
        "その SKILL.md を読み、書かれた手順に従って実行環境を調べ、報告してください。"
    ),
}


def worker_running() -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", WORKER], capture_output=True, text=True)
    return r.stdout.strip() == "true"


@pytest.fixture(scope="module", autouse=True)
def _require_worker():
    if not config.has_environment_key():
        pytest.skip(".env に ANTHROPIC_ENVIRONMENT_ID / ANTHROPIC_ENVIRONMENT_KEY が無い")
    if not worker_running():
        pytest.skip("ワーカーが起動していない(scripts/worker_up.sh)")


def test_worker_has_no_api_key():
    env = subprocess.run(
        ["docker", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", WORKER],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    names = {e.split("=", 1)[0] for e in env if e}
    assert "ANTHROPIC_API_KEY" not in names and "CLAUDE_API_KEY" not in names
    assert {"ANTHROPIC_ENVIRONMENT_ID", "ANTHROPIC_ENVIRONMENT_KEY"} <= names


def test_marker_via_session():
    run = run_session("bash ツールで `cat /etc/sandbox-marker` を実行して、出力をそのまま答えてください。", title="marker")
    save_json("managed_marker.json", run.to_dict())
    assert MARKER in run.tool_output() or MARKER in run.final_text, run.to_dict()


def probe_runs(run) -> list[dict]:
    results = {r["tool_use_id"]: r for r in run.tool_results}
    out = []
    for u in run.tool_uses:
        cmd = (u.get("input") or {}).get("command", "")
        if "probe" in cmd:
            r = results.get(u["id"], {})
            out.append({"command": cmd, "is_error": r.get("is_error"), "output": r.get("content", "")[:600]})
    return out


def reads(run, needle: str) -> list[dict]:
    results = {r["tool_use_id"]: r for r in run.tool_results}
    out = []
    for u in run.tool_uses:
        inp = u.get("input") or {}
        target = inp.get("file_path") or inp.get("path") or inp.get("command") or inp.get("pattern") or ""
        if needle in str(target):
            r = results.get(u["id"], {})
            out.append({"tool": u["name"], "input": inp, "is_error": r.get("is_error"), "output": r.get("content", "")[:300]})
    return out


@pytest.mark.parametrize("kind", ["natural", "with_path"])
def test_skill_in_worker(kind):
    run = run_session(PROMPTS[kind], title=f"skill-{kind}")
    text = run.final_text
    tool_out = run.tool_output()
    js = [jev.judge_value("passphrase", text, PASSPHRASE), jev.judge_value("marker", text, MARKER)]
    failed_p = jev.says_failed(text)
    obs = {
        "tool_names": [u["name"] for u in run.tool_uses],
        "skill_md_reads": reads(run, "SKILL.md"),
        "reference_reads": reads(run, "reference.md"),
        "script_runs": probe_runs(run),
        "marker_in_tool_output": MARKER in tool_out,
        "script_path_in_output": [l for l in tool_out.splitlines() if l.startswith("PROBE_SCRIPT:")],
        "passphrase_in_tool_output": PASSPHRASE in tool_out,
    }
    save_judgements(f"managed_{kind}", text, js, {"says_failed": failed_p})
    save_json(f"managed_{kind}.json", {
        **run.to_dict(),
        "observation": obs,
        "judgement": {
            **{j.label: j.to_dict() for j in js},
            "says_failed": {"jev_prob": failed_p, "jev_pass": jev.passes(failed_p)},
        },
    })
    if kind == "with_path":
        assert obs["marker_in_tool_output"], obs
        assert js[1].string_match and js[1].jev_pass, text


def test_layout_in_container():
    """エージェントとは別に、セッション実行中のコンテナ内のスキルの配置と権限を docker exec で取る(5.6)。
    セッションが終わると /workspace/skills は空になるので、実行中に取る。"""
    import threading
    import time

    snaps: list[str] = []
    stop = threading.Event()

    def sh(cmd: str) -> str:
        r = subprocess.run(["docker", "exec", WORKER, "sh", "-c", cmd], capture_output=True, text=True)
        return f"$ {cmd}\n{r.stdout}{r.stderr}"

    def poll():
        while not stop.is_set():
            out = sh("ls -laR /workspace/skills")
            if "SKILL.md" in out:
                snaps.append(out + sh("find / -name SKILL.md -not -path '/proc/*' 2>/dev/null") + sh("ls -la /workspace"))
                return
            time.sleep(0.3)

    th = threading.Thread(target=poll)
    th.start()
    try:
        run = run_session(
            "bash ツールで `ls -laR /workspace/skills; which python3` を実行して、出力をそのまま答えてください。",
            title="layout",
        )
    finally:
        stop.set()
        th.join()
    text = "\n".join([
        "# docker exec(セッション実行中のスナップショット)",
        snaps[0] if snaps else "(スナップショットを取れなかった)",
        sh("which python3; python3 --version"),
        "# docker exec(セッション終了後)",
        sh("ls -laR /workspace/skills"),
        "# エージェントの bash の出力",
        run.tool_output(),
    ])
    (config.RESULTS / "managed_layout.txt").write_text(text)
    assert snaps and "SKILL.md" in snaps[0]
