import pytest
from langchain_core.tracers.langchain import wait_for_all_tracers
from langchain_google_genai import ChatGoogleGenerativeAI
from using_gemini_with_websearch import query


@pytest.mark.asyncio
async def test_query_weather():
    await query("今日のさいたま市の天気は？")


@pytest.mark.asyncio
async def test_query_vscode_meetup():
    await query("日本のコミュニティ VS Code Meetup の最後のイベントはいつかわかる？")

@pytest.mark.asyncio
async def test_query_google_search():
    model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview")
    model_with_search = model.bind_tools([{"google_search": {}}])

    resp = model_with_search.invoke("日本のコミュニティ VS Code Meetup の最後のイベントはいつかわかる？")
    print(resp.content_blocks)

    wait_for_all_tracers()
