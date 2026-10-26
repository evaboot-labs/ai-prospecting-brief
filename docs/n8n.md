# Run it in n8n

[`n8n/ai-prospecting-brief.json`](../n8n/ai-prospecting-brief.json) is the same brief for n8n. Evaboot sends each day's new people to a webhook, and every weekday at 8 Claude writes the brief into a Google Sheet.

## What runs

**Collect** (each time Evaboot sends a run):

1. **New people from Evaboot** (Webhook): one URL per signal, ending in `/changed_jobs` or `/posted`.
2. **Signal rows** (Code) and **Add to Signals**: one row per person in the Signals tab, with the signal and the date.

**Brief** (every weekday at 8):

1. **Signals** and **Earlier briefs** read both tabs.
2. **Merge and score** (Code): the people of the last 7 days who were never in a brief, one row per person with all their signals, scored like `brief.py`.
3. **Judge and write** (AI Agent with Claude): fit or not, why now, the next step and one concrete action, for the best 16.
4. **Check and rank** (Code): drops an incomplete verdict, turns `email` into `linkedin` when the email is not verified, and keeps the top 10.
5. **Add to Brief**: today's rows in the Brief tab, plus the people judged not a fit, so nobody is judged twice.

## Set it up

1. **Make the sheet:** one Google Sheet with two tabs.
   - `Signals`, header row: `Received, Signal, Id, Name, Title, Company, Employees, Growth 1y %, Sales team, Months in role, Email, Email status, Headline, Company description, LinkedIn`
   - `Brief`, header row: `Date, Rank, Id, Name, Title, Company, Signals, Why now, Next step, Action, Email, LinkedIn`
2. **Import** the JSON in n8n: *Workflows > Import from file*.
3. **Add two credentials:** **Anthropic** on the Claude node, and **Google Sheets** on the four sheet nodes.
4. **Fill in both settings nodes** (Collect settings and Brief settings hold the same fields): `signals_tab_url` and `brief_tab_url` (each with its `gid`), `top`, `buyers` and `offer`.
5. **Publish** the workflow. Open **New people from Evaboot** and copy its production URL. It looks like `https://<you>.app.n8n.cloud/webhook/<id>/evaboot-brief/:signal`.
6. **Connect Evaboot,** from your AI Agent with the Evaboot MCP, or in Evaboot's Integrations page:
   - Add a webhook destination per signal: the URL with `:signal` replaced by `changed_jobs`, then by `posted`.
   - Create a daily recurring export of each signal search and attach it to its destination.
7. **Test:** push one finished export to each destination (no credits), check the Signals tab, then click **Execute workflow** on **Every weekday at 8** and read the Brief tab.

## Good to know

- Each daily run spends 1 Evaboot credit per new person. Only people new to the search are exported.
- To change who fits, edit `buyers` in both settings nodes. Keep it in step with `SIGNALS.md` if you also run the brief from your agent.
- Add a signal (for example a search on a hiring keyword) by adding a destination with its own name at the end of the URL, and a weight for it in **Merge and score**.

Back to the [README](../README.md).
