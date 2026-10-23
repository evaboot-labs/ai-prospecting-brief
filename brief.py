"""Helpers for the AI prospecting brief. The agent exports the new people from your signal searches
through the Evaboot MCP and judges them; these commands merge the signals, score them, check the
agent's judgments and render the brief the same way every day. Nothing here touches the network.

    python3 brief.py facts --signal changed_jobs=data/jobs.json --signal posted=data/posts.json \\
        [--seen data/seen.txt] > queue/leads.json                 one row per person, signals merged, scored
    python3 brief.py check queue/leads.json queue/judged.json      the agent's verdicts: fit, reason, next step
    python3 brief.py render queue/leads.json queue/judged.json [--top 10] [--seen data/seen.txt] \\
        > briefs/<date>.md                                         the brief; --seen records who was shown
"""
import argparse
import json
import sys

# Points per signal. A person found by two signal searches outranks one found by a single search.
WEIGHTS = {"changed_jobs": 3, "posted": 2, "new_in_role": 1, "fast_growth": 2, "hypergrowth": 1, "safe_email": 1}
LABELS = {"changed_jobs": "changed jobs", "posted": "posted on LinkedIn", "new_in_role": "under 3 months in role",
          "fast_growth": "company +{growth}% in a year", "hypergrowth": "", "safe_email": "verified email"}
NEXT_STEPS = {"email", "linkedin", "call", "watch"}
MAX_REASON_WORDS = 30


def num(v):
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def facts(sources, seen):
    """sources: [(signal name, export.json)]. One entry per person, the signals they were found by plus the
    ones their own fields show, and a score. People already in an earlier brief are left out."""
    people = {}
    for signal, path in sources:
        for p in json.load(open(path)).get("prospects") or []:
            pid = p.get("Linkedin URL Unique ID") or p.get("Linkedin URL Public") or p.get("Full Name")
            if not pid or pid in seen:
                continue
            row = people.setdefault(pid, {"id": pid, "raw": p, "signals": set()})
            row["signals"].add(signal)
    out = []
    for pid, row in people.items():
        p, signals = row["raw"], row["signals"]
        years, months = num(p.get("Years in Position")), num(p.get("Months in Position"))
        in_role = None if years is None and months is None else (years or 0) * 12 + (months or 0)
        growth = num(p.get("Company Employee Growth 1 Year (%)"))
        if in_role is not None and in_role < 3:
            signals.add("new_in_role")
        if growth is not None and growth >= 30:
            signals.add("fast_growth")
        if growth is not None and growth >= 100:
            signals.add("hypergrowth")
        if (p.get("Email Status") or "").lower() == "safe":
            signals.add("safe_email")
        out.append({
            "id": pid, "name": p.get("Full Name") or "", "first_name": p.get("First Name") or "",
            "title": (p.get("Current Job") or "").strip(), "company": p.get("Company Name") or "",
            "employees": p.get("Company Employee Range") or "", "growth_1y_pct": growth,
            "sales_team": num(p.get("Sales Team Size")), "months_in_role": in_role,
            "headline": " ".join((p.get("Profile Headline") or "").split())[:200],
            "company_description": " ".join((p.get("Company Description") or "").split())[:300],
            "email": p.get("Email") or "", "email_status": p.get("Email Status") or "not found",
            "linkedin": p.get("Linkedin URL Public") or "",
            "signals": sorted(signals), "score": sum(WEIGHTS.get(s, 0) for s in signals),
        })
    out.sort(key=lambda r: (-r["score"], r["name"]))
    return out


def check(leads_path, judged_path, top=10):
    """Every person in the top of the list gets a verdict: fit or not, a short reason from their own signals,
    and a next step. Returns the problems found."""
    leads = {r["id"]: r for r in json.load(open(leads_path))}
    judged = json.load(open(judged_path))
    problems = []
    for j in judged:
        lead = leads.get(j.get("id"))
        if not lead:
            problems.append(f"unknown person {j.get('id')}")
            continue
        who = lead["name"]
        if j.get("fit") not in (True, False):
            problems.append(f"{who}: fit must be true or false")
        reason = str(j.get("reason") or "").strip()
        if not reason:
            problems.append(f"{who}: write the reason")
        elif len(reason.split()) > MAX_REASON_WORDS:
            problems.append(f"{who}: reason is {len(reason.split())} words, keep it under {MAX_REASON_WORDS}")
        if j.get("fit") and j.get("next_step") not in NEXT_STEPS:
            problems.append(f"{who}: next_step must be one of {sorted(NEXT_STEPS)}")
        if j.get("fit") and j.get("next_step") == "email" and lead["email_status"].lower() != "safe":
            problems.append(f"{who}: the email is {lead['email_status']}, not safe; use linkedin")
        action = str(j.get("action") or "").strip()
        if j.get("fit") and not action:
            problems.append(f"{who}: write the action, one concrete sentence")
        elif j.get("fit") and action.lower().startswith(str(j.get("next_step") or "?").lower()):
            problems.append(f"{who}: the action repeats the next step name, start with what to say or do")
    judged_ids = {j.get("id") for j in judged}
    for r in list(leads.values())[:top]:
        if r["id"] not in judged_ids:
            problems.append(f"no verdict for {r['name']} (in the top {top})")
    return problems


def signal_text(row):
    parts = []
    for s in row["signals"]:
        label = LABELS.get(s, s)
        if s == "fast_growth":
            label = label.format(growth=int(row["growth_1y_pct"]))
        if label:
            parts.append(label)
    return ", ".join(parts)


def render(leads_path, judged_path, top, seen_path, today):
    leads = json.load(open(leads_path))
    judged = {j["id"]: j for j in json.load(open(judged_path))}
    fits = [r for r in leads if judged.get(r["id"], {}).get("fit")][:top]
    skipped = [r for r in leads if r["id"] in judged and not judged[r["id"]].get("fit")]
    lines = [f"# Prospecting brief, {today}", "",
             f"{len(fits)} people to act on today, best signals first. "
             f"{len(leads)} new people found, {len(skipped)} judged not a fit.", "",
             "| # | Who | Signals | Why now | Next step |", "|---|---|---|---|---|"]
    for i, r in enumerate(fits, 1):
        j = judged[r["id"]]
        who = f"**{r['name']}**, {r['title']} at {r['company']}"
        step = f"**{j['next_step']}**: {j['action']}"
        lines.append(f"| {i} | {who} | {signal_text(r)} | {j['reason']} | {step} |")
    if skipped:
        lines += ["", "Not a fit: " + "; ".join(f"{r['name']} ({judged[r['id']]['reason']})" for r in skipped)]
    if seen_path:
        with open(seen_path, "a") as f:
            f.writelines(r["id"] + "\n" for r in fits + skipped)
    return "\n".join(lines) + "\n"


def main():
    import datetime
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("facts")
    a.add_argument("--signal", action="append", required=True, help="name=export.json, once per signal search")
    a.add_argument("--seen")
    a = sub.add_parser("check"); a.add_argument("leads"); a.add_argument("judged"); a.add_argument("--top", type=int, default=10)
    a = sub.add_parser("render"); a.add_argument("leads"); a.add_argument("judged")
    a.add_argument("--top", type=int, default=10); a.add_argument("--seen")
    args = ap.parse_args()
    if args.cmd == "facts":
        seen = set()
        if args.seen:
            try:
                seen = {line.strip() for line in open(args.seen) if line.strip()}
            except FileNotFoundError:
                pass
        sources = [tuple(s.split("=", 1)) for s in args.signal]
        rows = facts(sources, seen)
        both = sum(1 for r in rows if len({s for s, _ in sources} & set(r["signals"])) > 1)
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"{len(rows)} new people, {both} found by more than one search", file=sys.stderr)
    elif args.cmd == "check":
        problems = check(args.leads, args.judged, args.top)
        for p in problems:
            print("FAIL", p)
        print(f"{len(problems)} problems")
        sys.exit(1 if problems else 0)
    else:
        sys.stdout.write(render(args.leads, args.judged, args.top, args.seen, datetime.date.today().isoformat()))


if __name__ == "__main__":
    main()
