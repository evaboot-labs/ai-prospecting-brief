"""Builds n8n/ai-prospecting-brief.json. Run: python3 n8n/build_workflow.py

Two entry points in one workflow:

1. Collect: each signal search has an Evaboot recurring export that posts its new people to
   /webhook/evaboot-brief/<signal> (changed_jobs, posted). The rows land in the Signals tab, dated.
2. Brief: every weekday at 8, the workflow reads the Signals tab, keeps the rows of the last 7 days
   that are not in an earlier brief, merges and scores them like brief.py, lets Claude judge
   the best ones (fit, why now, next step), and appends the brief to the Brief tab.
"""
import json
import uuid
from pathlib import Path

ANTHROPIC_CRED = {"anthropicApi": {"id": "", "name": "Anthropic"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}
MODEL = "claude-sonnet-5-5"

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, kind="main", out=0):
    connections.setdefault(a, {}).setdefault(kind, [])
    while len(connections[a][kind]) <= out:
        connections[a][kind].append([])
    connections[a][kind][out].append({"node": b, "type": kind, "index": 0})


def code(name, js, pos, **extra):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos, **extra)


def sheet(name, op, url_expr, pos, executeOnce=False, **params):
    p = {"operation": op,
         "documentId": {"__rl": True, "mode": "url", "value": url_expr},
         "sheetName": {"__rl": True, "mode": "url", "value": url_expr}, "options": {}, **params}
    extra = {"alwaysOutputData": True} if op == "read" else {}
    if executeOnce:
        extra["executeOnce"] = True
    node(name, "n8n-nodes-base.googleSheets", 4.7, p, pos, SHEETS_CRED, **extra)


def settings(name, pos):
    node(name, "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
        {"id": str(uuid.uuid4()), "name": k, "type": "string", "value": v} for k, v in [
            ("signals_tab_url", "PASTE_THE_SIGNALS_TAB_URL_WITH_GID"),
            ("brief_tab_url", "PASTE_THE_BRIEF_TAB_URL_WITH_GID"),
            ("top", "10"),
            ("buyers", "Heads, directors and VPs of Revenue Operations, Sales Operations or GTM Operations at US B2B "
                       "software companies of 51 to 500 employees. Not a fit: consultants, advisors, fractional and "
                       "independent roles; sales roles without operations in the title; companies under 51 or over 500."),
            ("offer", "Evaboot exports Sales Navigator searches to clean lists with verified emails, and can send each "
                      "week's new people straight to the CRM."),
        ]]}, "includeOtherFields": True, "options": {}}, pos)


ROWS_JS = r"""
// One row per person in the Evaboot run, tagged with the signal from the webhook path.
const signal = $json.params.signal;
const prospects = $json.body.prospects || [];
const num = v => { const n = parseFloat(String(v ?? '').replace(/[,%]/g, '')); return isNaN(n) ? '' : n; };
const words = s => String(s || '').split(/\s+/).join(' ').trim();
const now = new Date().toISOString();
return prospects.map(p => {
  const y = num(p['Years in Position']), m = num(p['Months in Position']);
  return { json: {
    'Received': now, 'Signal': signal,
    'Id': p['Linkedin URL Unique ID'] || p['Linkedin URL Public'] || p['Full Name'],
    'Name': p['Full Name'] || '', 'Title': String(p['Current Job'] || '').trim(), 'Company': p['Company Name'] || '',
    'Employees': p['Company Employee Range'] || '', 'Growth 1y %': num(p['Company Employee Growth 1 Year (%)']),
    'Sales team': num(p['Sales Team Size']), 'Months in role': (y === '' && m === '') ? '' : (y || 0) * 12 + (m || 0),
    'Email': p['Email'] || '', 'Email status': p['Email Status'] || 'not found',
    'Headline': words(p['Profile Headline']).slice(0, 200), 'Company description': words(p['Company Description']).slice(0, 300),
    'LinkedIn': p['Linkedin URL Public'] || '',
  } };
});
"""

MERGE_JS = r"""
// Same as brief.py facts: people received in the last 7 days and never in a brief, signals merged and scored.
// Someone over today's cap is not in the Brief tab, so they compete again tomorrow.
const WEIGHTS = { changed_jobs: 3, posted: 2, new_in_role: 1, fast_growth: 2, hypergrowth: 1, safe_email: 1 };
const shown = new Set($('Earlier briefs').all().map(r => String(r.json['Id'] || '')).filter(Boolean));
const since = Date.now() - 7 * 24 * 3600 * 1000;
const people = {};
for (const { json: r } of $('Signals').all()) {
  if (!r['Id'] || shown.has(String(r['Id'])) || new Date(r['Received']).getTime() < since) continue;
  const p = people[r['Id']] ??= { ...r, signals: new Set() };
  p.signals.add(r['Signal']);
}
const top = Number($('Brief settings').first().json.top) || 10;
const rows = Object.values(people).map(p => {
  const months = p['Months in role'] === '' ? null : Number(p['Months in role']);
  const growth = p['Growth 1y %'] === '' ? null : Number(p['Growth 1y %']);
  if (months !== null && months < 3) p.signals.add('new_in_role');
  if (growth !== null && growth >= 30) p.signals.add('fast_growth');
  if (growth !== null && growth >= 100) p.signals.add('hypergrowth');
  if (String(p['Email status']).toLowerCase() === 'safe') p.signals.add('safe_email');
  const signals = [...p.signals].sort();
  return { ...p, signals, score: signals.reduce((s, x) => s + (WEIGHTS[x] || 0), 0) };
}).sort((a, b) => b.score - a.score || a.Name.localeCompare(b.Name));
if (!rows.length) return [];
// Judge a few more than the brief holds: some will not fit.
return [{ json: { people: rows.slice(0, top + 6), total: rows.length } }];
"""

BRIEF_JS = r"""
// brief.py check's required fields; an incomplete verdict is dropped, and an email step without a safe
// email becomes linkedin. Ranked by score like brief.py render, not by the order Claude answered in.
const LABELS = { changed_jobs: 'changed jobs', posted: 'posted on LinkedIn', new_in_role: 'under 3 months in role',
                 safe_email: 'verified email' };
const STEPS = new Set(['email', 'linkedin', 'call', 'watch']);
const verdicts = Object.fromEntries(($json.output.people || []).map(v => [v.id, v]));
const top = Number($('Brief settings').first().json.top) || 10;
const today = new Date().toISOString().slice(0, 10);
const out = [];
let rank = 0;
for (const p of $('Merge and score').first().json.people) {
  const v = verdicts[p.Id];
  if (!v) continue;
  const reason = String(v.reason || '').trim();
  let step = v.next_step, action = String(v.action || '').trim();
  if (v.fit && (!STEPS.has(step) || !action || !reason)) continue;
  if (v.fit && step === 'email' && String(p['Email status']).toLowerCase() !== 'safe') step = 'linkedin';
  const signals = p.signals.map(s => s === 'fast_growth' ? `company +${Math.round(p['Growth 1y %'])}% in a year`
    : (s === 'hypergrowth' ? '' : (LABELS[s] || s))).filter(Boolean).join(', ');
  if (v.fit && rank >= top) continue;  // over today's brief: tomorrow it is new again only if a new run brings it
  out.push({ json: {
    'Date': today, 'Rank': v.fit ? ++rank : 'not a fit', 'Id': p.Id, 'Name': p.Name, 'Title': p.Title,
    'Company': p.Company, 'Signals': signals, 'Why now': reason, 'Next step': v.fit ? step : '',
    'Action': v.fit ? action : '', 'Email': v.fit && step === 'email' ? p.Email : '', 'LinkedIn': p.LinkedIn,
  } });
}
return out.sort((a, b) => (typeof a.json.Rank === 'number' ? a.json.Rank : 99) - (typeof b.json.Rank === 'number' ? b.json.Rank : 99));
"""

JUDGE_SYSTEM = """You write a daily prospecting brief. For each person in the JSON (their signals, title, company, size, growth, headline), decide if they fit the buyers below, then give one line on why now and the next step. Use only the facts given; never invent anything.

Return {people: [{id, fit, reason, next_step, action}]}:
- fit: true or false. A person outside the buyers is not a fit; the reason then says why in a few words.
- reason: one line under 30 words, built on their own signals and profile.
- next_step: "email" only if email_status is safe, otherwise "linkedin"; "call" only with a strong reason; "watch" when it is too early.
- action: one concrete sentence on what to say or do, specific to this person. Do not start it with the step name.
- Never guess anyone's gender: no he, she, him or her. Use the first name, \"they\" or the role.

Buyers:
{{ $('Brief settings').first().json.buyers }}

What we sell:
{{ $('Brief settings').first().json.offer }}"""

# 1. Collect
node("New people from Evaboot", "n8n-nodes-base.webhook", 2, {
    "httpMethod": "POST", "path": "evaboot-brief/:signal", "responseMode": "onReceived", "options": {},
}, [0, 0], webhookId=str(uuid.uuid4()))
settings("Collect settings", [220, 0])
code("Signal rows", ROWS_JS, [440, 0])
# Two runs can arrive at once (one per signal): "Use Append" keeps both instead of overwriting the same rows.
sheet("Add to Signals", "append", "={{ $('Collect settings').first().json.signals_tab_url }}", [660, 0],
      columns={"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []})
nodes[-1]["parameters"]["options"] = {"useAppend": True}

# 2. Brief
node("Every weekday at 8", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [
    {"field": "cronExpression", "expression": "0 8 * * 1-5"}]}}, [0, 360])
settings("Brief settings", [220, 360])
sheet("Signals", "read", "={{ $('Brief settings').first().json.signals_tab_url }}", [440, 360])
sheet("Earlier briefs", "read", "={{ $('Brief settings').first().json.brief_tab_url }}", [660, 360], executeOnce=True)
code("Merge and score", MERGE_JS, [880, 360], executeOnce=True)
node("Judge and write", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "hasOutputParser": True,
    "text": "={{ JSON.stringify($json.people.map(p => ({ id: p.Id, first_name: String(p.Name).split(' ')[0], signals: p.signals, title: p.Title, company: p.Company, "
            "employees: p.Employees, growth_1y_pct: p['Growth 1y %'], sales_team: p['Sales team'], "
            "months_in_role: p['Months in role'], email_status: p['Email status'], headline: p.Headline, "
            "company_description: p['Company description'] }))) }}",
    "options": {"systemMessage": "=" + JUDGE_SYSTEM, "maxIterations": 3},
}, [1100, 360], retryOnFail=True, maxTries=3, waitBetweenTries=2000)
node("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 6000},
}, [1060, 560], ANTHROPIC_CRED)
node("Verdicts", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "schemaType": "manual",
    "inputSchema": json.dumps({"type": "object", "required": ["people"], "properties": {"people": {
        "type": "array", "items": {"type": "object", "required": ["id", "fit", "reason"], "properties": {
            "id": {"type": "string"}, "fit": {"type": "boolean"}, "reason": {"type": "string"},
            "next_step": {"type": "string"}, "action": {"type": "string"}}}}}}, indent=2),
}, [1220, 560])
code("Check and rank", BRIEF_JS, [1440, 360])
sheet("Add to Brief", "append", "={{ $('Brief settings').first().json.brief_tab_url }}", [1660, 360],
      columns={"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []})

for a, b in [("New people from Evaboot", "Collect settings"), ("Collect settings", "Signal rows"),
             ("Signal rows", "Add to Signals"), ("Every weekday at 8", "Brief settings"),
             ("Brief settings", "Signals"), ("Signals", "Earlier briefs"), ("Earlier briefs", "Merge and score"),
             ("Merge and score", "Judge and write"), ("Judge and write", "Check and rank"),
             ("Check and rank", "Add to Brief")]:
    link(a, b)
link("Claude", "Judge and write", "ai_languageModel")
link("Verdicts", "Judge and write", "ai_outputParser")

workflow = {"name": "AI prospecting brief (Evaboot + Claude)", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).with_name("ai-prospecting-brief.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print(out, len(nodes), "nodes")
