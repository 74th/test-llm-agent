from verify import jev


def test_jev_noul_roundtrip():
    hit = jev.mentions_value("認証コードは TK-48213 です。", "TK-48213")
    miss = jev.mentions_value("今日は晴れです。", "TK-48213")
    assert 0.0 <= miss <= 1.0 and 0.0 <= hit <= 1.0
    assert hit > miss
