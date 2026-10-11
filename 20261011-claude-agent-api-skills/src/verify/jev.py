"""Jev(TypeSafe System One)による応答判定。noul 値(0〜1)を返す。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from typesafe_sdk import TypeSafeClient

from .config import jev_api_key

THRESHOLD = 0.3  # noul がこの値より大きければ「述べている」と判定

_client: TypeSafeClient | None = None
usage_log: list[tuple[int, int]] = []


def client() -> TypeSafeClient:
    global _client
    if _client is None:
        _client = TypeSafeClient(api_key=jev_api_key())
    return _client


def noul(state: str, question: str) -> float:
    """state に対する真偽質問の確率。"""
    res = client().system_one(
        state=state,
        questions={"q": {"type": "noul", "instructions": question}},
    )
    u = getattr(res, "usage", None)
    if u is not None:
        usage_log.append((u.input_tokens, u.output_tokens))
    return float(res.answers["q"].noul)


def mentions_value(response_text: str, value: str) -> float:
    return noul(
        response_text,
        f"この文章は、値「{value}」を(そのまま)述べているか?",
    )


def says_failed(response_text: str) -> float:
    return noul(
        response_text,
        "この文章は、スクリプトの実行やファイルの読み取りに失敗した(できなかった)と述べているか?",
    )


def passes(prob: float) -> bool:
    return prob > THRESHOLD


def usage_total() -> dict[str, int]:
    return {
        "calls": len(usage_log),
        "input_tokens": sum(i for i, _ in usage_log),
        "output_tokens": sum(o for _, o in usage_log),
    }


@dataclass
class Judgement:
    """1 つの値についての、文字列照合と Jev の判定結果。"""

    label: str
    value: str
    string_match: bool
    jev_prob: float
    jev_pass: bool

    @property
    def disagree(self) -> bool:
        return self.string_match != self.jev_pass

    def to_dict(self) -> dict:
        return {**asdict(self), "disagree": self.disagree}


def judge_value(label: str, text: str, value: str) -> Judgement:
    p = mentions_value(text, value)
    return Judgement(label, value, value in text, p, passes(p))
