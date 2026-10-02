"""Turn the activity log into the impact numbers judges ask for.

  python main.py metrics          -> human-readable report
  python main.py metrics --json   -> machine-readable

Everything here is measured from data/activity.log and the client state file.
The only assumption is the manual baseline, which is configurable.
"""
import json
import os
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List

import config
import store

# How long an account manager realistically needs to onboard a client by hand:
# chase the questionnaire, chase the files, chase the sign-off. Adjust with
# AGENT_MANUAL_BASELINE_MINUTES if you measure your own agency.
MANUAL_BASELINE_MINUTES = int(os.environ.get("AGENT_MANUAL_BASELINE_MINUTES", "90"))

PATTERNS = {
    "start": re.compile(r"Agency started onboarding"),
    "complete": re.compile(r"Onboarding completed"),
    "tool": re.compile(r"Agent called tool: (\w+)"),
    "client_msg": re.compile(r"Agent received client message"),
    "doc": re.compile(r"Agent processed document (.+?) -> (\w+), (\d+) chars"),
    "save": re.compile(r"Agent (saved|updated) ([a-z ]+)$"),
    "brief": re.compile(r"Agent generated client brief"),
    "tasks": re.compile(r"Agent created (\d+) internal tasks"),
    "reply": re.compile(r"Agent replied to client"),
}


def _read_lines() -> List[str]:
    if not config.ACTIVITY_FILE.exists():
        return []
    return [ln for ln in config.ACTIVITY_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _at(line: str):
    try:
        return datetime.strptime(line.split()[0], "%H:%M")
    except (ValueError, IndexError):
        return None


def analyse() -> Dict:
    lines = _read_lines()
    state = store.load_state()
    tools: Counter = Counter()
    docs: List[Dict] = []
    stamps = [_at(l) for l in lines]
    stamps = [s for s in stamps if s]

    client_msgs = sum(1 for l in lines if PATTERNS["client_msg"].search(l))
    tool_calls = sum(1 for l in lines if PATTERNS["tool"].search(l))
    for l in lines:
        m = PATTERNS["tool"].search(l)
        if m:
            tools[m.group(1)] += 1
    for l in lines:
        m = PATTERNS["doc"].search(l)
        if m:
            docs.append({"filename": m.group(1), "kind": m.group(2), "chars": int(m.group(3))})

    # Onboarding window: last start -> its completion, falling back to whole log.
    start_idx = max((i for i, l in enumerate(lines) if PATTERNS["start"].search(l)), default=None)
    end_idx = max((i for i, l in enumerate(lines) if PATTERNS["complete"].search(l)), default=None)
    window = lines[start_idx:end_idx + 1] if start_idx is not None and end_idx is not None else lines
    wstamps = [_at(l) for l in window]
    wstamps = [s for s in wstamps if s]
    elapsed = int((max(wstamps) - min(wstamps)).total_seconds() / 60) if len(wstamps) > 1 else 0

    fields = len(state.get("information", {}))
    total_fields = len(__import__("tools").REQUIREMENTS)
    completed = state.get("onboarding_complete", False)
    chars = sum(d["chars"] for d in docs)

    manual = MANUAL_BASELINE_MINUTES
    saved = max(manual - elapsed, 0)
    per_msg = round(tool_calls / client_msgs, 1) if client_msgs else 0

    return {
        "client": state.get("business_name"),
        "onboarding_complete": completed,
        "fields_collected": fields,
        "fields_required": total_fields,
        "client_messages_received": client_msgs,
        "tool_calls": tool_calls,
        "tool_breakdown": dict(tools.most_common()),
        "documents_processed": len(docs),
        "document_chars_extracted": chars,
        "agent_minutes_elapsed": elapsed,
        "manual_baseline_minutes": manual,
        "minutes_saved": saved,
        "percent_time_saved": round(100 * saved / manual) if manual else 0,
        "agent_actions_per_client_message": per_msg,
        "questions_the_client_had_to_answer": client_msgs,
        "brief_generated": any(PATTERNS["brief"].search(l) for l in lines),
        "tasks_created": sum(int(PATTERNS["tasks"].search(l).group(1))
                             for l in lines if PATTERNS["tasks"].search(l)),
    }


def report(m: Dict) -> str:
    done = "yes" if m["onboarding_complete"] else "no"
    rows = [
        ("SME onboarded", m["client"] or "-"),
        ("Onboarding completed", done),
        ("Information fields collected", f"{m['fields_collected']}/{m['fields_required']}"),
        ("Wall-clock, start to brief+tasks", f"{m['agent_minutes_elapsed']} min"),
        ("Same onboarding done manually (baseline)", f"{m['manual_baseline_minutes']} min"),
        ("Time returned to the agency", f"{m['minutes_saved']} min ({m['percent_time_saved']}%)"),
        ("Client messages needed", m["questions_the_client_had_to_answer"]),
        ("Agent tool calls executed", m["tool_calls"]),
        ("Actions per client message", m["agent_actions_per_client_message"]),
        ("Documents parsed", m["documents_processed"]),
        ("Characters extracted from documents", m["document_chars_extracted"]),
        ("Client brief generated", "yes" if m["brief_generated"] else "no"),
        ("Internal agency tasks created", m["tasks_created"]),
    ]
    lines = [
        f"# Impact — {m['client']} onboarding",
        "",
        "_All figures measured from data/activity.log and the client state file._",
        "",
        "| Measure | Value |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in rows]
    lines += [
        "",
        "## Where the agent's work went",
        "",
    ]
    lines += [f"- `{name}` x{count}" for name, count in m["tool_breakdown"].items()]
    lines += [
        "",
        f"The manual baseline ({m['manual_baseline_minutes']} min) is the assumption in "
        f"`AGENT_MANUAL_BASELINE_MINUTES` in config.py — replace it with your agency's "
        "measured figure before you present.",
    ]
    return "\n".join(lines)


def main() -> None:
    m = analyse()
    if "--json" in os.sys.argv:
        print(json.dumps(m, indent=2))
    else:
        print(report(m))
    out = config.DATA_DIR / "impact_report.md"
    out.write_text(report(m), encoding="utf-8")
    print(f"\nwritten: {out}")