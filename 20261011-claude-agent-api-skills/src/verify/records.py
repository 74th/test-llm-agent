"""結果ファイルの保存。秘密の値が混ざっていたら保存しない。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import jev
from .config import RESULTS, secret_values

JUDGEMENTS = RESULTS / "judgements"


def save_json(rel: str, data: Any) -> Path:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    for v in secret_values():
        if v in text:
            raise RuntimeError(f"{rel} に秘密の値が含まれているため保存しない")
    path = RESULTS / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    return path


def save_judgements(name: str, response: str, judgements: list[jev.Judgement], extra: dict[str, float] | None = None) -> Path:
    """1 つの応答に対する判定(文字列照合 + Jev)を results/judgements/<name>.json に保存する。"""
    return save_json(
        f"judgements/{name}.json",
        {
            "name": name,
            "response": response,
            "judgements": [j.to_dict() for j in judgements],
            "extra": extra or {},
            "jev_usage_cumulative": jev.usage_total(),
        },
    )
