"""Jev(TypeSafe System One)による応答判定。noul 値(0〜1)を返す。"""

from __future__ import annotations


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


def passes(prob: float) -> bool:
    return prob > THRESHOLD
