import pytest
from using_skill_and_tools import query


@pytest.mark.asyncio
async def test_query_weather():
    await query("今日のさいたま市の天気は？")

@pytest.mark.asyncio
async def test_query_pentelpantel():
    await query("ペンテルパンテルとは何ですか？")
