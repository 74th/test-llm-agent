import pytest

from verify import jev

pytestmark = pytest.mark.live


def test_jev_splits_hit_and_miss():
    hit = jev.mentions_value("合言葉は KUMQUAT-7412 でした。", "KUMQUAT-7412")
    miss = jev.mentions_value("参照ファイルは読めませんでした。", "KUMQUAT-7412")
    assert jev.passes(hit), hit
    assert not jev.passes(miss), miss
    assert jev.usage_total()["calls"] >= 2
