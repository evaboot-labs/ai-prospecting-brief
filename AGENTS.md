# Agent instructions

This repo is an AI prospecting brief. Every day it takes the new people from the user's Sales Navigator signal searches (people who changed jobs, people who posted on LinkedIn), merges and scores their signals, judges whether each one fits, and writes a short brief: who to contact today, why now, and the next step. The user does the outreach. When the user asks for a daily prospecting brief, AI prospecting, or "who should I contact today":

1. Follow the skill in `skills/ai-prospecting-brief/SKILL.md` step by step.
2. Read `SIGNALS.md` for the buyers, the signal searches, the offer and the brief rules. If it says `Status: EXAMPLE`, ask the user and update it.
3. Use `brief.py` to merge the signals, check your verdicts and render the brief. The Evaboot MCP server does the Sales Navigator work (`.mcp.json`).
4. If the user is not connected yet, follow `docs/connect-your-agent.md` with them.
5. If the user wants n8n instead, follow `docs/n8n.md` with them one step at a time: you cannot click inside n8n, so say exactly what to do and wait for their confirmation.

Previews are free; exports cost 1 Evaboot credit per lead. Confirm with the user before every export and before creating a recurring export. Never contact anyone yourself. Never ask for or handle an API key: the user writes it into `.env`. Never commit `.env`, `data/`, `queue/` or `briefs/`: they hold real people's data.
