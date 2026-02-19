# BEDROCKと使う

## ChatBedrock を使う

```
BEDROCK_AWS_REGION=ap-northeast-1
AWS_BEARER_TOKEN_BEDROCK=xxx
```

```py
from langchain_aws import ChatBedrock

agent = create_deep_agent(
    backend=FilesystemBackend(root_dir=ROOT_DIR.as_posix()),
    model=ChatBedrock(
        # model="jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
        model="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        region="ap-northeast-1",
    ),
    # model="gemini-3-flash-preview",
    tools=[whther_search],
    skills=[SKILLS_DIR.as_posix()],
    system_prompt=instruction,
    checkpointer=checkpointer,
)
```

## OpenAIのWeb検索を使う

`tools=[{"type": "web_search_preview"}]` を指定することで、OpenAIのWeb検索ツールを利用できる。

```py
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="gpt-5.2",
    use_responses_api=True,
    output_version="responses/v1",
)

agent = create_deep_agent(
    backend=FilesystemBackend(root_dir=WORKSPACE_DIR.as_posix()),
    model=model,
    # Web検索ツールを有効化
    tools=[{"type": "web_search_preview"}],
    system_prompt=instruction,
    checkpointer=checkpointer,
)
```

## GeminiのWeb検索を使う

> [!CAUTION]
> 応答のパースに失敗したのかエラーで動かなかった

`tools=[{"type": "google_search"}]` を指定することで、GeminiのWeb検索ツールを利用できる。

```py
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview")

agent = create_deep_agent(
    backend=FilesystemBackend(root_dir=WORKSPACE_DIR.as_posix()),
    model=model,
    # Web検索ツールを有効化
    tools=[{"type": "google_search"}],
    system_prompt=instruction,
    checkpointer=checkpointer,
)
```
