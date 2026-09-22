---
name: configuration-probe
description: Verify that this self-hosted session loaded its configured skill.
---

When the user asks to verify agent configuration, respond with the exact line
`SKILL_PROBE=amber-orbit`. If they also ask to check documentation, use the
`openai_docs` MCP server and include `MCP_PROBE=used` after the skill line.
