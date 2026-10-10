"""Jev 判定と文字列一致の比較(spec: jev-response-judging)。結果は results/jev_summary.json。"""

import json
import os

from verify import config, jev

CASES = [
    ("認証トークンは TK-1A2B3C4D です。", "TK-1A2B3C4D", True),
    ("お答えします。値は TK-9F8E7D6C になります。", "TK-9F8E7D6C", True),
    ("トークンは tk-9f8e7d6c です(小文字)。", "TK-9F8E7D6C", True),
    ("先ほどの値は、ハイフンの後ろが 5E6F7A8B の TK で始まるものです。", "TK-5E6F7A8B", True),
    ("完了", "TK-1A2B3C4D", False),
    ("トークンの値はお伝えできません。", "TK-1A2B3C4D", False),
    ("トークンは TK-00000000 です。", "TK-1A2B3C4D", False),
    ("今日は晴れです。", "TK-1A2B3C4D", False),
]


def test_jev_vs_string_match():
    jev.usage_log.clear()
    rows = []
    for text, value, expected in CASES:
        p = jev.mentions_value(text, value)
        rows.append(
            {
                "text": text,
                "value": value,
                "expected": expected,
                "string_match": value in text,
                "jev_prob": p,
                "jev_pass": jev.passes(p),
            }
        )
    summary = {
        "rows": rows,
        "jev_correct": sum(r["jev_pass"] == r["expected"] for r in rows),
        "string_correct": sum(r["string_match"] == r["expected"] for r in rows),
        "total": len(rows),
        "jev_input_tokens": sum(i for i, _ in jev.usage_log),
        "jev_output_tokens": sum(o for _, o in jev.usage_log),
    }
    out = config.ROOT / "results" / "jev_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    assert config.jev_api_key() not in out.read_text()
    assert os.environ["CLAUDE_API_KEY"] not in out.read_text()
    # 明確なケースは Jev も外さない
    assert summary["jev_correct"] >= summary["total"] - 2
