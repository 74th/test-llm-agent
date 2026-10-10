"""バックグラウンド tool 検証(spec: background-task-continuation)。"""

import json
import secrets
import time
from pathlib import Path

import pytest
from claude_agent_sdk import ClaudeSDKClient, query

from verify import config, jev
from verify.agent import new_config_dir
from verify.background import Recorder, bg_options, drain_until

pytestmark = pytest.mark.anyio

CWD = Path(__file__).resolve().parents[1] / "workspace"
FINDINGS = config.ROOT / "results" / "background_findings.json"


@pytest.fixture(autouse=True)
def _cwd():
    CWD.mkdir(exist_ok=True)
    FINDINGS.parent.mkdir(exist_ok=True)


def note(key: str, value) -> None:
    data = json.loads(FINDINGS.read_text()) if FINDINGS.exists() else {}
    data[key] = value
    FINDINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def new_case() -> tuple[int, str, str]:
    """(n, 期待値, シェル式)。期待値はプロンプトに現れず、実行時にだけ計算される。"""
    n = secrets.randbelow(9000) + 1000
    return n, f"R{n * 3}", f"R$(({n}*3))"


def bg_prompt(secs: int, expr: str) -> str:
    return f"バックグラウンドで `sleep {secs}; echo DONE-VALUE={expr}` を実行して。完了を待たず、すぐ返答して。"


async def start_and_first_result(c, rec, secs, expr, first_timeout=90):
    await c.query(bg_prompt(secs, expr))
    assert await drain_until(c, rec, until=lambda r: len(r.results) >= 1, timeout=first_timeout)
    return rec.results[0]


async def test_followup_on_completion_streaming():
    """4.1/4.3: 先に返答 → 完了を契機に、新規入力なしで追加応答。"""
    secs = 40
    _, value, expr = new_case()
    rec = Recorder()
    async with ClaudeSDKClient(bg_options(new_config_dir(), CWD)) as c:
        first = await start_and_first_result(c, rec, secs, expr)
        t_first = rec.events[-1].t
        assert t_first < secs - 10, f"完了待ちしている: {t_first}s"
        assert value not in (first.result or "")
        assert await drain_until(c, rec, until=lambda r: len(r.results) >= 2, timeout=secs + 60)
        second = rec.results[1]
        t_second = rec.events[-1].t
    assert t_second >= secs, f"完了前に追加応答が来た: {t_second}s"
    assert second.origin and second.origin["kind"] == "task-notification"
    assert value in second.result
    assert jev.passes(jev.mentions_value(second.result, value))
    note("streaming_client", {"secs": secs, "first_result_at": t_first, "followup_at": t_second,
                              "followup_origin": second.origin["kind"], "events": [e.__dict__ for e in rec.events if not e.kind.startswith("system:thinking")]})


async def test_question_while_waiting():
    """4.2: 待機中に別の質問へ応答でき、その後も完了通知の応答が来る。"""
    secs = 40
    _, value, expr = new_case()
    rec = Recorder()
    async with ClaudeSDKClient(bg_options(new_config_dir(), CWD)) as c:
        await start_and_first_result(c, rec, secs, expr)
        await c.query("待っている間に質問: 7かける8はいくつ?数字だけ答えて。")
        assert await drain_until(c, rec, until=lambda r: len(r.results) >= 2, timeout=60)
        t_mid = rec.events[-1].t
        assert t_mid < secs, f"待機中に応答できていない: {t_mid}s"
        assert "56" in rec.results[1].result
        assert await drain_until(c, rec, until=lambda r: len(r.results) >= 3, timeout=secs + 60)
    assert value in rec.results[2].result
    note("question_while_waiting", {"answered_at": t_mid, "completion_followup_still_delivered": True})


async def test_followup_with_oneshot_query():
    """one-shot の query() でも、完了通知の追加応答が同じイテレータで届くか。"""
    secs = 20
    _, value, expr = new_case()
    rec = Recorder()
    async for m in query(prompt=bg_prompt(secs, expr), options=bg_options(new_config_dir(), CWD)):
        rec.record(m)
    note("oneshot_query", {"results": len(rec.results), "origins": [(r.origin or {}).get("kind") for r in rec.results]})
    assert len(rec.results) >= 2
    assert value in rec.results[-1].result


async def test_client_closed_before_completion_then_resume():
    """4.4(代替方式の確認): 完了前にクライアントを閉じた場合、通知は届くか。届かなければ resume で通知を注入できるか。"""
    secs = 25
    _, value, expr = new_case()
    cfg = new_config_dir()
    rec = Recorder()
    out = CWD / f"bg-{value}.txt"
    cmd = f"sleep {secs}; echo DONE-VALUE={expr} | tee {out}"
    async with ClaudeSDKClient(bg_options(cfg, CWD)) as c:
        await c.query(f"バックグラウンドで `{cmd}` を実行して。完了を待たず、すぐ返答して。")
        assert await drain_until(c, rec, until=lambda r: len(r.results) >= 1, timeout=90)
        session_id = rec.results[0].session_id
    # クライアント終了 = CLI プロセス終了。バックグラウンド処理がその後も生き残るかを見る
    time.sleep(secs + 5)
    survived = out.exists()
    # アプリ側で完了を検知した想定で、通知文を新規入力として resume 注入する
    rec2 = Recorder()
    async with ClaudeSDKClient(bg_options(cfg, CWD, resume=session_id)) as c:
        await c.query(f"[完了通知] さきほどのバックグラウンドコマンドが完了しました。出力は DONE-VALUE={value} です。この値を報告してください。")
        assert await drain_until(c, rec2, until=lambda r: any(x.result for x in r.results), timeout=90)
    reply = next(x for x in rec2.results if x.result)
    note("client_closed_then_resume", {
        "background_process_survived_client_close": survived,
        "results_on_resume": [{"origin": (x.origin or {}).get("kind"), "num_turns": x.num_turns, "text": x.result[:80]} for x in rec2.results],
        "resume_injection_reply": reply.result,
    })
    assert value in reply.result


@pytest.mark.slow
async def test_five_minute_background():
    """4.5: 5分のバックグラウンド処理。`pytest -m slow` で手動実行。"""
    secs = 300
    _, value, expr = new_case()
    rec = Recorder()
    async with ClaudeSDKClient(bg_options(new_config_dir(), CWD)) as c:
        await start_and_first_result(c, rec, secs, expr)
        await c.query("待っている間に質問: 7かける8はいくつ?数字だけ答えて。")
        assert await drain_until(c, rec, until=lambda r: len(r.results) >= 2, timeout=60)
        assert await drain_until(c, rec, until=lambda r: len(r.results) >= 3, timeout=secs + 120)
        t = rec.events[-1].t
    assert t >= secs
    assert value in rec.results[2].result
    note("five_minutes", {"followup_at": t, "origin": (rec.results[2].origin or {}).get("kind")})
