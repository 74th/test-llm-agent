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
