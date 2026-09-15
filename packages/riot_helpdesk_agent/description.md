# riot_helpdesk_agent

LangGraph helpdesk assistant for Riot Support tickets on Enterprise h2oGPTe.
Classifies the ticket, routes it to a knowledge branch, pulls player context over
MCP, and drafts a reply for a human Riot agent to review.

## How to call it

```python
from custom_agents import run_helpdesk

print(run_helpdesk(query="<full ticket text>"))
```

Signature is `run_helpdesk(query: str, chat_history: list[dict] | None = None) -> str`.

## Rules for the calling agent

1. Call `run_helpdesk` exactly once, passing the user's whole message as `query`.
2. Do not list available agents and do not inspect the schema first.
3. The return value is a finished Markdown report written for a human Riot support
   agent. Output it verbatim as your entire final answer.
4. Do not summarise it, re-title it, rebuild its tables, translate it, or wrap it in
   commentary about how the agent ran. Do not mention Python, tooling, or timings.
5. The report already states its own caveats under "Avisos" when something degraded.
   If that section is absent, nothing degraded — do not add warnings of your own.

## Deployment

Upload the ZIP to **Agents > Agents** with agent type `langgraph`, and assign the
Local MCP tool `riot-player-context`.
