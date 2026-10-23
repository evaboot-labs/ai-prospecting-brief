---
name: ai-prospecting-brief
description: Write a daily AI prospecting brief from real buying signals - run Sales Navigator signal searches through Evaboot (people who changed jobs, people who posted on LinkedIn), export the new people with verified emails, merge and score their signals, judge each one against SIGNALS.md, and list who to contact today, why now, and the next step. Use when the user asks for AI prospecting, a daily prospecting brief, signal-based prospecting, or who to contact today.
---

# AI prospecting brief

This skill runs inside a clone of https://github.com/evaboot-labs/ai-prospecting-brief: it uses the repo's `brief.py`, `SIGNALS.md` and `docs/`. If `brief.py` is not in the working directory, clone the repo and work from there.

You do the Sales Navigator and Evaboot work through the Evaboot MCP server (`https://mcp.evaboot.com/mcp`). Every tool named below is an Evaboot MCP tool. You judge the people yourself. `brief.py` merges the signals, checks your verdicts and renders the brief.

## Rules

- **You never contact anyone.** The brief tells the user who to contact and how; they do it.
- Confirm with the user before `export_sn_search_or_list` and `create_recurring_export`. Show the count and the cost (1 Evaboot credit per exported lead), then wait for a yes.
- Judge each person only from their row in `queue/leads.json` and `SIGNALS.md`. Never invent a fact.
- Never ask for or paste an API key. The user writes `EVABOOT_API_KEY` into `.env` and exports it before starting the agent (`docs/connect-your-agent.md`).
- Print every Sales Navigator URL as a Markdown link with the URL in angle brackets: `[Open in Sales Navigator](<url>)`.

## Step 0: check the setup

1. If the Evaboot MCP tools are not in this session, walk the user through `docs/connect-your-agent.md`, then ask them to restart the agent from this folder.
2. Otherwise call `verify_token` and `get_daily_export_quota`. If `has_valid_salesnav` is false, ask the user to sign in to Evaboot in Chrome, open any Sales Navigator search with the Evaboot extension, and click Export with Evaboot, then call the quota again.
3. Run `mkdir -p data queue briefs`.
4. Read `SIGNALS.md`. If it says `Status: EXAMPLE`, ask the user who they sell to, who is not a fit, and what they sell in one line. Rewrite the file and set `Status: yours`.

## Step 1: the signal searches

1. Build the buyer search with `build_sn_search_from_prompt`, **people only** (roles, seniority, country). Add `INDUSTRY` and `COMPANY_HEADCOUNT` to the URL yourself: asking the builder for them starts a slow company-first crawl.
2. Make one URL per signal by adding one filter to the buyer search:
   - changed jobs: `(type:RECENTLY_CHANGED_JOBS,values:List((id:RPC,selectionType:INCLUDED)))`
   - posted on LinkedIn: `(type:POSTED_ON_LINKEDIN,values:List((id:RPOL,selectionType:INCLUDED)))`
3. Preview each with `search_sn_leads` (`count: 10`, free) and show the totals.

## Step 2: today's people

1. On a yes, export each signal search with `export_sn_search_or_list` and `max_results` (15 to 25 each), and poll `get_export` with `limit: 0` until `EXECUTED`.
2. Save each export, one file per signal and day: `set -a; [ -n "$EVABOOT_API_KEY" ] || . ./.env; set +a; curl -s -H "Authorization: Bearer $EVABOOT_API_KEY" https://api.evaboot.com/v1/extractions/<extraction_id>/ > data/<signal>-$(date +%F).json`
3. Merge the files of the last 7 days, one `--signal` per file. People already shown are in `data/seen.txt` and drop out, so a good person who missed today's top 10 competes again tomorrow:

```bash
python3 brief.py facts --signal changed_jobs=data/changed_jobs-2026-10-23.json \
  --signal posted=data/posted-2026-10-23.json --seen data/seen.txt > queue/leads.json
```

## Step 3: judge and write the brief

Write `queue/judged.json` for at least the top 10 of `queue/leads.json`: `{"id", "fit": true/false, "reason", "next_step", "action"}`. The reason is one line from their signals and profile. `next_step` is `email` only with a `safe` email, otherwise `linkedin`, `call` or `watch`. The action is one concrete sentence: what to say or do, without repeating the step name. Never guess gender: use the first name, "they" or the role, not he or she.

```bash
python3 brief.py check queue/leads.json queue/judged.json
python3 brief.py render queue/leads.json queue/judged.json --top 10 --seen data/seen.txt > briefs/$(date +%F).md
```

Fix every `FAIL`, render, and show the brief.

## Step 4: every day

Offer `create_recurring_export` on each signal export's `extraction_id` (daily). Each run returns only the people who are new to that search. Each run spends credits; say so before creating them. Each morning, skip step 2.1 (a new export costs credits again): find the latest run of each recurring export with `get_export_list`, then do steps 2.2, 2.3 and 3. Or set up the n8n version (`docs/n8n.md`), which receives the runs by webhook and writes the brief itself.
