"""results/judgements/*.json を集計して results/jev_summary.json を出す(6.1)。

    uv run python scripts/jev_summary.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from verify.config import RESULTS  # noqa: E402
from verify.records import save_json  # noqa: E402


def main() -> None:
    files = sorted((RESULTS / "judgements").glob("*.json"))
    cases, mismatches = [], []
    for f in files:
        d = json.loads(f.read_text())
        row = {"name": d["name"], "says_failed_prob": d["extra"].get("says_failed"), "judgements": d["judgements"]}
        cases.append(row)
        for j in d["judgements"]:
            if j["disagree"]:
                mismatches.append({"name": d["name"], **j, "response": d["response"]})
    n_values = sum(len(c["judgements"]) for c in cases)
    n_failed_q = sum(1 for c in cases if c["says_failed_prob"] is not None)
    # usage は Jev 呼び出しのトークン数。プロセスごとの累計なので、ここでは呼び出し回数だけを合計し、
    # トークン数は各ファイルに記録された累計の最大値(下限)を載せる。
    cumul = [d["jev_usage_cumulative"] for d in (json.loads(f.read_text()) for f in files)]
    out = {
        "cases": cases,
        "string_vs_jev_mismatches": mismatches,
        "totals": {
            "responses": len(cases),
            "value_judgements": n_values,
            "failure_judgements": n_failed_q,
            "jev_calls": n_values + n_failed_q,
            "max_cumulative_tokens_in_one_process": {
                "input_tokens": max((c["input_tokens"] for c in cumul), default=0),
                "output_tokens": max((c["output_tokens"] for c in cumul), default=0),
            },
        },
    }
    p = save_json("jev_summary.json", out)
    print(f"{p}: {out['totals']}, mismatches={len(mismatches)}")


if __name__ == "__main__":
    main()
