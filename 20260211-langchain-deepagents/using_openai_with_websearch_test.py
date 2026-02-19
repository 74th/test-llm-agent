import pytest
from using_openai_with_websearch import query


@pytest.mark.asyncio
async def test_query_weather():
    await query("今日のさいたま市の天気は？")


@pytest.mark.asyncio
async def test_query_vscode_meetup():
    await query("日本のコミュニティ VS Code Meetup の最後のイベントはいつかわかる？")
